#!/usr/bin/env python
"""并发模拟测试 — 两个 job 同时执行

⚠️ 联网集成脚本，需要真实云校园凭据，不在 CI 中运行。
凭据从环境变量读取，缺失则跳过，严禁硬编码:

  TEST_ACCOUNT=you@example.com TEST_PASSWORD=... python tests/test_concurrent.py
"""
import sys, os, json, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.task_job import job_manager
from app.services.cloudcampus import login as cloud_login

# 从环境变量读取，缺失则跳过（不得把账号密码写进源码）
ACCOUNT = os.environ.get("TEST_ACCOUNT", "")
PASSWORD = os.environ.get("TEST_PASSWORD", "")

if not ACCOUNT or not PASSWORD:
    print(
        "⏭  跳过并发测试: 未设置 TEST_ACCOUNT / TEST_PASSWORD 环境变量。\n"
        "   这是联网集成脚本，需要真实云校园凭据，凭据不得硬编码。"
    )
    sys.exit(0)

print("═══ 登录获取 session ═══")
info = cloud_login(ACCOUNT, PASSWORD)
if not info or not info.get("user_id"):
    print("登录失败:", info)
    sys.exit(1)
print(f"✅ {info['nickname']} uid={info['user_id']} cookie_len={len(info['cookie'])} sesskey={info['sesskey']}")
print()

results = {}
errors = {}

# Only test with 2 tasks each for speed
test_tasks = [
    {"title": "Task 1", "url": "https://www.cloudcampus.com.cn/mod/h5pactivity/view.php?id=625274"},
    {"title": "Task 2", "url": "https://www.cloudcampus.com.cn/mod/h5pactivity/view.php?id=625276"},
]


def run_user(label, sid):
    print(f"[{label}] 创建 job...", flush=True)
    info_copy = dict(info)
    job_manager.create(sid, info_copy, test_tasks, 11881)

    job_manager.start(sid)

    for _ in range(60):
        time.sleep(1)
        j = job_manager.get(sid)
        if j and j.status in ("done", "failed"):
            res = j.result or {}
            results[label] = {
                "status": j.status,
                "result": res,
            }
            print(f"[{label}] ✅ 完成 | replay:{res.get('success',0)}/{res.get('total',0)} "
                  f"visit:{res.get('visited',0)}/{res.get('total',0)}",
                  flush=True)
            return
    errors[label] = "超时"
    print(f"[{label}] ❌ {errors[label]}", flush=True)


print("═══ 并发执行: 两个 session 同时运行 ═══")
t1 = threading.Thread(target=run_user, args=("S1", "concurrent_test_1@qq.com"), daemon=True)
t2 = threading.Thread(target=run_user, args=("S2", "concurrent_test_2@qq.com"), daemon=True)

start = time.time()
t1.start()
t2.start()
t1.join(timeout=120)
t2.join(timeout=120)
elapsed = time.time() - start

print(f"\n═══ 结果 (耗时 {elapsed:.0f}s) ═══")
all_ok = True
for label in ("S1", "S2"):
    r = results.get(label)
    if r:
        res = r["result"]
        print(f"[{label}] {r['status']} | replay:{res.get('success',0)}/{res.get('total',0)} "
              f"visit:{res.get('visited',0)}/{res.get('total',0)}")
        if r["status"] == "failed" or res.get("success", 0) < len(test_tasks):
            all_ok = False
    else:
        print(f"[{label}] ❌ {errors.get(label, 'unknown')}")
        all_ok = False

print(f"\n{'✅ 并发正常' if all_ok else '❌ 并发有问题'}")

# Cleanup
try:
    from app.database import SessionLocal
    from app.models.db_models import TaskLog
    db = SessionLocal()
    cnt = db.query(TaskLog).delete()
    db.commit()
    db.close()
    print(f"🧹 已清理 {cnt} 条测试日志")
except Exception:
    pass

sys.exit(0 if all_ok else 1)
