#!/usr/bin/env python
"""
P2 进度接口回归测试 — 纯逻辑/离线，不需要云校园网络或真实凭据。

覆盖 get_progress 在「用户有真实任务」时的崩溃(此前空任务列表才不触发):
  #1 view_tasks 是 (title, href) 元组集合 → 不能用 t["title"] 索引(TypeError)
  #2 check_packets_exist 返回的 dict 没有 'excluded' 键 → not t["excluded"] (KeyError)
  #3 total_tasks 返回 set → 前端期望数字

通过 monkeypatch 把上游网络/DB 调用替换成真实形状的桩数据，直接调用
get_progress(同步函数)，断言不崩溃且输出类型正确。

运行: cd backend && python3 -m pytest ../tests/test_p2_progress.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import app.routes.tasks as tasks_mod


def _patch_common(monkeypatch, resend, all_tasks, packets_present):
    """resend/all_tasks: list[(title, href)]; packets_present: set[href] 有 .npy 的。"""
    monkeypatch.setattr(
        tasks_mod, "get_user_session",
        lambda sid: {"cookie": "c", "nickname": "n", "user_id": "u"},
    )
    monkeypatch.setattr(tasks_mod.job_manager, "get_status", lambda sid: None)
    monkeypatch.setattr(
        tasks_mod, "query_resend", lambda cookie, cid: {"tasks": resend}
    )
    monkeypatch.setattr(
        tasks_mod, "query_all", lambda cookie, cid: {"tasks": all_tasks}
    )
    monkeypatch.setattr(tasks_mod, "_get_excluded_patterns", lambda: [])

    def _fake_check(items):
        for it in items:
            it["has_packet"] = it["url"] in packets_present
        return items

    monkeypatch.setattr(tasks_mod, "check_packets_exist", _fake_check)


def test_progress_with_view_and_resend_tasks_no_crash(monkeypatch):
    """有 view + resend 任务时不应再 TypeError/KeyError。"""
    resend = [("发包任务A", "https://x/view.php?id=1")]
    # all 含 resend + 一个仅 view 的任务
    all_tasks = [
        ("发包任务A", "https://x/view.php?id=1"),
        ("阅读任务B", "https://x/view.php?id=2"),
    ]
    _patch_common(
        monkeypatch, resend, all_tasks, packets_present={"https://x/view.php?id=1"}
    )

    res = tasks_mod.get_progress("sid@example.com")

    # total_tasks 必须是数字而不是 set
    assert isinstance(res["total_tasks"], int)
    assert res["total_tasks"] == 2
    # 任务列表应同时含可回放(category 2)与仅阅读(category 1)
    cats = sorted(t["category_id"] for t in res["tasks"])
    assert cats == [1, 2]
    # 有包的 resend 任务 has_packet=True
    ready = [t for t in res["tasks"] if t["category_id"] == 2]
    assert ready and ready[0]["has_packet"] is True
    # view 任务标题/URL 正确从元组取出
    view = [t for t in res["tasks"] if t["category_id"] == 1]
    assert view and view[0]["title"] == "阅读任务B"
    assert view[0]["url"] == "https://x/view.php?id=2"


def test_progress_resend_without_packet_goes_to_skipped(monkeypatch):
    """没有 .npy 的 resend 任务计入 skipped，不出现在可执行列表。"""
    resend = [("无包任务", "https://x/view.php?id=9")]
    all_tasks = [("无包任务", "https://x/view.php?id=9")]
    _patch_common(monkeypatch, resend, all_tasks, packets_present=set())

    res = tasks_mod.get_progress("sid@example.com")
    assert res["skipped_tasks"] == 1
    assert res["valid_tasks"] == 0
    assert isinstance(res["total_tasks"], int)


def test_progress_empty_tasks_still_ok(monkeypatch):
    """空任务列表(老路径)仍然正常返回数字类型。"""
    _patch_common(monkeypatch, [], [], packets_present=set())
    res = tasks_mod.get_progress("sid@example.com")
    assert res["total_tasks"] == 0
    assert res["valid_tasks"] == 0
    assert res["tasks"] == []
