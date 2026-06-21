"""checkpoint.py 测试 — 检查点恢复系统：保存/加载/清理/持久化"""

import json
import time
import pytest
from unittest.mock import patch
from agent.tools.checkpoint import (
    BrowserCheckpoint, CheckpointManager, get_checkpoint_manager,
)


@pytest.fixture
def mgr(tmp_path):
    """创建临时目录的 CheckpointManager"""
    return CheckpointManager(checkpoint_dir=str(tmp_path))


@pytest.fixture
def cp():
    """创建默认检查点"""
    return BrowserCheckpoint(session_id="sess_001", task="测试任务")


# ── 保存/加载 ──

class TestSaveLoad:
    def test_save_returns_path(self, mgr, cp):
        path = mgr.save(cp)
        assert path.endswith("sess_001.json")

    def test_load_saved_checkpoint(self, mgr, cp):
        mgr.save(cp)
        loaded = mgr.load("sess_001")
        assert loaded is not None
        assert loaded.session_id == "sess_001"
        assert loaded.task == "测试任务"

    def test_load_nonexistent_returns_none(self, mgr):
        assert mgr.load("no_such_session") is None

    def test_load_corrupted_file(self, mgr):
        filepath = mgr.dir / "bad.json"
        filepath.write_text("not json!!!", encoding="utf-8")
        assert mgr.load("bad") is None


# ── 文件持久化 ──

class TestPersistence:
    def test_file_actually_created(self, mgr, cp):
        mgr.save(cp)
        filepath = mgr.dir / "sess_001.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["session_id"] == "sess_001"

    def test_overwrite_on_re_save(self, mgr, cp):
        mgr.save(cp)
        cp.task = "更新任务"
        mgr.save(cp)
        loaded = mgr.load("sess_001")
        assert loaded.task == "更新任务"


# ── 删除/清理 ──

class TestDelete:
    def test_delete_existing(self, mgr, cp):
        mgr.save(cp)
        assert mgr.delete("sess_001") is True
        assert mgr.load("sess_001") is None

    def test_delete_nonexistent(self, mgr):
        assert mgr.delete("no_such") is False


# ── 安全性 ──

class TestSecurity:
    def test_path_traversal_blocked(self, mgr):
        safe_id = mgr._safe_session_id("../../etc/passwd")
        assert "/" not in safe_id
        assert ".." not in safe_id

    def test_special_chars_sanitized(self, mgr):
        safe = mgr._safe_session_id("a@b#c$d%e")
        assert safe == "abcde"


# ── 记录步骤 ──

class TestRecordStep:
    def test_record_step_adds_to_completed(self, mgr, cp):
        mgr.record_step(cp, "click", {"x": 10}, {"code": 0, "msg": "ok"})
        assert len(cp.steps_completed) == 1
        assert cp.steps_completed[0]["tool"] == "click"

    def test_record_step_error_sets_failed(self, mgr, cp):
        mgr.record_step(cp, "navigate", {}, {"code": 500, "msg": "error"})
        assert cp.status == "failed"
        assert cp.error == "error"

    def test_record_step_completed_not_overwritten(self, mgr, cp):
        cp.status = "completed"
        mgr.record_step(cp, "nav", {}, {"code": 500, "msg": "err"})
        assert cp.status == "completed"  # 已完成不回退


# ── 列出会话 ──

class TestListSessions:
    def test_list_empty_dir(self, mgr):
        assert mgr.list_sessions() == []

    def test_list_with_sessions(self, mgr, cp):
        mgr.save(cp)
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "sess_001"

    def test_list_sorted_by_time(self, mgr):
        # 各保存之间加时间间隔，确保时间戳有先后
        for i, sid in enumerate(["s1", "s2", "s3"]):
            mgr.save(BrowserCheckpoint(session_id=sid, task=sid))
            if i < 2:
                time.sleep(1.1)
        sessions = mgr.list_sessions()
        ids = [s["session_id"] for s in sessions]
        assert ids == ["s3", "s2", "s1"]  # 最新在前


# ── 单例 ──

class TestSingleton:
    @patch("agent.tools.checkpoint._checkpoint_manager", None)
    def test_get_checkpoint_manager_singleton(self):
        m1 = get_checkpoint_manager()
        m2 = get_checkpoint_manager()
        assert m1 is m2
