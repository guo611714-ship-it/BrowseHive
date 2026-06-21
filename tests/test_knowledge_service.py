"""Tests for agent.knowledge_service"""

import json
import pytest
from pathlib import Path
from agent.knowledge_service import KnowledgeService, _to_kebab


# ---- _to_kebab unit tests ----

class TestToKebab:
    def test_spaces(self):
        result = _to_kebab("hello world")
        assert result.startswith("hello-world-")
        assert len(result) == len("hello-world-") + 6  # hash is 6 chars

    def test_underscores(self):
        result = _to_kebab("some_name")
        assert result.startswith("some-name-")

    def test_chinese(self):
        result = _to_kebab("任务 状态")
        assert result.startswith("任务-状态-")

    def test_empty(self):
        result = _to_kebab("!!!")
        assert result.startswith("untitled-")

    def test_deterministic(self):
        assert _to_kebab("test") == _to_kebab("test")

    def test_different_inputs_different_hashes(self):
        a = _to_kebab("hello world")
        b = _to_kebab("hello-world")
        assert a != b  # different inputs → different hashes


# ---- read_memory ----

class TestReadMemory:
    def test_empty_memory(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        result = svc.read_memory()
        assert result == []

    def test_reads_all_md_files(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        # Create MEMORY.md index
        (mem / "MEMORY.md").write_text(
            "# Memory Index\n\n- [Alpha](alpha.md) — first\n- [Beta](beta.md) — second\n",
            encoding="utf-8",
        )
        (mem / "alpha.md").write_text("hello alpha", encoding="utf-8")
        (mem / "beta.md").write_text("hello beta", encoding="utf-8")
        svc = KnowledgeService(tmp_path)
        result = svc.read_memory()
        assert len(result) == 2
        names = [r["name"] for r in result]
        assert "Alpha" in names
        assert "Beta" in names

    def test_keyword_filter(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "MEMORY.md").write_text(
            "# Memory Index\n\n- [Python](a.md) — lang\n- [Rust](b.md) — lang\n",
            encoding="utf-8",
        )
        (mem / "a.md").write_text("python is great", encoding="utf-8")
        (mem / "b.md").write_text("rust is fast", encoding="utf-8")
        svc = KnowledgeService(tmp_path)
        result = svc.read_memory(keyword="python")
        assert len(result) == 1
        assert result[0]["name"] == "Python"

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        svc = KnowledgeService(tmp_path / "nope")
        result = svc.read_memory()
        assert result == []


# ---- write_memory ----

class TestWriteMemory:
    def test_returns_true(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        result = svc.write_memory("My Note", "some content")
        assert result is True

    def test_creates_file(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        svc.write_memory("My Note", "some content")
        files = list((tmp_path / "memory").glob("*.md"))
        assert len(files) >= 1
        assert any("my-note-" in f.name for f in files)

    def test_content_written(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        svc.write_memory("note", "body text")
        files = list((tmp_path / "memory").glob("note-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "body text" in content

    def test_updates_index(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        svc.write_memory("note", "x")
        idx_file = tmp_path / "memory" / "MEMORY.md"
        assert idx_file.exists()
        content = idx_file.read_text(encoding="utf-8")
        assert "[note]" in content

    def test_chinese_name(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        result = svc.write_memory("学习笔记", "content")
        assert result is True
        files = list((tmp_path / "memory").glob("*.md"))
        assert any("学习笔记" in f.name or "学习" in f.name for f in files)


# ---- search_kb ----

class TestSearchKB:
    def test_kb_not_available_returns_empty(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        result = svc.search_kb("anything")
        assert result == []

    def test_kb_no_index_returns_empty(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        svc = KnowledgeService(tmp_path)
        result = svc.search_kb("test")
        assert result == []


# ---- get_context_for_task ----

class TestGetContextForTask:
    def test_empty_when_nothing_matches(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        result = svc.get_context_for_task("xyz")
        assert result == ""

    def test_returns_context_from_memory(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "MEMORY.md").write_text(
            "# Memory Index\n\n- [Deploy](deploy.md) — deploy notes\n",
            encoding="utf-8",
        )
        (mem / "deploy.md").write_text("deploy steps here", encoding="utf-8")
        svc = KnowledgeService(tmp_path)
        result = svc.get_context_for_task("deploy")
        assert "deploy steps here" in result


# ---- save_task_result ----

class TestSaveTaskResult:
    def test_creates_experience_file(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        result = svc.save_task_result("task_001", "done successfully")
        assert result is True

    def test_file_is_created(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        svc.save_task_result("task_001", "done successfully")
        files = list((tmp_path / "memory").glob("*.md"))
        assert len(files) >= 1
        assert any("task-result" in f.name for f in files)

    def test_file_contains_result(self, tmp_path):
        svc = KnowledgeService(tmp_path)
        svc.save_task_result("t1", "result text")
        files = list((tmp_path / "memory").glob("task-result*.md"))
        content = files[0].read_text(encoding="utf-8")
        assert "result text" in content
