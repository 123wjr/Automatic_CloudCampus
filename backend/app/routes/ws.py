"""
WebSocket — 实时进度推送
═══════════════════════════════════════════════════════════

端点: ws://host/ws/progress/{session_id}

消息协议:
  客户端 → 服务端:
    {"type":"start_replay", "tasks":[...], "course_id":11881}
    {"type":"ping"}

  服务端 → 客户端:
    {"type":"phase", "message":"正在阅读任务页面...", "visit_progress":{...}, "replay_progress":{...}}
    {"type":"progress", "current":5, "total":100, "title":"...", "status":"success"}
    {"type":"finished", "status":"done|partial|failed|stopped", "message":"...", "result":{...}}
    {"type":"pong"}
    {"type":"error", "message":"..."}

连接流程:
  ┌─────────────────────────────────────────────────────┐
  │  前端 connectWebSocket()                             │
  │       ↓                                              │
  │  ws://host/ws/progress/{session_id}                  │
  │       ↓                                              │
  │  服务端: 检查 user_sessions 中的 cookie/sesskey       │
  │       ↓                                              │
  │  检查 job_manager.get(sid)                           │
  │  ├─ job 存在 running/pending                         │
  │  │   → 发送当前 visit_progress + replay_progress    │
  │  │   → _stream_job_progress() 持续轮询推送           │
  │  ├─ job 存在 done                                    │
  │  │   → 发送 finished                                 │
  │  └─ 无 job                                          │
  │      → 等待 start_replay 消息                        │
  │      → 收到后创建 job + 启动线程                     │
  └─────────────────────────────────────────────────────┘

_stream_job_progress():
  与 receive_text() 并发运行（asyncio.create_task）
  每 0.5 秒从 job_manager 读取最新进度，有变化时推送给客户端
  客户端 ping/pong 请求可被正常响应
"""

import asyncio
import json
import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models.db_models import PaymentOrder
from app.services.task_job import job_manager
from app.routes.auth import get_user_session
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

active_ws: dict[str, dict[str, WebSocket]] = {}


@router.websocket("/ws/progress/{session_id}")
async def websocket_progress(websocket: WebSocket, session_id: str):
    await websocket.accept()

    user_session = get_user_session(session_id)
    if not user_session:
        await websocket.send_json(
            {"type": "error", "message": "会话已过期，请重新登录"}
        )
        await websocket.close()
        return

    conn_id = str(uuid.uuid4())[:8]
    active_ws.setdefault(session_id, {})[conn_id] = websocket
    stream_task = None

    async def _cancel_stream():
        """取消上一个进度推送协程，避免同一连接上并行运行多个 stream。"""
        nonlocal stream_task
        if stream_task and not stream_task.done():
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
        stream_task = None

    job = job_manager.get(session_id)
    if job and job.status in ("running", "pending"):
        await websocket.send_json(
            {
                "type": "phase",
                "phase": job.phase,
                "message": "任务正在后台执行...",
                "visit_progress": dict(job.visit_progress),
                "replay_progress": dict(job.replay_progress),
                "mark_progress": dict(job.mark_progress),
            }
        )
        await _send_progress(websocket, dict(job.progress))
        stream_task = asyncio.create_task(_stream_job_progress(websocket, session_id))
    elif job and job.status in ("done", "partial", "failed", "stopped"):
        await _send_finished(websocket, job)

    try:

        async def _handle_start(msg: dict):
            nonlocal stream_task

            db = SessionLocal()
            try:
                record = (
                    db.query(PaymentOrder)
                    .filter(
                        PaymentOrder.user_id == session_id,
                        PaymentOrder.paid == True,
                    )
                    .first()
                )
            finally:
                db.close()
            if not record:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "没有已支付的订单，请先支付或使用福利码",
                    }
                )
                return

            tasks = msg.get("tasks", [])
            course_id = msg.get("course_id", settings.DEFAULT_COURSE_ID)

            existing = job_manager.get(session_id)
            if existing and existing.status in ("running", "pending"):
                await _send_progress(websocket, dict(existing.progress))
                await _cancel_stream()
                stream_task = asyncio.create_task(
                    _stream_job_progress(websocket, session_id)
                )
            else:
                job_manager.create(session_id, user_session, tasks, course_id)
                # Job 实际从 visit 阶段开始（先阅读页面再发包），这里如实标注
                # 为 visit，避免前端把“阅读”阶段误判为已完成。
                await websocket.send_json(
                    {
                        "type": "phase",
                        "phase": "visit",
                        "message": f"开始处理 {len(tasks)} 个任务...",
                    }
                )
                job_manager.start(session_id)
                await _cancel_stream()
                stream_task = asyncio.create_task(
                    _stream_job_progress(websocket, session_id)
                )

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "start_replay":
                await _handle_start(msg)
            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error for {session_id}: {e}")
    finally:
        await _cancel_stream()
        conns = active_ws.get(session_id, {})
        conns.pop(conn_id, None)
        if not conns:
            active_ws.pop(session_id, None)


async def _stream_job_progress(websocket: WebSocket, session_id: str):
    last_progress = {}
    while True:
        current = job_manager.get(session_id)
        if not current:
            break
        progress = dict(current.progress)
        if progress != last_progress:
            last_progress = progress
            try:
                await websocket.send_json({"type": "progress", **progress})
            except Exception:
                break
        if current.status in ("done", "partial", "failed", "stopped"):
            await asyncio.sleep(1)
            try:
                await _send_finished(websocket, current)
            except Exception:
                pass
            break
        await asyncio.sleep(0.5)


async def _send_finished(websocket: WebSocket, job):
    await websocket.send_json(
        {
            "type": "finished",
            "status": job.status,
            "phase": job.phase,
            "message": job.progress.get("message", ""),
            "progress": dict(job.progress),
            "visit_progress": dict(job.visit_progress),
            "replay_progress": dict(job.replay_progress),
            "mark_progress": dict(job.mark_progress),
            "result": job.result,
        }
    )


async def _send_progress(websocket: WebSocket, progress: dict):
    try:
        await websocket.send_json({"type": "progress", **progress})
    except Exception:
        pass
