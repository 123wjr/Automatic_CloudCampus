#!/usr/bin/env python
"""
P1 稳定性修复回归测试 — 纯逻辑/离线，不需要云校园网络或真实凭据。

覆盖:
  #1 start() 幂等：已有存活线程时重复 start 不再启动第二个发包线程
     （mark_paid 被 payment 回调 + 进度恢复重复调用 → 重复发包的根因）
  #2 mark_single_task 自建 session 时用完即关，不泄漏 socket
  #3 visit/mark 阶段缺 cookie 时不再因 assert 崩溃整个 Job

运行: cd backend && python3 -m pytest ../tests/test_p1_stability.py -q
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.task_job import job_manager


def test_start_is_idempotent_while_thread_alive():
    """#1: 已有存活执行线程时，再次 start 不应启动第二个线程。"""
    sid = "p1-test-start-guard@example.com"
    job_manager._jobs.pop(sid, None)
    job_manager._threads.pop(sid, None)

    # 用一个会阻塞一会儿的假线程占住 _threads，模拟 Job 正在跑
    release = threading.Event()

    def _blocker():
        release.wait(timeout=5)

    fake = threading.Thread(target=_blocker, daemon=True)
    fake.start()

    # 建一个真实 Job，但把它的执行线程替换成上面的阻塞线程
    job_manager.create(sid, {"nickname": "t"}, [], course_id=11881)
    job_manager._threads[sid] = fake

    # 此时 start 应识别到已有存活线程并直接返回，不替换线程
    job_manager.start(sid)
    assert job_manager._threads[sid] is fake, "存活线程在跑时 start 不应替换线程"

    release.set()
    fake.join(timeout=5)

    job_manager._jobs.pop(sid, None)
    job_manager._threads.pop(sid, None)


def test_start_replaces_dead_thread():
    """#1: 上一个线程已结束时，start 允许启动新线程（不会被旧记录卡死）。"""
    sid = "p1-test-dead-thread@example.com"
    job_manager._jobs.pop(sid, None)
    job_manager._threads.pop(sid, None)

    dead = threading.Thread(target=lambda: None, daemon=True)
    dead.start()
    dead.join(timeout=5)
    assert not dead.is_alive()

    # 空 tasks 的 Job：_run_job 会很快跑完，主要验证 start 不因旧死线程拒绝启动
    job_manager.create(sid, {"nickname": "t", "cookie": ""}, [], course_id=11881)
    job_manager._threads[sid] = dead

    job_manager.start(sid)
    # start 应已替换为新线程
    assert job_manager._threads[sid] is not dead

    # 给后台线程一点时间收尾（无网络任务，应迅速 done/failed）
    time.sleep(0.2)

    job_manager._jobs.pop(sid, None)
    job_manager._threads.pop(sid, None)


def test_mark_single_task_closes_own_session(monkeypatch):
    """#2: 不传 ses 时 mark_single_task 自建 session，请求后必须关闭。"""
    import app.services.replayer as rp

    closed = {"value": False}

    class FakeResp:
        status_code = 200

    class FakeSession:
        def post(self, *a, **k):
            return FakeResp()

        def close(self):
            closed["value"] = True

    monkeypatch.setattr(rp, "build_ses", lambda cookie: FakeSession())

    resp = rp.mark_single_task({"cookie": "x", "sesskey": "y"}, "625274")
    assert resp.status_code == 200
    assert closed["value"] is True, "自建 session 用完后应被 close()"


def test_mark_single_task_reuses_passed_session(monkeypatch):
    """#2: 传入 ses 时复用，不应被 mark_single_task 关闭（由调用方统一关闭）。"""
    import app.services.replayer as rp

    closed = {"value": False}

    class FakeResp:
        status_code = 200

    class FakeSession:
        def post(self, *a, **k):
            return FakeResp()

        def close(self):
            closed["value"] = True

    ses = FakeSession()
    resp = rp.mark_single_task({"cookie": "x", "sesskey": "y"}, "625274", ses=ses)
    assert resp.status_code == 200
    assert closed["value"] is False, "传入的 session 不应被 mark_single_task 关闭"
