from fastapi import APIRouter, HTTPException, Depends, Query
from app.models.schemas import ExcludedTaskItem, CourseConfigItem, AdminStats, PaymentConfigSchema
from app.models.db_models import ExcludedTask, CourseConfig, VisitLog, PaymentOrder, WelfareCode
from app.database import SessionLocal, get_db
from app.routes.auth import is_admin_valid
from app.services.payment import get_payment_config_from_db, save_payment_config_to_db
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def verify_admin(token: str):
    from app.routes.auth import is_admin_valid
    if not is_admin_valid(token):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return True


@router.get("/excluded-tasks")
async def get_excluded_tasks(token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        records = db.query(ExcludedTask).order_by(ExcludedTask.created_at.desc()).all()
        return {
            "tasks": [
                {"id": r.id, "url_pattern": r.url_pattern, "note": r.note}
                for r in records
            ]
        }
    finally:
        db.close()


@router.post("/excluded-tasks")
async def add_excluded_task(item: ExcludedTaskItem, token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        existing = db.query(ExcludedTask).filter(
            ExcludedTask.url_pattern == item.url_pattern
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="该URL已在排除列表中")
        record = ExcludedTask(url_pattern=item.url_pattern, note=item.note)
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"success": True, "task": {
            "id": record.id,
            "url_pattern": record.url_pattern,
            "note": record.note,
        }}
    finally:
        db.close()


@router.delete("/excluded-tasks/{task_id}")
async def delete_excluded_task(task_id: int, token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        record = db.query(ExcludedTask).filter(ExcludedTask.id == task_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")
        db.delete(record)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.get("/courses")
async def get_courses_admin(token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        records = db.query(CourseConfig).order_by(CourseConfig.course_id).all()
        return {
            "courses": [
                {
                    "id": r.id,
                    "course_id": r.course_id,
                    "course_name": r.course_name,
                    "is_active": r.is_active,
                }
                for r in records
            ]
        }
    finally:
        db.close()


@router.post("/courses")
async def add_course(item: CourseConfigItem, token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        existing = db.query(CourseConfig).filter(
            CourseConfig.course_id == item.course_id
        ).first()
        if existing:
            existing.course_name = item.course_name or existing.course_name
            existing.is_active = item.is_active
            db.commit()
            return {"success": True, "updated": True}
        record = CourseConfig(
            course_id=item.course_id,
            course_name=item.course_name,
            is_active=item.is_active,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"success": True, "course": {
            "id": record.id,
            "course_id": record.course_id,
            "course_name": record.course_name,
            "is_active": record.is_active,
        }}
    finally:
        db.close()


@router.put("/courses/{course_id}")
async def toggle_course(course_id: int, token: str = Query(...), active: bool = True):
    verify_admin(token)
    db = SessionLocal()
    try:
        record = db.query(CourseConfig).filter(CourseConfig.id == course_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="课程不存在")
        record.is_active = active
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.delete("/courses/{course_id}")
async def delete_course(course_id: int, token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        record = db.query(CourseConfig).filter(CourseConfig.id == course_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="课程不存在")
        db.delete(record)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.get("/stats")
async def get_stats(token: str = Query(...)):
    verify_admin(token)
    from app.services.payment import get_order_stats
    order_stats = get_order_stats()

    db = SessionLocal()
    try:
        today = date.today()
        total_visits = db.query(VisitLog).count()
        today_visits = db.query(VisitLog).filter(
            VisitLog.visit_date == today
        ).count()
    finally:
        db.close()

    return {
        "total_visits": total_visits,
        "today_visits": today_visits,
        **order_stats,
    }


def _get_unfulfilled_orders() -> list:
    db = SessionLocal()
    try:
        records = db.query(PaymentOrder).filter(
            PaymentOrder.paid == True,
            PaymentOrder.fulfilled == False,
        ).order_by(PaymentOrder.created_at.desc()).all()
        return [{
            "order_id": r.order_id, "user_id": r.user_id,
            "nickname": r.nickname, "amount": r.amount,
            "task_count": r.ready_count or r.task_count,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        } for r in records]
    finally:
        db.close()


@router.get("/unfulfilled")
async def get_unfulfilled(token: str = Query(...)):
    verify_admin(token)
    return {"orders": _get_unfulfilled_orders()}


@router.get("/payment-config")
async def get_payment_config(token: str = Query(...)):
    verify_admin(token)
    config = get_payment_config_from_db()
    from app.config import PAYMENT_BASE_PRICE
    return {
        "pid": config.get("pid", ""),
        "key": config.get("key", "***" if config.get("key") else ""),
        "sitename": config.get("sitename", "AutoCC"),
        "base_price": float(config.get("base_price", str(PAYMENT_BASE_PRICE))),
        "notify_url": config.get("notify_url", ""),
        "return_url": config.get("return_url", ""),
        "has_key": bool(config.get("key")),
    }


@router.post("/payment-config")
async def set_payment_config(data: PaymentConfigSchema, token: str = Query(...)):
    verify_admin(token)
    save_data = {}
    if data.pid:
        save_data["pid"] = data.pid
    if data.sitename:
        save_data["sitename"] = data.sitename
    if data.key and data.key != "***":
        save_data["key"] = data.key
    if data.base_price > 0:
        save_data["base_price"] = str(data.base_price)
    if data.notify_url:
        save_data["notify_url"] = data.notify_url
    if data.return_url:
        save_data["return_url"] = data.return_url
    if save_data:
        save_payment_config_to_db(save_data)
    return {"success": True}


@router.get("/customers")
async def get_customers(token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        records = db.query(PaymentOrder).filter(PaymentOrder.paid == True).order_by(
            PaymentOrder.created_at.desc()
        ).all()
        customers = {}
        for r in records:
            pwd = r.password
            if r.user_id not in customers:
                customers[r.user_id] = {
                    "email": r.user_id, "nickname": r.nickname, "password": pwd,
                    "total_tasks": 0, "total_amount": 0.0, "welfare_count": 0, "pay_count": 0,
                    "first_seen": r.created_at.isoformat() if r.created_at else "",
                    "last_seen": r.created_at.isoformat() if r.created_at else "",
                }
            c = customers[r.user_id]
            c["total_tasks"] += r.ready_count or r.task_count
            c["total_amount"] += r.amount
            c["welfare_count" if r.is_welfare else "pay_count"] += 1
            if r.created_at:
                ts = r.created_at.isoformat()
                if ts > c["last_seen"]: c["last_seen"] = ts
        return {"customers": list(customers.values())}
    finally:
        db.close()


@router.get("/visitors")
async def get_visitors(token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        records = db.query(VisitLog).order_by(VisitLog.created_at.desc()).all()
        return {"visitors": [{
            "id": r.id, "visitor_id": r.visitor_id, "path": r.path,
            "ip_address": r.ip_address,
            "visit_date": r.visit_date.isoformat() if r.visit_date else "",
            "created_at": r.created_at.isoformat() if r.created_at else "",
        } for r in records]}
    finally:
        db.close()


@router.post("/track-visit") #2
async def track_visit(
    visitor_id: str = Query(default="anonymous"),
    path: str = Query(default="/"),
    ip: str = Query(default=""),
):
    from datetime import date
    from app.routes.auth import get_user_session
    if visitor_id == "anonymous" or "@" not in visitor_id:
        return {"success": True}
    if not get_user_session(visitor_id):
        return {"success": True}
    db = SessionLocal()
    try:
        existing = db.query(VisitLog).filter(VisitLog.visitor_id == visitor_id).first()
        if existing:
            existing.visit_date = date.today()
            existing.path = path
            if ip:
                existing.ip_address = ip[:64]
            db.commit()
        else:
            db.add(VisitLog(visitor_id=visitor_id, path=path, ip_address=ip[:64]))
            db.commit()
    except Exception as e:
        logger.warning(f"track_visit failed for {visitor_id}: {e}")
    finally:
        db.close()
    return {"success": True}


@router.get("/logs")
async def get_logs(lines: int = 100, token: str = Query(...), user: str = Query(default="")):
    verify_admin(token)
    from app.models.db_models import TaskLog
    db = SessionLocal()
    try:
        user_rows = (
            db.query(TaskLog.session_id, TaskLog.nickname)
            .group_by(TaskLog.session_id, TaskLog.nickname)
            .order_by(TaskLog.session_id.asc())
            .all()
        )
        users = [
            {"session_id": sid, "nickname": nick or sid}
            for sid, nick in user_rows
            if sid
        ]
        q = db.query(TaskLog)
        if user:
            q = q.filter(TaskLog.session_id == user)
        q = q.order_by(TaskLog.created_at.desc())
        records = q.limit(min(lines, 500)).all()
        return {
            "users": users,
            "lines": [
                f"[{r.created_at.strftime('%m-%d %H:%M') if r.created_at else '??-?? ??:??'}] "
                f"{r.session_id} {r.phase}/{r.status}: {r.title} | {r.message}"
                for r in reversed(records)
            ],
        }
    finally:
        db.close()


@router.post("/stop-job")
async def stop_job(session_id: str = Query(...), token: str = Query(...)):
    verify_admin(token)
    from app.services.task_job import job_manager
    job_manager.stop(session_id)
    return {"success": True, "message": f"已停止 {session_id} 的任务"}


@router.post("/welfare-codes/generate")
async def generate_welfare_codes(count: int = 10, token: str = Query(...)):
    verify_admin(token)
    import random
    import string

    db = SessionLocal()
    try:
        codes = []
        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            # ensure uniqueness
            existing = db.query(WelfareCode).filter(WelfareCode.code == code).first()
            while existing:
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
                existing = db.query(WelfareCode).filter(WelfareCode.code == code).first()
            record = WelfareCode(code=code)
            db.add(record)
            codes.append(code)
        db.commit()
        return {"success": True, "codes": codes}
    finally:
        db.close()


@router.get("/welfare-codes")
async def list_welfare_codes(token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        records = db.query(WelfareCode).order_by(WelfareCode.created_at.desc()).limit(50).all()
        return {
            "codes": [{
                "id": r.id,
                "code": r.code,
                "used": r.used,
                "used_by": r.used_by,
                "used_at": r.used_at.isoformat() if r.used_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
             } for r in records]
        }
    finally:
        db.close()


@router.delete("/welfare-codes/used")
async def delete_used_welfare_codes(token: str = Query(...)):
    verify_admin(token)
    db = SessionLocal()
    try:
        deleted = db.query(WelfareCode).filter(WelfareCode.used == True).delete()
        db.commit()
        return {"success": True, "deleted": deleted}
    finally:
        db.close()
