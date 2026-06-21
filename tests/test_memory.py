"""memory模块测试"""

import json
import time
from pathlib import Path

import pytest
from agent.memory import MemoryStore


@pytest.fixture
def mem(tmp_path):
    """创建临时MemoryStore"""
    return MemoryStore(tmp_path / "memory")


class TestMemoryStoreInit:
    def test_creates_directory(self, tmp_path):
        d = tmp_path / "new_mem"
        MemoryStore(d)
        assert d.exists()

    def test_creates_initial_files(self, mem):
        assert mem.long_term_file.exists()
        assert mem.user_file.exists()
        assert mem.history_file.exists()
        assert mem.tokens_file.exists()

    def test_long_term_memory_has_content(self, mem):
        content = mem.get_long_term_memory()
        assert len(content) > 0

    def test_user_prefs_has_content(self, mem):
        content = mem.get_user_prefs()
        assert len(content) > 0


class TestHistory:
    def test_append_and_read(self, mem):
        mem.append_history({"role": "user", "content": "hello"})
        history = mem.get_recent_history()
        assert len(history) == 1
        assert history[0]["role"] == "user"

    def test_append_multiple(self, mem):
        for i in range(5):
            mem.append_history({"role": "user", "content": f"msg{i}"})
        history = mem.get_recent_history()
        assert len(history) == 5

    def test_get_recent_history_limit(self, mem):
        for i in range(10):
            mem.append_history({"role": "user", "content": f"msg{i}"})
        recent = mem.get_recent_history(limit=3)
        assert len(recent) == 3
        assert recent[0]["content"] == "msg7"

    def test_clear_history(self, mem):
        mem.append_history({"role": "user", "content": "test"})
        mem.clear_history()
        assert mem.get_recent_history() == []

    def test_empty_history(self, mem):
        assert mem.get_recent_history() == []


class TestLongTermMemory:
    def test_update_and_read(self, mem):
        mem.update_long_term_memory("# New Memory\nUpdated content.")
        content = mem.get_long_term_memory()
        assert "Updated content." in content

    def test_version_snapshot_created(self, mem):
        mem.update_long_term_memory("v1")
        mem.update_long_term_memory("v2")
        versions_dir = mem.memory_dir / "versions" / "long_term"
        snapshots = list(versions_dir.glob("*.snapshot.md"))
        assert len(snapshots) >= 1


class TestUserPrefs:
    def test_update_and_read(self, mem):
        mem.update_user_prefs("# User\nPrefers dark mode.")
        content = mem.get_user_prefs()
        assert "dark mode" in content

    def test_version_snapshot(self, mem):
        mem.update_user_prefs("v1")
        mem.update_user_prefs("v2")
        versions_dir = mem.memory_dir / "versions" / "user"
        snapshots = list(versions_dir.glob("*.snapshot.md"))
        assert len(snapshots) >= 1


class TestDailyMemory:
    def test_append_daily(self, mem):
        mem.append_daily_memory("Did something useful.")
        today = time.strftime("%Y-%m-%d")
        daily_file = mem.memory_dir / f"{today}.md"
        assert daily_file.exists()
        content = daily_file.read_text(encoding="utf-8")
        assert "Did something useful." in content

    def test_append_multiple_same_day(self, mem):
        mem.append_daily_memory("First entry.")
        mem.append_daily_memory("Second entry.")
        today = time.strftime("%Y-%m-%d")
        daily_file = mem.memory_dir / f"{today}.md"
        content = daily_file.read_text(encoding="utf-8")
        assert "First entry." in content
        assert "Second entry." in content


class TestTokenUsage:
    def test_record_and_stats(self, mem):
        mem.record_token_usage(
            provider="openai", model="gpt-4",
            input_tokens=100, output_tokens=50,
        )
        stats = mem.get_token_stats()
        assert stats["total_input"] == 100
        assert stats["total_output"] == 50
        assert "openai/gpt-4" in stats["by_model"]

    def test_by_model_aggregation(self, mem):
        mem.record_token_usage("openai", "gpt-4", 100, 50)
        mem.record_token_usage("openai", "gpt-4", 200, 80)
        stats = mem.get_token_stats()
        model = stats["by_model"]["openai/gpt-4"]
        assert model["input"] == 300
        assert model["output"] == 130
        assert model["count"] == 2

    def test_by_usage_type(self, mem):
        mem.record_token_usage("openai", "gpt-4", 100, 50, usage_type="subagent")
        stats = mem.get_token_stats()
        assert "subagent" in stats["by_usage_type"]

    def test_empty_tokens(self, mem):
        stats = mem.get_token_stats()
        assert stats["total_input"] == 0
        assert stats["total_output"] == 0
        assert stats["by_model"] == {}

    def test_tokens_file_missing(self, mem):
        """tokens.jsonl不存在时返回空字典"""
        mem.tokens_file.unlink()
        stats = mem.get_token_stats()
        assert stats == {}

    def test_cache_fields(self, mem):
        mem.record_token_usage("openai", "gpt-4", 100, 50,
                               cache_read=30, cache_create=20)
        stats = mem.get_token_stats()
        assert stats["total_cache_read"] == 30
        assert stats["total_cache_create"] == 20


class TestCompressLock:
    def test_try_compress_lock_success(self, mem):
        assert mem.try_compress_lock() is True
        mem.release_compress_lock()

    def test_try_compress_lock_already_held(self, mem):
        mem.try_compress_lock()
        assert mem.try_compress_lock() is False
        mem.release_compress_lock()

    def test_compress_context_manager(self, mem):
        with mem.compress_context():
            pass
