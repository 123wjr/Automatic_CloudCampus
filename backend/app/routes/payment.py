"""
支付路由 — 下单、福利码、支付状态查询、通知回调
═══════════════════════════════════════════════════════════
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from app.models.schemas import PaymentRequest
from app.models.db_models import WelfareCode, PaymentOrder
from app.database import SessionLocal
from app.services.payment import (
    create_payment_order,
    check_payment_status,
    handle_payment_notify,
)
from app.services.task_job import job_manager
from app.routes.auth import get_user_session

router = APIRouter(prefix="/api/payment", tags=["payment"])


@router.post("/create")
async def create_order(req: PaymentRequest, request: Request):
    if not req.ready_count or req.ready_count <= 0:
        raise HTTPException(status_code=400, detail="没有可执行的任务")

    session = get_user_session(req.user_id) or {}
    client_ip = req.client_ip or (
        request.client.host if request.client else "127.0.0.1"
    )
    result = create_payment_order(
        user_id=req.user_id,
        task_count=req.task_count,
        ready_count=req.ready_count,
        amount=0.0,
        nickname=req.nickname,
        total_tasks=req.total_tasks,
        client_ip=client_ip,
        tasks=[t.dict() for t in req.tasks],
        user_info=session,
        session_id=req.user_id,
    )
    return result


@router.post("/redeem")
async def redeem_welfare_code(
    code: str = "",
    user_id: str = "",
    nickname: str = "",
    task_count: int = 0,
    ready_count: int = 0,
):
    if not code:
        raise HTTPException(status_code=400, detail="请输入福利码")

    session = get_user_session(user_id) or {}
    password = session.get("password", "")

    db = SessionLocal()
    try:
        wc = db.query(WelfareCode).filter(WelfareCode.code == code).first()
        if not wc:
            raise HTTPException(status_code=404, detail="福利码无效")
        # avoid using Column[bool] directly in boolean context
        if wc.used is True:
            raise HTTPException(status_code=400, detail="该福利码已被使用")
        wc.used = True
        wc.used_by = user_id or nickname
        wc.used_at = datetime.now()  # type: ignore

        order = PaymentOrder(
            order_id=f"welfare_{datetime.now().strftime('%Y%m%d%H%M%S')}_{code}",
            user_id=user_id,
            nickname=nickname or user_id,
            password=password,
            amount=0,
            task_count=task_count,
            ready_count=ready_count,
            paid=True,
            is_welfare=True,
        )
        db.add(order)
        db.commit()
    finally:
        db.close()
    return {
        "success": True,
        "message": "福利码验证成功，请返回页面刷新进度以开始执行任务",
    }


@router.get("/status/{order_id}")
async def get_order_status(order_id: str):
    result = check_payment_status(order_id)
    if not result:
        raise HTTPException(status_code=404, detail="订单不存在")
    return result


@router.get("/orders/{session_id}")
async def get_user_orders(session_id: str):
    """返回该用户的所有历史订单（不含密码），按时间倒序"""
    session = get_user_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")
    db = SessionLocal()
    try:
        orders = (
            db.query(PaymentOrder)
            .filter(PaymentOrder.user_id == session_id)
            .order_by(PaymentOrder.created_at.desc())
            .limit(50)
            .all()
        )
        return {
            "orders": [
                {
                    "order_id": o.order_id,
                    "amount": float(o.amount) if o.amount is not None else 0,
                    "task_count": o.task_count,
                    "ready_count": o.ready_count,
                    "paid": o.paid,
                    "fulfilled": o.fulfilled,
                    "is_welfare": o.is_welfare,
                    "nickname": o.nickname,
                    "created_at": o.created_at.isoformat() if o.created_at else "",
                }
                for o in orders
            ]
        }
    finally:
        try:
            db.close()
        except Exception:
            pass


@router.get("/notify")
async def payment_notify_get(request: Request):
    params = dict(request.query_params)
    ok, msg = handle_payment_notify(params)
    return "success" if ok else msg


@router.post("/notify")
async def payment_notify_post(request: Request):
    from fastapi import Form

    form = await request.form()
    params = dict(form)
    ok, msg = handle_payment_notify(params)
    return "success" if ok else msg
