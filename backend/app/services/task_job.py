"""
任务执行引擎 — 后台 Job 管理
═══════════════════════════════════════════════════════════════════════════

负责管理每个用户的自动化任务生命周期，在独立线程中运行。

调用链:
  ws.py (WebSocket start_replay) ──→ job_manager.create() + start()
  payment.py (confirm_payment)   ──→ job_manager.mark_paid()
  tasks.py (progress recovery)   ──→ job_manager.mark_paid()  [恢复丢失的 job]

执行流程图:
┌──────────────────────────────────────────────────────────┐
│                      _run_job(session_id)                │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Phase 1: visit  (📖 阅读页面)                            │
│  ┌────────────────────────────────────────────┐           │
│  │  for each task URL:                        │           │
│  │    1. requests.Session().get(url)           │  ← 注册 viewed 状态
│  │    2. 进度回调 → _update() → _log_queue     │           │
│  │  _flush_logs()  →  批量写入 task_logs 表    │           │
│  │  job.visit_progress["done"] = True       │           │
│  └────────────────────────────────────────────┘           │
│                      ↓                                   │
│  Phase 2: replay  (🚀 完成发包)                            │
│  ┌────────────────────────────────────────────┐           │
│  │  for each task:                            │           │
│  │    1. 读取 Raw/{task_id}.npy               │  ← 截获的 xAPI 满分包
│  │    2. _rewrite_packet() 替换用户身份        │           │
│  │    3. requests.post() 发送给云校园           │  ← 提交满分
│  │    4. 进度回调 → _update() → _log_queue     │           │
│  │  _flush_logs()  →  批量写入                │           │
│  │  job["replay_progress"]["done"] = True      │           │
│  └────────────────────────────────────────────┘           │
│                      ↓                                   │
│  job["status"] = "done"                                   │
│  _mark_fulfilled()  →  DB: fulfilled=True                 │
│  loop.close()                                              │
└──────────────────────────────────────────────────────────┘

关键设计:
  - 每阶段日志先存入内存队列 _log_queue，阶段结束时批量 commit 到 SQLite
    避免 146 次高频写锁竞争导致 DB 损坏
  - visit_progress / replay_progress 分别追踪，支持断线重连恢复
  - _update() 同时更新 job["progress"] 和对应 phase 的 progress

WebSocket 断线恢复:
  DashboardWebSocket ──→ 重连 ──→ job_manager.get_status(sid)
  ──→ 返回 visit_progress + replay_progress
  ──→ 前端 ProgressPanel 从 jobStatus 恢复双进度条

异常处理:
  - 单任务失败不中断，计入 failed 计数
  - 整体异常 → job["status"]="failed"，记录异常消息
  - DB write 异常被 catch 吞噬（不能因日志写入失败导致任务崩溃）
"""

import asyncio
import logging
import threading
from datetime import datetime

from app.config import settings
from app.services.cloudcampus import query_all
from app.services.replayer import manual_set_done

logger = logging.getLogger(__name__)

from dataclasses import dataclass, field
from typing import Literal, ClassVar


@dataclass
class Job:
    session_id: str
    user_info: dict
    course_id: int = 11881

    # 任务
    view_tasks: list[dict] = field(default_factory=list)
    resend_tasks: list[dict] = field(default_factory=list)
    mark_tasks: list[dict] = field(default_factory=list)
    # 状态机
    StatusType: ClassVar = Literal[
        "pending", "running", "done", "partial", "failed", "stopped", "paused"
    ]
    PhaseType: ClassVar = Literal[
        "visit", "visit_done", "replay", "replay_done", "mark", "mark_done"
    ]

    status: StatusType = "pending"  # pending → running → done/failed/stopped/paused
    phase: PhaseType = "visit"  # visit → visit_done → replay → replay_done
    paused: bool = False

    # 进度
    progress: dict = field(
        default_factory=lambda: {"current": 0, "total": 0, "message": "", "title": ""}
    )
    visit_progress: dict = field(
        default_factory=lambda: {"current": 0, "total": 0, "done": False}
    )
    replay_progress: dict = field(
        default_factory=lambda: {"current": 0, "total": 0, "done": False}
    )
    mark_progress: dict = field(
        default_factory=lambda: {"current": 0, "total": 0, "done": False}
    )
    # 执行结果
    result: dict | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 内部追踪（不暴露给 API）
    _log_queue: list = field(default_factory=list, repr=False)
    _fail_streak: int = field(default=0, repr=False)

    def to_status_dict(self) -> dict:
        """返回给 API 的状态摘要"""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "phase": self.phase,
            "progress": dict(self.progress),
            "visit_progress": dict(self.visit_progress),
            "replay_progress": dict(self.replay_progress),
            "mark_progress": dict(self.mark_progress),
            "result": self.result,
            "created_at": self.created_at,
        }

    @property
    def log_queue(self):
        return self._log_queue

    @log_queue.setter
    def log_queue(self, value):
        self._log_queue = value


class TaskJobManager:
    """
    后台任务管理器（单例: job_manager）

    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  create()   │ ──→ │   start()   │ ──→ │ _run_job()  │
    │ 初始化 Job   │     │ 启动线程     │     │ 线程主循环   │
    └─────────────┘     └─────────────┘     └─────────────┘

    状态机:
      pending ──→ running ──→ done
                     └───────→ failed

    Job 数据结构:
      {
        "session_id": str,       # 用户邮箱
        "status": "pending|running|done|failed",
        "phase": "visit|visit_done|replay|replay_done",
        "progress": {current, total, message, title},
        "visit_progress": {current, total, done},   # 阅读阶段进度
        "replay_progress": {current, total, done},  # 发包阶段进度
        "tasks": [...],
        "user_info": {nickname, cookie, sesskey, user_id, password},
        "result": {total, success, failed, results},
        "_log_queue": [...]      # 待批量写入的日志
      }
    """

    def __init__(self):
        self._lock = threading.Lock()  # 保护 _jobs 字典的线程锁
        self._jobs: dict[str, Job] = {}  # {session_id: job_dict}
        self._threads: dict[str, threading.Thread] = {}  # {session_id: 执行线程}

    def create(
        self,
        session_id: str,
        user_info: dict,
        tasks: list[dict],
        course_id: int | None = None,
    ) -> Job:

        view_tasks, resend_tasks = [], []
        for t in tasks:
            if t.get("category_id") == 1:
                view_tasks.append(t)
            else:
                resend_tasks.append(t)

        with self._lock:
            existing = self._jobs.get(session_id)
            if existing is not None:
                if existing.status not in (
                    "done",
                    "partial",
                    "failed",
                    "stopped",
                    "paused",
                ):
                    # 已有进行中的 Job，直接复用，避免重复执行
                    return existing

            job = Job(
                session_id=session_id,
                status="pending",
                phase="visit",
                progress={
                    "current": 0,
                    "total": len(tasks),
                    "message": "",
                    "title": "",
                },
                visit_progress={
                    "current": 0,
                    "total": len(view_tasks),
                    "done": (len(view_tasks) == 0),
                },
                replay_progress={
                    "current": 0,
                    "total": len(resend_tasks),
                    "done": (len(resend_tasks) == 0),
                },
                view_tasks=view_tasks,
                resend_tasks=resend_tasks,
                user_info=user_info,
                course_id=course_id or settings.DEFAULT_COURSE_ID,
            )
            self._jobs[session_id] = job
            return job

    def start(self, session_id: str):
        """
        启动 Job 到独立线程（daemon，不阻塞主进程退出）

        幂等保护：若该 session 已有存活的执行线程，直接返回，避免
        mark_paid 被重复调用（payment 回调 + 进度恢复）时启动第二个线程
        重放同一批满分包 → 重复发包 / 重复扣量。
        """
        with self._lock:
            job = self._jobs.get(session_id)
            if not job:
                return
            existing = self._threads.get(session_id)
            if existing is not None and existing.is_alive():
                # 已有线程在跑，不重复启动
                return
            job.status = "running"
            job.paused = False
            job._fail_streak = 0
            thread = threading.Thread(
                target=self._run_job, args=(session_id,), daemon=True
            )
            self._threads[session_id] = thread
        thread.start()

    def stop(self, session_id: str):
        """管理员手动停止任务"""
        with self._lock:
            job = self._jobs.get(session_id)
            if job:
                job.status = "stopped"
                job.progress.message = "管理员已停止任务"

    def _run_job(self, session_id: str):
        """Job 主线程：visit → (re-login if needed) → replay → verify"""
        job = self._jobs.get(session_id)
        if not job:
            return

        try:
            job.status = "running"

            from app.services.replayer import (
                replay_all as _replay_all,
                visit_task_pages as _visit_pages,
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # ═══════ Phase 1: 阅读页面 ═══════
            # 必须先 registered view，云校园才会接受后续 grade 发包
            job.phase = "visit"
            self._update(
                session_id,
                current=0,
                total=len(job.view_tasks),
                message="正在阅读任务页面...",
            )
            visit_result = loop.run_until_complete(
                _visit_pages(
                    job.view_tasks,
                    job.user_info,
                    lambda p: self._update(session_id, phase="visit", **p),
                )
            )
            job.phase = "visit_done"
            self._update(
                session_id,
                current=visit_result["total"],
                total=visit_result["total"],
                message=f"页面阅读: {visit_result['visited']}成功/{visit_result['failed']}失败",
            )
            with self._lock:
                if job.visit_progress:
                    job.visit_progress["done"] = True
                    job.visit_progress["current"] = visit_result["total"]
            self._flush_logs(session_id)

            if job.paused or job.status == "stopped":
                loop.close()
                return

            # ═══════ Phase 2: 发包 ═══════
            job.phase = "replay"
            job._fail_streak = 0
            self._update(
                session_id,
                current=0,
                total=len(job.resend_tasks),
                message="开始完成任务...",
            )
            result = loop.run_until_complete(
                _replay_all(
                    job.resend_tasks,
                    job.user_info,
                    lambda p: self._update_with_fail_check(
                        session_id, phase="replay", **p
                    ),
                )
            )
            job.result = result
            job.phase = "replay_done"
            self._update(
                session_id,
                current=result["total"],
                total=result["total"],
                message=f"发包完成: {result['success']}成功/{result['failed']}失败",
            )
            with self._lock:
                if job.replay_progress:
                    job.replay_progress["done"] = True
                    job.replay_progress["current"] = result["total"]
            self._flush_logs(session_id)

            # 检查是否需要暂停
            if job.paused or job.status == "stopped":
                loop.close()
                return

            # ═══════ Phase 3: 手动处理 ═══════
            job.phase = "mark"
            cookies_str = job.user_info.get("cookie") or ""
            if not cookies_str:
                # 没有 cookie 无法标记完成，跳过 mark 阶段而不是崩溃整个 Job
                logger.warning(f"skip mark phase for {session_id}: missing cookie")
                job.mark_tasks = []
            else:
                job.mark_tasks = query_all(cookies_str, job.course_id)["tasks"]
            self._update(
                session_id,
                current=0,
                total=len(job.mark_tasks),
                message="正在点击任务页面...",
            )
            mark_result = loop.run_until_complete(
                manual_set_done(
                    job.mark_tasks,
                    job.user_info,
                    lambda p: self._update(session_id, phase="mark", **p),
                )
            )
            job.phase = "mark_done"
            self._update(
                session_id,
                current=mark_result["total"],
                total=mark_result["total"],
                message=f"手动处理: {mark_result['success']}成功/{mark_result['failed']}失败",
            )
            with self._lock:
                if job.mark_progress:
                    job.mark_progress["done"] = True
                    job.mark_progress["current"] = mark_result["total"]
            self._flush_logs(session_id)

            # ═══════ Phase 4: 验证结果 ═══════
            verify_result = None
            has_work = (
                visit_result.get("total", 0)
                + result.get("total", 0)
                + mark_result.get("total", 0)
                > 0
            )
            if has_work:
                self._update(session_id, message="正在验证任务完成状态...")
                verify_result = self._verify_completion(job)

            final_result = {
                **result,
                "visit": visit_result,
                "replay": result,
                "mark": mark_result,
                "verify": verify_result,
            }
            final_message, has_remaining = self._summarize_final_result(final_result)
            final_result["can_retry"] = has_remaining
            job.result = final_result
            job.status = "partial" if has_remaining else "done"
            self._update(session_id, message=final_message)
            self._queue_log(
                session_id,
                title="任务汇总",
                phase="final",
                status=job.status,
                message=final_message,
            )
            self._flush_logs(session_id)
            if job.status == "done":
                self._mark_fulfilled(session_id)
            loop.close()

        except Exception as e:
            logger.error(f"Job failed for {session_id}: {e}", exc_info=True)
            job.status = "failed"
            self._update(session_id, message=f"执行失败: {e}")
            self._queue_log(
                session_id,
                title="任务异常",
                phase=getattr(job, "phase", "unknown"),
                status="failed",
                message=f"执行失败: {e}",
            )
            try:
                self._flush_logs(session_id)
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    def _update_with_fail_check(self, session_id: str, **kwargs):
        """带连续失败检测的进度更新"""
        self._update(session_id, **kwargs)
        if kwargs.get("status") == "failed":
            job = self._jobs.get(session_id)
            if job:
                job._fail_streak = job._fail_streak + 1
                if job._fail_streak >= 10:
                    self._update(
                        session_id,
                        message="连续失败超过10次，自动暂停。请联系管理员或稍后重试。",
                    )
                    job.paused = True
                    job.status = "paused"
                    self._queue_log(
                        session_id,
                        title="自动暂停",
                        phase=kwargs.get("phase", job.phase),
                        status="paused",
                        message="连续失败超过10次",
                    )

    def _verify_completion(self, job: Job) -> dict:
        """发包完成后回查云校园验证任务是否真的完成"""
        try:
            from app.services.cloudcampus import query_all

            cookie = job.user_info.get("cookie", "")
            if not cookie:
                message = "验证失败: 登录态为空，无法确认任务是否已完成"
                self._update(job.session_id, message=message)
                return {
                    "checked": False,
                    "error": "missing_cookie",
                    "message": message,
                }
            result = query_all(cookie, job.course_id or settings.DEFAULT_COURSE_ID)
            if result.get("error"):
                message = f"验证失败: {result.get('error')}"
                self._update(job.session_id, message=message)
                return {
                    "checked": False,
                    "error": result.get("error"),
                    "message": message,
                }
            incomplete = result.get("tasks", [])
            total = result.get("total_h5p_count") or len(incomplete)
            done_count = max(total - len(incomplete), 0)
            self._update(
                job.session_id,
                message=f"验证完成: {done_count}/{total} 个任务已完成",
            )
            if len(incomplete) > 0:
                self._update(
                    job.session_id,
                    message=f"注意: 仍有 {len(incomplete)} 个任务显示未完成，可能需要手动检查",
                )
            return {
                "checked": True,
                "total": total,
                "done": done_count,
                "incomplete": len(incomplete),
                "incomplete_tasks": [
                    self._task_title(t) for t in incomplete[:10]
                ],
            }
        except Exception as e:
            logger.warning(f"_verify_completion failed: {e}")
            message = f"验证失败: {e}"
            self._update(job.session_id, message=message)
            return {
                "checked": False,
                "error": str(e),
                "message": message,
            }

    @staticmethod
    def _task_title(task) -> str:
        if isinstance(task, dict):
            return str(task.get("title") or task.get("name") or "")
        if isinstance(task, (list, tuple)) and task:
            return str(task[0])
        return str(task)

    def _summarize_final_result(self, result: dict) -> tuple[str, bool]:
        """生成不误导用户的最终文案，并返回是否仍需重试。"""
        visit = result.get("visit") or {}
        replay = result.get("replay") or {}
        mark = result.get("mark") or {}
        verify = result.get("verify") or {}

        failed_parts = []
        if visit.get("failed", 0) > 0:
            failed_parts.append(f"页面阅读 {visit['failed']} 个失败")
        if replay.get("failed", 0) > 0:
            failed_parts.append(f"发包 {replay['failed']} 个失败")
        if mark.get("failed", 0) > 0:
            failed_parts.append(f"手动处理 {mark['failed']} 个失败")

        remaining_parts = []
        if verify:
            if verify.get("incomplete", 0) > 0:
                remaining_parts.append(f"验证仍有 {verify['incomplete']} 个未完成")
            elif verify.get("error"):
                remaining_parts.append("最终验证失败，无法确认全部完成")

        if remaining_parts:
            parts = failed_parts + remaining_parts
            return "本轮处理结束，但" + "，".join(parts) + "。可点击重试再次处理。", True
        if failed_parts:
            return "所有任务已确认完成；本轮记录：" + "，".join(failed_parts), False
        return "所有任务已确认完成", False

    def _update(self, session_id: str, **kwargs):
        with self._lock:
            job = self._jobs.get(session_id)
            if job:
                job.progress.update(kwargs)
                phase = kwargs.get("phase", "")
                if phase == "visit":
                    job.visit_progress.update(
                        {
                            "current": kwargs.get(
                                "current", job.visit_progress["current"]
                            ),
                            "total": kwargs.get("total", job.visit_progress["total"]),
                        }
                    )
                elif phase == "replay":
                    job.replay_progress.update(
                        {
                            "current": kwargs.get(
                                "current", job.replay_progress["current"]
                            ),
                            "total": kwargs.get("total", job.replay_progress["total"]),
                        }
                    )
                elif phase == "mark":
                    job.mark_progress.update(
                        {
                            "current": kwargs.get(
                                "current", job.mark_progress["current"]
                            ),
                            "total": kwargs.get("total", job.mark_progress["total"]),
                        }
                    )

            status = kwargs.get("status", "")
            if kwargs.get("title") and status and self._should_log_task_status(status):
                self._queue_log_locked(
                    job,
                    session_id,
                    title=kwargs.get("title", ""),
                    phase=kwargs.get("phase", "replay"),
                    status=status,
                    message=kwargs.get("message", ""),
                )

    @staticmethod
    def _should_log_task_status(status: str) -> bool:
        return status in {"failed", "visit_failed", "set_failed"}

    def _queue_log(self, session_id: str, title: str, phase: str, status: str, message: str):
        with self._lock:
            job = self._jobs.get(session_id)
            if not job:
                return
            self._queue_log_locked(job, session_id, title, phase, status, message)

    @staticmethod
    def _queue_log_locked(
        job: Job,
        session_id: str,
        title: str,
        phase: str,
        status: str,
        message: str,
    ):
        job.log_queue.append(
            {
                "session_id": session_id,
                "nickname": job.user_info.get("nickname", ""),
                "title": title[:512],
                "phase": phase,
                "status": status,
                "message": message[:512],
            }
        )

    def _flush_logs(self, session_id: str):
        with self._lock:
            job = self._jobs.get(session_id)
            if not job or not job.log_queue:
                return
            entries = job.log_queue
            job.log_queue = []
        try:
            from app.database import SessionLocal
            from app.models.db_models import TaskLog

            db = SessionLocal()
            for e in entries:
                db.add(TaskLog(**e))
            db.commit()
            db.close()
        except Exception as e:
            logger.warning(f"_flush_logs failed: {e}")

    def _mark_fulfilled(self, session_id: str):
        """标记该用户最新一笔已付未完成的订单为 fulfilled=True"""
        try:
            from app.database import SessionLocal
            from app.models.db_models import PaymentOrder

            db = SessionLocal()
            order = (
                db.query(PaymentOrder)
                .filter(
                    PaymentOrder.user_id == session_id,
                    PaymentOrder.paid == True,
                    PaymentOrder.fulfilled == False,
                )
                .order_by(PaymentOrder.created_at.desc())
                .first()
            )
            if order:
                order.fulfilled = True  # type: ignore
                db.commit()
            db.close()
        except Exception as e:
            logger.warning(f"_mark_fulfilled failed: {e}")

    def get(self, session_id: str) -> Job | None:
        """获取完整 Job 数据"""
        return self._jobs.get(session_id)

    def get_active(self, session_id: str) -> Job | None:
        """
        返回仍在进行中的 Job（pending/running/paused），否则 None。

        用于登录复用登录态：进行中的任务持有一份有效 cookie，重新登录会让
        云校园颁发新会话、使该 cookie 失效，从而打断后台任务。此时应沿用任务
        自身的登录信息，而不是重新登录。
        """
        job = self._jobs.get(session_id)
        if job and job.status in ("pending", "running", "paused"):
            return job
        return None

    def get_status(self, session_id: str) -> dict | None:
        """
        获取 Job 状态摘要（用于 API 返回）

        返回:
          {session_id, status, phase, progress,
           visit_progress, replay_progress, result, created_at}
        """
        job = self._jobs.get(session_id)
        if not job:
            return None
        return job.to_status_dict()

    def mark_complete(self, session_id: str, message: str = "所有任务已确认完成"):
        with self._lock:
            job = self._jobs.get(session_id)
            if not job:
                return
            job.status = "done"
            job.progress.update({"message": message})
            if isinstance(job.result, dict):
                job.result["can_retry"] = False
        self._mark_fulfilled(session_id)

    def mark_paid(
        self,
        session_id: str,
        user_info: dict,
        tasks: list[dict],
        course_id: int | None = None,
    ):
        """
        支付确认后自动创建并启动 Job

        调用来源:
          payment.py confirm_payment()       ← zpayz 回调 / 轮询确认
          tasks.py get_progress()            ← 登录后恢复丢失的 job
        """
        self.create(
            session_id, user_info, tasks, course_id or settings.DEFAULT_COURSE_ID
        )
        self.start(session_id)


# 全局单例
job_manager = TaskJobManager()
