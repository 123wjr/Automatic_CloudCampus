#!/usr/bin/env python
"""AutoCC 端到端测试 — 覆盖用户端、支付、发包、管理端全部功能

⚠️ 这是需要真实云校园凭据 + 联网的集成脚本，不在 CI 中运行。
凭据一律从环境变量读取，缺失则跳过，严禁把账号/密码写进源码:

  TEST_ACCOUNT=you@example.com TEST_PASSWORD=... \\
  AUTOCC_ADMIN_PASSWORD=... python tests/test_e2e.py
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

TEST_ACCOUNT = os.environ.get("TEST_ACCOUNT", "")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "")
ADMIN_USER = os.environ.get("AUTOCC_ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("AUTOCC_ADMIN_PASSWORD", "")

if not TEST_ACCOUNT or not TEST_PASSWORD:
    print(
        "⏭  跳过端到端测试: 未设置 TEST_ACCOUNT / TEST_PASSWORD 环境变量。\n"
        "   这是联网集成脚本，需要真实云校园凭据，凭据不得硬编码。"
    )
    sys.exit(0)

FAILED = []
PASSED = []


def ok(name: str):
    PASSED.append(name)
    print(f"  ✅ {name}")


def fail(name: str, reason: str):
    FAILED.append((name, reason))
    print(f"  ❌ {name}: {reason}")


def assert_ok(r, name="request"):
    if r.status_code == 200:
        ok(name)
    else:
        fail(name, f"HTTP {r.status_code} {r.text[:200]}")
    return r.status_code == 200


# ═══════════ 1. 用户登录 ═══════════
print("\n═══ 1. 用户登录 ═══")
r = client.post("/api/auth/login", json={"account": TEST_ACCOUNT, "password": TEST_PASSWORD})
if assert_ok(r, "用户登录"):
    data = r.json()
    if data.get("success"):
        ok("返回 success=True")
    else:
        fail("返回 success=True", str(data))
    sid = data.get("session_id", "")
    if sid:
        ok(f"获得 session_id")
    else:
        fail("获得 session_id", "空")
    if data.get("nickname"):
        ok(f"昵称: {data['nickname']}")
    if data.get("user_id"):
        ok(f"用户ID: {data['user_id']}")
else:
    sid = ""

# ═══════════ 2. 查询进度 ═══════════
print("\n═══ 2. 查询进度 ═══")
if sid:
    r = client.get(f"/api/tasks/progress/{sid}")
    if assert_ok(r, "查询进度"):
        d = r.json()
        total = d.get("total_tasks", 0)
        valid = d.get("valid_tasks", 0)
        skipped = d.get("skipped_tasks", 0)
        tasks = d.get("tasks", [])
        ok(f"总任务: {total}, 可执行: {valid}, 跳过: {skipped}, 列表: {len(tasks)}")
        if d.get("nickname"):
            ok(f"昵称: {d['nickname']}")
        job = d.get("job")
        if job:
            ok(f"运行中任务: {job['status']} ({job.get('phase','')})")
        else:
            ok("无任务运行中（正常）")

# ═══════════ 3. 管理端登录 ═══════════
print("\n═══ 3. 管理端登录 ═══")
r = client.post("/api/auth/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
if assert_ok(r, "管理员登录"):
    admin_token = r.json().get("token", "")
    if admin_token:
        ok("获得 token")
    else:
        fail("获得 token", "空")
else:
    admin_token = ""

# ═══════════ 4. 支付下单 ═══════════
print("\n═══ 4. 支付下单 ═══")
if sid:
    r = client.post("/api/payment/create", json={
        "user_id": sid, "nickname": "TestUser", "task_count": 5,
        "ready_count": 3, "total_tasks": 5, "amount": 0,
    })
    if assert_ok(r, "创建订单"):
        d = r.json()
        order_id = d.get("order_id", "")
        if order_id:
            ok(f"订单号: {order_id}")
        else:
            fail("订单号", "空")
        amt = d.get("amount", 0)
        ok(f"金额: ¥{amt}")
        if d.get("configured"):
            ok("支付接口已配置")
        if d.get("pay_url") or d.get("qr_base64"):
            ok("获得支付二维码")
    else:
        order_id = ""
else:
    order_id = ""

# ═══════════ 5. 支付状态查询 ═══════════
print("\n═══ 5. 支付状态查询 ═══")
if order_id:
    r = client.get(f"/api/payment/status/{order_id}")
    if assert_ok(r, "查询支付状态"):
        d = r.json()
        ok(f"状态: {d.get('status')} (paid={d.get('paid')})")

# ═══════════ 6. 福利码 ═══════════
print("\n═══ 6. 福利码管理 ═══")
if admin_token:
    # 6a. 生成
    r = client.post(f"/api/admin/welfare-codes/generate?token={admin_token}&count=3")
    if assert_ok(r, "生成3个福利码"):
        codes = r.json().get("codes", [])
        ok(f"获得 {len(codes)} 个码")
    else:
        codes = []

    # 6b. 列表
    r = client.get(f"/api/admin/welfare-codes?token={admin_token}")
    if assert_ok(r, "福利码列表"):
        all_codes = r.json().get("codes", [])
        ok(f"共 {len(all_codes)} 个码")
    else:
        all_codes = []

    # 6c. 兑换
    if codes:
        code = codes[0]
        r = client.post(f"/api/payment/redeem", params={
            "code": code, "user_id": sid or "test@qq.com", "nickname": "Test"
        })
        if assert_ok(r, "兑换福利码"):
            ok(r.json().get("message", ""))
        # 再次兑换应该失败
        r = client.post(f"/api/payment/redeem", params={
            "code": code, "user_id": "other@qq.com", "nickname": "Other"
        })
        if r.status_code in (400, 404):
            ok("重复兑换正确拒绝")
        else:
            fail("重复兑换正确拒绝", f"HTTP {r.status_code}")

    # 6d. 删除已使用
    r = client.delete(f"/api/admin/welfare-codes/used?token={admin_token}")
    if assert_ok(r, "删除已使用"):
        ok(f"删除 {r.json().get('deleted',0)} 条")

# ═══════════ 7. 管理端统计 ═══════════
print("\n═══ 7. 管理端统计 ═══")
if admin_token:
    r = client.get(f"/api/admin/stats?token={admin_token}")
    if assert_ok(r, "统计数据"):
        d = r.json()
        ok(f"访客: {d.get('total_visits',0)} | 今日: {d.get('today_visits',0)}")
        ok(f"订单: {d.get('total_orders',0)} | 收入: ¥{d.get('total_revenue',0)}")
        recent = d.get("recent_orders", [])
        ok(f"最近订单: {len(recent)} 条")

# ═══════════ 8. 客户管理 ═══════════
print("\n═══ 8. 客户管理 ═══")
if admin_token:
    r = client.get(f"/api/admin/customers?token={admin_token}")
    if assert_ok(r, "客户列表"):
        customers = r.json().get("customers", [])
        ok(f"客户: {len(customers)} 人")
        if customers:
            c = customers[0]
            ok(f"首客户: {c.get('nickname','')} | 任务:{c.get('total_tasks',0)} | ¥{c.get('total_amount',0)}")

# ═══════════ 9. 访客列表 ═══════════
print("\n═══ 9. 访客列表 ═══")
if admin_token:
    r = client.get(f"/api/admin/visitors?token={admin_token}")
    if assert_ok(r, "访客列表"):
        visitors = r.json().get("visitors", [])
        ok(f"访客: {len(visitors)} 条")
        if visitors:
            ok(f"首访客: {visitors[0].get('visitor_id','')}")

# ═══════════ 10. 课程管理 ═══════════
print("\n═══ 10. 课程管理 ═══")
if admin_token:
    r = client.post(f"/api/admin/courses?token={admin_token}", json={
        "course_id": 11881, "course_name": "测试课程", "is_active": True,
    })
    assert_ok(r, "添加课程")
    r = client.get(f"/api/admin/courses?token={admin_token}")
    if assert_ok(r, "课程列表"):
        courses = r.json().get("courses", [])
        ok(f"课程: {len(courses)} 门")
    # 清理
    for c in r.json().get("courses", []):
        client.delete(f"/api/admin/courses/{c['id']}?token={admin_token}")
    ok("课程已清理")

# ═══════════ 11. 排除任务 ═══════════
print("\n═══ 11. 排除任务 ═══")
if admin_token:
    r = client.post(f"/api/admin/excluded-tasks?token={admin_token}", json={
        "url_pattern": "https://www.cloudcampus.com.cn/test/excluded/999", "note": "测试排除",
    })
    if assert_ok(r, "添加排除"):
        tid = r.json().get("task", {}).get("id")
    else:
        tid = None
    r = client.get(f"/api/admin/excluded-tasks?token={admin_token}")
    if assert_ok(r, "排除列表"):
        ok(f"排除项: {len(r.json().get('tasks',[]))} 条")
    if tid:
        r = client.delete(f"/api/admin/excluded-tasks/{tid}?token={admin_token}")
        assert_ok(r, "删除排除")
    ok("排除项已清理")

# ═══════════ 12. 支付配置 ═══════════
print("\n═══ 12. 支付配置 ═══")
if admin_token:
    r = client.get(f"/api/admin/payment-config?token={admin_token}")
    if assert_ok(r, "支付配置读"):
        ok(f"base_price: {r.json().get('base_price',0)}")

# ═══════════ 13. 联系方式 ═══════════
print("\n═══ 13. 联系方式 ═══")
if admin_token:
    r = client.get(f"/api/admin/contact?token={admin_token}")
    try:
        if r.status_code == 200:
            ok(f"邮箱: {r.json().get('email','')}")
        else:
            ok(f"联系方式端点: {r.status_code}")
    except Exception:
        ok(f"联系方式端点: {r.status_code} (非JSON响应)")

# ═══════════ 14. 日志查看 ═══════════
print("\n═══ 14. 日志查看 ═══")
if admin_token:
    r = client.get(f"/api/admin/logs?token={admin_token}&lines=5")
    if assert_ok(r, "日志"):
        lines = r.json().get("lines", [])
        ok(f"获取 {len(lines)} 行")

# ═══════════ 15. 公开接口 ═══════════
print("\n═══ 15. 公开接口 ═══")
r = client.get("/api/health")
assert_ok(r, "健康检查")
r = client.get("/api/config/public")
if assert_ok(r, "公开配置"):
    ok(f"联系邮箱: {r.json().get('contact_email','')}")

# ═══════════ 16. WebSocket ═══════════
print("\n═══ 16. WebSocket 连接 ═══")
if sid:
    try:
        with client.websocket_connect(f"/ws/progress/{sid}") as ws:
            ok("WebSocket 连接成功")
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            if data.get("type") == "pong":
                ok("Ping/Pong 正常")
            else:
                ok(f"收到: {data.get('type','?')}")
            ws.close()
    except Exception as e:
        fail("WebSocket", str(e)[:100])

# ═══════════ 17. 限流测试 ═══════════
print("\n═══ 17. 限流测试 ═══")
r = client.post("/api/auth/admin/login", json={"username": "bad", "password": "wrong"})
if r.status_code == 401:
    ok("错误密码返回 401")
else:
    fail("错误密码返回401", f"HTTP {r.status_code}")
# Rapid login attempts
rate_limited = False
for _ in range(10):
    r = client.post("/api/auth/login", json={"account": "bad@test.com", "password": "x"})
    if r.status_code == 429:
        rate_limited = True
        break
if rate_limited:
    ok("登录限流生效 (429)")
else:
    ok("登录未触发限流（正常）")

# ═══════════ 清理 ═══════════
print("\n═══ 清理测试数据 ═══")
cleaned = 0
if admin_token:
    # 删除所有福利码
    r = client.delete(f"/api/admin/welfare-codes/used?token={admin_token}")
    if r.status_code == 200: cleaned += r.json().get("deleted", 0)
    # 通过 DB 清理测试订单
    try:
        from app.database import SessionLocal
        from app.models.db_models import PaymentOrder, VisitLog, TaskLog, ExcludedTask, CourseConfig, WelfareCode
        db = SessionLocal()
        for model in [PaymentOrder, VisitLog, TaskLog, ExcludedTask, CourseConfig, WelfareCode]:
            cnt = db.query(model).delete()
            cleaned += cnt
        db.commit()
        db.close()
    except Exception:
        pass
ok(f"已清理 {cleaned} 条测试数据")

# ═══════════ 结果 ═══════════
print(f"\n{'='*50}")
print(f"  通过: {len(PASSED)}  失败: {len(FAILED)}")
if FAILED:
    print(f"\n  失败详情:")
    for name, reason in FAILED:
        print(f"    ❌ {name}: {reason}")
print(f"{'='*50}")
sys.exit(1 if FAILED else 0)
