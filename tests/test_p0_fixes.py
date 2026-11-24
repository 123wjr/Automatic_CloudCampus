#!/usr/bin/env python
"""
P0 关键修复回归测试 — 纯逻辑/离线，不需要云校园网络或真实凭据。

覆盖:
  #1 create() 首次为某 session 建 Job 不再 UnboundLocalError
  #4 mark 阶段任务条目元组(title,href)/dict 都能被规范化
     + task_id 提取容忍 id= 后跟其它 query 参数
  #5 re_login 缺少 account/password 时优雅返回原 user_info(不抛 assert)

运行: cd backend && python3 -m pytest ../tests/test_p0_fixes.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import asyncio

from app.services.replayer import _extract_task_id, _task_title_url, re_login
from app.services.task_job import job_manager


def test_create_first_job_no_unbound_local():
    """#1: 某 session 第一次建 Job 时不应抛 UnboundLocalError。"""
    sid = "p0-test-unbound@example.com"
    job_manager._jobs.pop(sid, None)
    job = job_manager.create(sid, {"nickname": "t"}, [], course_id=11881)
    assert job is not None
    assert job.status == "pending"
    job_manager._jobs.pop(sid, None)


def test_extract_task_id_tolerates_trailing_params():
    """#4/#low: id= 后跟 & 或 # 时仍能提取纯 id。"""
    assert _extract_task_id("https://x/view.php?id=625274") == "625274"
    assert _extract_task_id("https://x/view.php?id=625274&forceview=1") == "625274"
    assert _extract_task_id("https://x/view.php?course=2&id=625274") == "625274"
    assert _extract_task_id("https://x/view.php?id=625274#frag") == "625274"


def test_task_title_url_normalizes_tuple_and_dict():
    """#4: query_all 返回 (title, href) 元组，也支持 dict。"""
    assert _task_title_url(("标题A", "https://x?id=1")) == ("标题A", "https://x?id=1")
    assert _task_title_url({"title": "标题B", "url": "https://x?id=2"}) == (
        "标题B",
        "https://x?id=2",
    )
    assert _task_title_url(None) == ("", "")


def test_re_login_graceful_without_credentials():
    """#5: 缺少 account/password 时返回原 dict，不抛异常。"""
    original = {"user_id": "123", "cookie": "c=1"}
    out = asyncio.run(re_login(dict(original)))
    assert out == original


if __name__ == "__main__":
    test_create_first_job_no_unbound_local()
    test_extract_task_id_tolerates_trailing_params()
    test_task_title_url_normalizes_tuple_and_dict()
    test_re_login_graceful_without_credentials()
    print("✅ all P0 offline regression tests passed")
