"""
支付服务 — 易支付(zpayz.cn)集成 + 订单管理
═══════════════════════════════════════════════════════════

支付流程图:
┌──────────┐       ┌──────────────────┐       ┌──────────────┐
│  前端      │       │     后端          │       │   zpayz.cn   │
│ PaymentModal    │   /api/payment/*   │       │  mapi.php    │
└────┬─────┘       └────────┬─────────┘       └──────┬───────┘
     │                      │                        │
     │  POST /create        │                        │
     │  {user_id,tasks,amount}                       │
     │─────────────────────→│                        │
     │                      │  POST mapi.php         │
     │                      │  {pid,type=alipay,     │
     │                      │   out_trade_no,...}    │
     │                      │───────────────────────→│
     │                      │                        │
     │                      │  JSON {code:1,         │
     │                      │   qrcode, payurl}      │
     │                      │←───────────────────────│
     │                      │                        │
     │                      │  生成 QR base64 图片    │
     │  {order_id,          │  (qrcode 库本地生成)    │
     │   qr_base64, amount} │                        │
     │←─────────────────────│                        │
     │                      │                        │
     │  用户扫码支付         │                        │
     │  (支付宝处理)         │                        │
     │                      │                        │
     │  轮询 /status/{id}    │  GET api.php?act=order │
     │─────────────────────→│───────────────────────→│
     │                      │←───── {status:1} ──────│
     │                      │  confirm_payment()     │
     │                      │  → job_manager.mark_paid()
     │                      │  → 自动开始后台任务     │
     │  {paid:true}         │                        │
     │←─────────────────────│                        │
     │                      │                        │
     │  或：zpayz 异步回调   │                        │
     │                      │  POST /notify          │
     │                      │←───────────────────────│
     │                      │  verify_notify_sign()  │
     │                      │  → confirm_payment()   │

金额计算公式:
  amount = base_price × (ready_count / total_tasks)
  其中 base_price 默认 20 元，管理员可调
  金额仅由服务端计算，不接受客户端传入值

订单状态:
  DB: PaymentOrder(paid, fulfilled, is_welfare, context_json)
  - context_json: JSON 序列化 {tasks, user_info, session_id, course_id}
    确保服务器重启后仍可恢复订单执行
  - 免费/welfare: paid=True, amount=0
  - 已付未做: paid=True, fulfilled=False  ← 恢复机制检测
  - 已完成: paid=True, fulfilled=True

认证方式:
  zpayz.cn MD5 签名: sorted(params) + key → MD5 → hexdigest
"""

import hashlib
import hmac
import json as _json
import logging
import requests
import uuid
import io
import base64
from datetime import datetime
from urllib.parse import urlparse

import qrcode

logger = logging.getLogger(__name__)

try:
    from app.database import SessionLocal as _SessionLocal
    from app.models.db_models import PaymentOrder, PaymentConfig

    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

from app.config import settings

_pending_orders: dict[str, dict] = {}

ZPAY_API_URL = settings.ZPAY_API_URL
ZPAY_ORDER_QUERY_URL = settings.ZPAY_ORDER_QUERY_URL


def _get_db_session():
    if _DB_AVAILABLE:
        return _SessionLocal()
    raise RuntimeError("Database not available")


def _get_config(key: str, default: str = "") -> str:
    if not _DB_AVAILABLE:
        return default
    db = _get_db_session()
    try:
        record = db.query(PaymentConfig).filter(PaymentConfig.config_key == key).first()
        if record:
            return str(record.config_value)
    except Exception:
        logger.warning(f"Failed to read config key={key}")
    finally:
        db.close()
    return default


def _get_pid() -> str:
    return _get_config("pid") or settings.PAYMENT_PID


def _get_key() -> str:
    return _get_config("key") or settings.PAYMENT_KEY


def _get_base_price() -> float:
    val = _get_config("base_price", "")
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return settings.PAYMENT_BASE_PRICE


def _get_notify_url() -> str:
    saved = _get_config("notify_url", "")
    if saved:
        return saved
    return settings.PAYMENT_NOTIFY_PATH


def _calculate_amount(base_price: float, ready_count: int, total_tasks: int) -> float:
    if total_tasks <= 0 or ready_count <= 0:
        return 0.0
    raw = base_price * ready_count / total_tasks
    return round(max(raw, 0.01), 2)


def _save_order_to_db(
    order_id,
    user_id,
    nickname,
    amount,
    task_count,
    ready_count,
    trade_no="",
    password="",
    is_welfare=False,
    context_json="",
):
    if not _DB_AVAILABLE:
        return
    db = _get_db_session()
    try:
        existing = (
            db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
        )
        if existing:
            if trade_no and not existing.trade_no:
                existing.trade_no = trade_no
            if context_json and not existing.context_json:
                existing.context_json = context_json
            db.commit()
            return
        record = PaymentOrder(
            order_id=order_id,
            user_id=user_id,
            nickname=nickname,
            password=password,
            amount=amount,
            task_count=task_count,
            ready_count=ready_count,
            is_welfare=is_welfare,
            trade_no=trade_no,
            context_json=context_json,
        )
        db.add(record)
        db.commit()
    except Exception as e:
        logger.warning(f"_save_order_to_db failed: {e}")
    finally:
        db.close()


def _mark_order_paid_in_db(order_id, trade_no=""):
    if not _DB_AVAILABLE:
        return
    db = _get_db_session()
    try:
        record = (
            db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
        )
        if record:
            record.paid = True
            if trade_no:
                record.trade_no = trade_no
            db.commit()
    finally:
        db.close()


def _generate_qr_base64(data: str) -> str:
    if not data:
        return ""
    buf = io.BytesIO()
    img = qrcode.make(data, box_size=8, border=2)
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def create_payment_order(
    user_id: str,
    task_count: int,
    ready_count: int = 0,
    amount: float = 0.0,
    nickname: str = "",
    total_tasks: int = 0,
    client_ip: str = "",
    tasks: list | None = None,
    user_info: dict | None = None,
    session_id: str = "",
    course_id: int | None = None,
) -> dict:
    order_id = datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4().hex)[:8]
    base_price = _get_base_price()

    amount = _calculate_amount(base_price, ready_count, max(total_tasks, ready_count))

    course_id = course_id or settings.DEFAULT_COURSE_ID

    context_data = {  # TODO: fix related query or something like that
        "tasks": tasks or [],
        "session_id": session_id,
        "course_id": course_id,
    }
    context_json = _json.dumps(context_data, ensure_ascii=False)

    order = {
        "order_id": order_id,
        "user_id": user_id,
        "nickname": nickname,
        "amount": amount,
        "task_count": task_count,
        "ready_count": ready_count,
        "total_tasks": total_tasks,
        "paid": False,
        "created_at": datetime.now().isoformat(),
        "tasks": tasks or [],
        "user_info": user_info or {},
        "session_id": session_id,
        "course_id": course_id,
    }
    _pending_orders[order_id] = order

    try:
        pwd = (user_info or {}).get("password", "")
        _save_order_to_db(
            order_id,
            user_id,
            nickname,
            amount,
            task_count,
            ready_count,
            password=pwd,
            context_json=context_json,
        )
    except Exception as e:
        logger.warning(f"Failed to save order to DB: {e}")

    pid = _get_pid()
    key = _get_key()
    notify_url = _get_notify_url()

    if not pid or not key:
        return {
            "order_id": order_id,
            "pay_url": "",
            "qr_base64": "",
            "amount": amount,
            "base_price": base_price,
            "configured": False,
        }

    product_name = f"AutoCC任务执行 x{ready_count}"

    params = {
        "pid": pid,
        "type": "alipay",
        "out_trade_no": order_id,
        "notify_url": notify_url,
        "name": product_name,
        "money": str(amount),
        "clientip": client_ip or "127.0.0.1",
        "device": "pc",
    }

    data_keys = sorted(params.keys())
    sign_str = "&".join(f"{k}={params[k]}" for k in data_keys) + key
    sign = hashlib.md5(sign_str.encode("UTF-8")).hexdigest()

    params["sign"] = sign
    params["sign_type"] = "MD5"

    try:
        resp = requests.post(ZPAY_API_URL, data=params, timeout=15)
        data = resp.json()

        if data.get("code") == 1:
            pay_url = data.get("payurl", "")

            zpay_trade_no = data.get("trade_no", "")
            if zpay_trade_no:
                try:
                    _save_order_to_db(
                        order_id,
                        user_id,
                        nickname,
                        amount,
                        task_count,
                        ready_count,
                        trade_no=zpay_trade_no,
                    )
                    _pending_orders[order_id]["trade_no"] = zpay_trade_no
                except Exception as e:
                    logger.warning(f"Failed to update trade_no: {e}")

            return {
                "order_id": order_id,
                "pay_url": pay_url,
                "qr_base64": _generate_qr_base64(pay_url),
                "amount": amount,
                "base_price": base_price,
                "configured": True,
            }
        else:
            return {
                "order_id": order_id,
                "pay_url": "",
                "qr_base64": "",
                "amount": amount,
                "base_price": base_price,
                "configured": True,
                "error": data.get("msg", "支付下单失败"),
            }
    except Exception as e:
        logger.error(f"zpay create order failed: {e}")
        return {
            "order_id": order_id,
            "pay_url": "",
            "qr_base64": "",
            "amount": amount,
            "base_price": base_price,
            "configured": True,
            "error": str(e),
        }


def _lookup_order_db(order_id: str) -> dict | None:
    if not _DB_AVAILABLE:
        return None
    db = _get_db_session()
    try:
        record = (
            db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
        )
        if record:
            context = {
                "tasks": [],
                "user_info": {},
                "session_id": record.user_id,
                "course_id": settings.DEFAULT_COURSE_ID,
            }
            if record.context_json:
                try:
                    ctx = _json.loads(record.context_json)
                    context.update(ctx)
                except (_json.JSONDecodeError, TypeError):
                    pass
            return {
                "order_id": record.order_id,
                "user_id": record.user_id,
                "nickname": record.nickname,
                "amount": record.amount,
                "task_count": record.task_count,
                "ready_count": record.ready_count,
                "paid": record.paid,
                "tasks": context.get("tasks", []),
                "user_info": context.get("user_info", {}),
                "session_id": context.get("session_id", record.user_id),
                "course_id": context.get("course_id", settings.DEFAULT_COURSE_ID),
            }
    finally:
        db.close()
    return None


def confirm_payment(order_id: str, trade_no: str = "") -> bool:
    order = _pending_orders.get(order_id)
    if not order:
        order = _lookup_order_db(order_id)
        if order:
            _pending_orders[order_id] = order
    if not order:
        logger.warning(f"confirm_payment: order {order_id} not found")
        return False
    order["paid"] = True
    try:
        _mark_order_paid_in_db(order_id, trade_no)
    except Exception as e:
        logger.error(f"Failed to mark order paid in DB: {e}")
        return False

    tasks = order.get("tasks", [])
    user_info = order.get("user_info", {})
    session_id = order.get("session_id", "")
    if tasks and session_id:
        from app.services.task_job import job_manager

        job_manager.mark_paid(
            session_id,
            user_info,
            tasks,
            order.get("course_id", settings.DEFAULT_COURSE_ID),
        )
        logger.info(f"Job started for {session_id} with {len(tasks)} tasks")
    else:
        logger.warning(
            f"confirm_payment: no tasks or session_id for {order_id} "
            f"(tasks={len(tasks)}, sid={session_id})"
        )
    return True


def check_payment_status(order_id: str) -> dict | None:
    order = _pending_orders.get(order_id)
    if not order:
        order = _lookup_order_db(order_id)
    if not order:
        return None

    paid = order.get("paid", False)

    if not paid:
        pid = _get_pid()
        key = _get_key()
        if pid and key:
            try:
                url = f"{ZPAY_ORDER_QUERY_URL}&pid={pid}&key={key}&out_trade_no={order_id}"
                resp = requests.get(url, timeout=10)
                data = resp.json()
                if data.get("status") == 1 or data.get("code") == 1:
                    confirm_payment(order_id, data.get("trade_no", ""))
                    paid = True
            except Exception as e:
                logger.warning(f"check_payment_status query failed: {e}")

    return {
        "order_id": order["order_id"],
        "status": "paid" if paid else "pending",
        "paid": paid,
    }


def verify_notify_sign(params: dict) -> bool:
    key = _get_key()
    if not key:
        return False
    sign_param = params.get("sign", "")
    data_keys = sorted([k for k in params if k not in ("sign", "sign_type")])
    sign_str = "&".join(f"{k}={params[k]}" for k in data_keys) + key
    expected = hashlib.md5(sign_str.encode("UTF-8")).hexdigest()
    # 常量时间比较，避免签名校验的时序侧信道
    return hmac.compare_digest(expected, sign_param)


def handle_payment_notify(params: dict) -> tuple[bool, str]:
    out_trade_no = params.get("out_trade_no", "")
    trade_status = params.get("trade_status", "")
    trade_no = params.get("trade_no", "")

    if not verify_notify_sign(params):
        return False, "签名验证失败"

    if trade_status in ("TRADE_SUCCESS", "SUCCESS"):
        confirm_payment(out_trade_no, trade_no)
        return True, out_trade_no

    return False, f"未处理的交易状态: {trade_status}"


def get_order_stats():
    if not _DB_AVAILABLE:
        return {
            "total_orders": 0,
            "today_orders": 0,
            "total_revenue": 0.0,
            "recent_orders": [],
        }
    from sqlalchemy import func

    db = _get_db_session()
    try:
        today = datetime.now().date()
        total_orders = db.query(PaymentOrder).count()
        today_orders = (
            db.query(PaymentOrder)
            .filter(func.date(PaymentOrder.created_at) == today)
            .count()
        )
        total_revenue = (
            db.query(func.coalesce(func.sum(PaymentOrder.amount), 0))
            .filter(PaymentOrder.paid == True)
            .scalar()
            or 0
        )

        unfulfilled = (
            db.query(PaymentOrder)
            .filter(
                PaymentOrder.paid == True,
                PaymentOrder.fulfilled == False,
            )
            .count()
        )

        recent = (
            db.query(PaymentOrder)
            .order_by(PaymentOrder.created_at.desc())
            .limit(20)
            .all()
        )

        recent_data = [
            {
                "order_id": r.order_id,
                "nickname": r.nickname,
                "user_id": r.user_id,
                "amount": r.amount,
                "task_count": r.task_count,
                "ready_count": r.ready_count,
                "paid": r.paid,
                "fulfilled": r.fulfilled,
                "is_welfare": r.is_welfare,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in recent
        ]

        return {
            "total_orders": total_orders,
            "today_orders": today_orders,
            "total_revenue": round(total_revenue, 2),
            "unfulfilled": unfulfilled,
            "recent_orders": recent_data,
        }
    finally:
        db.close()


def get_payment_config_from_db() -> dict:
    if not _DB_AVAILABLE:
        return {}
    db = _get_db_session()
    try:
        records = db.query(PaymentConfig).all()
        result = {}
        for r in records:
            result[r.config_key] = r.config_value
        return result
    finally:
        db.close()


def save_payment_config_to_db(data: dict) -> None:
    if not _DB_AVAILABLE:
        return
    db = _get_db_session()
    try:
        for key, value in data.items():
            if value is None:
                continue
            record = (
                db.query(PaymentConfig).filter(PaymentConfig.config_key == key).first()
            )
            if record:
                record.config_value = str(value)
            else:
                db.add(PaymentConfig(config_key=key, config_value=str(value)))
        db.commit()
    finally:
        db.close()
