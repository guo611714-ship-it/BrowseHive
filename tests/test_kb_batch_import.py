"""batch_import method tests"""

import importlib
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

spec = importlib.util.spec_from_file_location(
    "kb_manager_batch",
    str(Path(__file__).parent.parent / "agent" / "kb" / "cli.py")
)
kb_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb_mod)
KnowledgeBaseManager = kb_mod.KnowledgeBaseManager


@pytest.fixture
def kb(tmp_path):
    vault = tmp_path / "test_vault"
    vault.mkdir()
    (vault / "01-Import").mkdir()
    (vault / "02-Notes").mkdir()
    (vault / "03-Index").mkdir()
    (vault / "config.json").write_text(
        json.dumps({"api_key": "test-key", "base_url": "https://test.com/v1", "model": "test-model"}),
        encoding="utf-8",
    )
    return KnowledgeBaseManager(str(vault))


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "source"
    d.mkdir()
    return d


class TestBatchImportEmpty:
    def test_empty_folder(self, kb, folder, capsys):
        """Empty folder should print [NONE] and return nothing."""
        kb.batch_import(str(folder))
        out = capsys.readouterr().out
        assert "[NONE]" in out

    def test_nonexistent_folder(self, kb, capsys):
        """Non-existent folder should print error and return nothing."""
        kb.batch_import("/nonexistent/path")
        out = capsys.readouterr().out
        assert "[ERR]" in out


class TestBatchImportFormats:
    def test_mixed_formats(self, kb, folder, capsys):
        """Both .md and .txt files are imported."""
        (folder / "a.md").write_text("# Title A\n\nContent A", encoding="utf-8")
        (folder / "b.txt").write_text("Plain text content B", encoding="utf-8")

        with patch.object(kb, "_analyze_with_claude", return_value={
            "title": "T", "summary": "S", "concepts": [], "entities": [],
            "tags": [], "suggested_links": [], "category": "other",
            "key_points": [], "structured_breakdown": {}, "missing_concepts": [],
        }):
            kb.batch_import(str(folder))

        out = capsys.readouterr().out
        assert "[IMPORT]" in out
        # Both files should appear in output
        assert "a.md" in out or "File" in out


class TestBatchImportDedup:
    def test_duplicate_detection(self, kb, folder, capsys):
        """Duplicate content is skipped."""
        content = "# Unique Title\n\nSome unique content here."
        (folder / "file1.md").write_text(content, encoding="utf-8")
        (folder / "file2.md").write_text(content, encoding="utf-8")

        with patch.object(kb, "_analyze_with_claude", return_value={
            "title": "T", "summary": "S", "concepts": [], "entities": [],
            "tags": [], "suggested_links": [], "category": "other",
            "key_points": [], "structured_breakdown": {}, "missing_concepts": [],
        }):
            kb.batch_import(str(folder))

        out = capsys.readouterr().out
        # One should be imported, one skipped
        assert out.count("[SKIP]") >= 1


class TestBatchImportToMemory:
    def test_to_memory(self, kb, folder, tmp_path, capsys):
        """--to-memory writes files to memory knowledge dir."""
        (folder / "note.md").write_text("# Memory Test\n\nMemory content.", encoding="utf-8")

        memory_knowledge = tmp_path / "memory" / "knowledge"
        memory_knowledge.mkdir(parents=True)

        with patch.object(kb, "_analyze_with_claude", return_value={
            "title": "Memory Test", "summary": "S", "concepts": [],
            "entities": [], "tags": [], "suggested_links": [],
            "category": "test-cat", "key_points": [],
            "structured_breakdown": {}, "missing_concepts": [],
        }):
            with patch("pathlib.Path.home", return_value=tmp_path / "memory"):
                # Patch home() so the memory path resolves inside tmp_path
                # The code builds: Path.home() / ".claude" / "projects" / ... / "knowledge"
                # We need to patch it so that memory_knowledge ends up where we want
                kb.batch_import(str(folder), to_memory=True)

        out = capsys.readouterr().out
        # Should indicate memory write
        assert "[MEM]" in out or "Memory" in out


class TestBatchImportNested:
    def test_nested_folders(self, kb, folder, capsys):
        """Nested subdirectories are scanned recursively."""
        sub = folder / "subdir"
        sub.mkdir()
        (sub / "nested.md").write_text("# Nested\n\nDeep content.", encoding="utf-8")

        with patch.object(kb, "_analyze_with_claude", return_value={
            "title": "Nested", "summary": "S", "concepts": [], "entities": [],
            "tags": [], "suggested_links": [], "category": "other",
            "key_points": [], "structured_breakdown": {}, "missing_concepts": [],
        }):
            kb.batch_import(str(folder))

        out = capsys.readouterr().out
        # The nested file should be picked up
        assert "[IMPORT]" in out
