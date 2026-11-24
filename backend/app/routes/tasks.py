import logging

from fastapi import APIRouter, HTTPException, Query

from app.config import DEFAULT_COURSE_ID
from app.models.schemas import TaskItemWithStatus
from app.routes.auth import get_user_session
from app.services.cloudcampus import _get_excluded_patterns, query_all, query_resend
from app.services.replayer import check_packets_exist
from app.services.task_job import job_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _model_dict(item: TaskItemWithStatus) -> dict:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return item.dict()


def _has_paid_order(session_id: str) -> bool:
    try:
        from app.database import SessionLocal
        from app.models.db_models import PaymentOrder

        db = SessionLocal()
        try:
            return (
                db.query(PaymentOrder)
                .filter(
                    PaymentOrder.user_id == session_id,
                    PaymentOrder.paid == True,
                )
                .first()
                is not None
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"paid order check failed for {session_id}: {e}")
        return False


def _mark_paid_orders_fulfilled(session_id: str):
    try:
        from app.database import SessionLocal
        from app.models.db_models import PaymentOrder

        db = SessionLocal()
        try:
            pending = (
                db.query(PaymentOrder)
                .filter(
                    PaymentOrder.user_id == session_id,
                    PaymentOrder.paid == True,
                    PaymentOrder.fulfilled == False,
                )
                .all()
            )
            for order in pending:
                order.fulfilled = True
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to mark fulfilled for {session_id}: {e}")


def _build_pending_task_payload(session: dict, course_id: int) -> dict:
    result = query_resend(session["cookie"], course_id)
    all_result = query_all(session["cookie"], course_id)

    if (
        result.get("error") == "cookie_expired"
        or all_result.get("error") == "cookie_expired"
    ):
        raise HTTPException(status_code=401, detail="Cookie 已过期，请重新登录")

    excluded_patterns = _get_excluded_patterns()

    resend_tasks = []
    excluded_tasks = set()
    for task in result.get("tasks", []):
        if task[1] not in excluded_patterns:
            resend_tasks.append(task)
        else:
            excluded_tasks.add(task)

    all_tasks = []
    for task in all_result.get("tasks", []):
        if task[1] not in excluded_patterns:
            all_tasks.append(task)
        else:
            excluded_tasks.add(task)

    resend_tasks = sorted(set(resend_tasks), key=lambda t: (t[0], t[1]))
    all_tasks = sorted(set(all_tasks), key=lambda t: (t[0], t[1]))
    view_tasks = sorted(set(all_tasks) - set(resend_tasks), key=lambda t: (t[0], t[1]))

    resend_with_status = [
        {"title": task[0], "url": task[1], "has_packet": False}
        for task in resend_tasks
    ]
    resend_with_status = check_packets_exist(resend_with_status)

    incomplete_ready = [task for task in resend_with_status if task["has_packet"]]
    incomplete_skipped = [task for task in resend_with_status if not task["has_packet"]]

    visible_tasks = []
    for index, task in enumerate(incomplete_ready, start=1):
        visible_tasks.append(
            TaskItemWithStatus(
                index=index,
                title=task["title"],
                url=task["url"],
                has_packet=True,
                excluded=False,
                category_id=2,
            )
        )

    for index, task in enumerate(view_tasks, start=len(visible_tasks) + 1):
        visible_tasks.append(
            TaskItemWithStatus(
                index=index,
                title=task[0],
                url=task[1],
                has_packet=False,
                excluded=False,
                category_id=1,
            )
        )

    return {
        "tasks": [_model_dict(task) for task in visible_tasks],
        "total_tasks": len(all_tasks),
        "valid_tasks": len(visible_tasks),
        "skipped_tasks": len(incomplete_skipped),
        "excluded_tasks": len(excluded_tasks),
        "course_id": str(course_id),
    }


@router.get("/progress/{session_id}")
def get_progress(session_id: str, course_id: int = Query(default=DEFAULT_COURSE_ID)):
    # 注意: 本函数体内全部是同步阻塞调用(requests / DB)，没有任何 await。
    # 声明为普通 def 让 FastAPI 在线程池中执行，避免阻塞事件循环。
    session = get_user_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")

    job_status = job_manager.get_status(session_id)

    # 进行中和已确认完成的任务直接返回 job 状态，避免重复查询云校园。
    # partial/failed/stopped 会继续查询当前剩余任务，便于用户重试。
    if job_status and job_status["status"] in ("pending", "running", "paused", "done"):
        return {
            "nickname": session["nickname"],
            "user_id": session["user_id"],
            "tasks": [],
            "total_tasks": 0,
            "valid_tasks": 0,
            "skipped_tasks": 0,
            "excluded_tasks": 0,
            "course_id": str(course_id),
            "job": job_status,
        }

    payload = _build_pending_task_payload(session, course_id)

    # Auto-recover lost job if user paid but no job running.
    if not job_status:
        try:
            if _has_unfulfilled_paid_order(session_id):
                if payload["tasks"]:
                    job_manager.mark_paid(session_id, session, payload["tasks"], course_id)
                    job_status = job_manager.get_status(session_id)
                else:
                    _mark_paid_orders_fulfilled(session_id)
        except Exception as e:
            logger.warning(f"Auto-recovery failed for {session_id}: {e}")

    return {
        "nickname": session["nickname"],
        "user_id": session["user_id"],
        **payload,
        "job": job_status,
    }


def _has_unfulfilled_paid_order(session_id: str) -> bool:
    try:
        from app.database import SessionLocal
        from app.models.db_models import PaymentOrder

        db = SessionLocal()
        try:
            return (
                db.query(PaymentOrder)
                .filter(
                    PaymentOrder.user_id == session_id,
                    PaymentOrder.paid == True,
                    PaymentOrder.fulfilled == False,
                )
                .order_by(PaymentOrder.created_at.desc())
                .first()
                is not None
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"unfulfilled order check failed for {session_id}: {e}")
        return False


@router.post("/retry/{session_id}")
def retry_tasks(session_id: str, course_id: int = Query(default=DEFAULT_COURSE_ID)):
    session = get_user_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")

    existing = job_manager.get(session_id)
    if existing and existing.status in ("pending", "running", "paused"):
        return {
            "started": False,
            "message": "任务正在执行中，请等待本轮结束",
            "job": job_manager.get_status(session_id),
        }

    if not _has_paid_order(session_id):
        raise HTTPException(status_code=400, detail="没有已支付的订单，无法重试")

    payload = _build_pending_task_payload(session, course_id)
    tasks = payload["tasks"]
    if not tasks:
        job_manager.mark_complete(session_id, "重新检查后没有待处理任务，所有任务已确认完成")
        return {
            "started": False,
            "message": "重新检查后没有待处理任务",
            "job": job_manager.get_status(session_id),
            **payload,
        }

    job_manager.create(session_id, session, tasks, course_id)
    job_manager.start(session_id)

    return {
        "started": True,
        "message": f"已开始重试 {len(tasks)} 个任务",
        "job": job_manager.get_status(session_id),
        **payload,
    }
