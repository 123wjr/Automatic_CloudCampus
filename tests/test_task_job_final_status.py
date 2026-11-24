import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.task_job import TaskJobManager


def test_progress_logging_keeps_only_failures_and_summary():
    manager = TaskJobManager()
    sid = "minimal-log@example.com"
    job = manager.create(sid, {"nickname": "Log User"}, [], course_id=11881)

    manager._update(
        sid,
        phase="replay",
        title="任务A",
        status="processing",
        message="正在处理",
    )
    manager._update(
        sid,
        phase="replay",
        title="任务A",
        status="success",
        message="处理成功",
    )
    assert job.log_queue == []

    manager._update(
        sid,
        phase="replay",
        title="任务B",
        status="failed",
        message="发包失败",
    )
    manager._queue_log(
        sid,
        title="任务汇总",
        phase="final",
        status="partial",
        message="仍有 1 个未完成",
    )

    assert [entry["status"] for entry in job.log_queue] == ["failed", "partial"]


def test_final_summary_partial_when_verify_has_incomplete_tasks():
    manager = TaskJobManager()

    message, can_retry = manager._summarize_final_result(
        {
            "visit": {"failed": 0},
            "replay": {"failed": 1},
            "mark": {"failed": 0},
            "verify": {"checked": True, "incomplete": 2},
        }
    )

    assert can_retry is True
    assert "发包 1 个失败" in message
    assert "验证仍有 2 个未完成" in message


def test_final_summary_done_when_verify_confirms_complete_despite_stage_failures():
    manager = TaskJobManager()

    message, can_retry = manager._summarize_final_result(
        {
            "visit": {"failed": 0},
            "replay": {"failed": 1},
            "mark": {"failed": 0},
            "verify": {"checked": True, "incomplete": 0},
        }
    )

    assert can_retry is False
    assert message.startswith("所有任务已确认完成")
    assert "发包 1 个失败" in message
