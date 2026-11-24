import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.models.db_models import PaymentOrder, TaskLog, WelfareCode


def test_welfare_order_records_task_counts(monkeypatch):
    import app.routes.payment as payment_route

    sid = "welfare-count@example.com"
    code = "COUNTTEST"

    db = payment_route.SessionLocal()
    try:
        db.query(PaymentOrder).filter(PaymentOrder.user_id == sid).delete()
        db.query(WelfareCode).filter(WelfareCode.code == code).delete()
        db.add(WelfareCode(code=code))
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        payment_route,
        "get_user_session",
        lambda user_id: {"password": "pw"} if user_id == sid else None,
    )

    import asyncio

    asyncio.run(
        payment_route.redeem_welfare_code(
            code=code,
            user_id=sid,
            nickname="Tester",
            task_count=8,
            ready_count=5,
        )
    )

    db = payment_route.SessionLocal()
    try:
        order = db.query(PaymentOrder).filter(PaymentOrder.user_id == sid).first()
        assert order is not None
        assert order.task_count == 8
        assert order.ready_count == 5
        assert order.is_welfare is True
    finally:
        db.query(PaymentOrder).filter(PaymentOrder.user_id == sid).delete()
        db.query(WelfareCode).filter(WelfareCode.code == code).delete()
        db.commit()
        db.close()


def test_admin_logs_can_filter_by_user(monkeypatch):
    import app.routes.admin as admin_route

    db = admin_route.SessionLocal()
    try:
        db.query(TaskLog).filter(TaskLog.session_id.in_(["u1@example.com", "u2@example.com"])).delete()
        db.add_all(
            [
                TaskLog(
                    session_id="u1@example.com",
                    nickname="U1",
                    title="任务汇总",
                    phase="final",
                    status="partial",
                    message="u1-msg",
                    created_at=datetime.now(),
                ),
                TaskLog(
                    session_id="u2@example.com",
                    nickname="U2",
                    title="任务汇总",
                    phase="final",
                    status="done",
                    message="u2-msg",
                    created_at=datetime.now(),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(admin_route, "verify_admin", lambda token: True)

    import asyncio

    result = asyncio.run(admin_route.get_logs(lines=10, token="ok", user="u1@example.com"))
    assert any(u["session_id"] == "u1@example.com" for u in result["users"])
    assert len(result["lines"]) == 1
    assert "u1-msg" in result["lines"][0]
    assert "u2-msg" not in result["lines"][0]

    db = admin_route.SessionLocal()
    try:
        db.query(TaskLog).filter(TaskLog.session_id.in_(["u1@example.com", "u2@example.com"])).delete()
        db.commit()
    finally:
        db.close()
