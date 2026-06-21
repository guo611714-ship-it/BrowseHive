#!/usr/bin/env python3
"""Comprehensive tests for kb-manager.py CLI (27 tests)."""
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

KB_MANAGER = Path(__file__).resolve().parent.parent / "kb-manager.py"


def _make_vault(tmp):
    """Copy kb-manager.py into tmp and create standard dirs + config."""
    shutil.copy2(str(KB_MANAGER), str(tmp / "kb-manager.py"))
    for d in ["01-Import", "02-Notes", "03-Index"]:
        (tmp / d).mkdir(parents=True, exist_ok=True)
    (tmp / "config.json").write_text(
        json.dumps({"api_key": "fake-key", "model": "test-model", "max_tokens": 256}),
        encoding="utf-8",
    )
    return tmp


def _run(tmp, *args, input_text=None, check=False):
    """Run kb-manager.py inside tmp vault, return subprocess.CompletedProcess."""
    cmd = [sys.executable, str(tmp / "kb-manager.py"), *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp),
        input=input_text,
        timeout=30,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"CLI failed: {result.stderr}\nstdout: {result.stdout}")
    return result


def _json_out(result):
    """Parse JSON from stdout, tolerating trailing newlines."""
    return json.loads(result.stdout.strip())


# --- Helpers for tests that need mocking (can't mock across subprocess) ---


def _exec_kb(tmp, argv_list, ns_overrides=None):
    """Load kb-manager.py via exec, apply ns_overrides, run main(), return stdout capture.

    ns_overrides: dict of name->value to inject/override in the module namespace.
    argv_list: sys.argv to set before calling main().
    Returns (stdout_text, stderr_text, return_code).
    """
    code = (tmp / "kb-manager.py").read_text(encoding="utf-8")
    code = code.replace('if __name__ == "__main__":', "if False:")
    ns = {"__name__": "__test__", "__file__": str(tmp / "kb-manager.py")}
    exec(compile(code, str(tmp / "kb-manager.py"), "exec"), ns)

    if ns_overrides:
        ns.update(ns_overrides)

    # Capture output via a StringIO-compatible replacement for out()
    import io
    capture = io.StringIO()

    def _capture_out(obj):
        capture.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

    ns["out"] = _capture_out

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    old_argv = sys.argv[:]
    sys.argv = argv_list
    rc = 0
    try:
        ns["main"]()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    except Exception:
        import traceback
        sys.stderr.write(traceback.format_exc())
        rc = 1
    finally:
        stdout_val = capture.getvalue()
        stderr_val = sys.stderr.getvalue()
        sys.stderr = old_stderr
        sys.argv = old_argv
    return stdout_val, stderr_val, rc


# ═══════════════════════════════════════════════════════════════════════
# 1. init (2 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestInit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_init_"))
        self.vault = _make_vault(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_creates_directories(self):
        for d in ["01-Import", "02-Notes", "03-Index"]:
            shutil.rmtree(self.vault / d, ignore_errors=True)
        (self.vault / "config.json").unlink(missing_ok=True)

        result = _run(self.vault, "init", check=True)
        data = _json_out(result)
        self.assertEqual(data["status"], "ok")
        self.assertTrue((self.vault / "01-Import").is_dir())
        self.assertTrue((self.vault / "02-Notes").is_dir())
        self.assertTrue((self.vault / "03-Index").is_dir())
        self.assertTrue((self.vault / "03-Index" / "documents.json").exists())

    def test_init_idempotent(self):
        result1 = _run(self.vault, "init", check=True)
        result2 = _run(self.vault, "init", check=True)
        data1 = _json_out(result1)
        data2 = _json_out(result2)
        self.assertEqual(data1["status"], "ok")
        self.assertEqual(data2["status"], "ok")
        # Verify directory structure is identical after second init
        for d in ["01-Import", "02-Notes", "03-Index"]:
            self.assertTrue((self.vault / d).is_dir())
            count1 = len(list((self.vault / d).iterdir()))
            _run(self.vault, "init", check=True)
            count2 = len(list((self.vault / d).iterdir()))
            self.assertEqual(count1, count2, f"File count changed in {d}")
        # Verify documents.json is preserved
        docs_json = self.vault / "03-Index" / "documents.json"
        if docs_json.exists():
            before = docs_json.read_text(encoding="utf-8")
            _run(self.vault, "init", check=True)
            after = docs_json.read_text(encoding="utf-8")
            self.assertEqual(before, after, "documents.json should be preserved across init calls")


# ═══════════════════════════════════════════════════════════════════════
# 2. list (2 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestList(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_list_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_empty_vault(self):
        result = _run(self.vault, "list", check=True)
        data = _json_out(result)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["documents"], [])

    def test_list_with_documents(self):
        docs = [{"path": "01-Import/test.md", "title": "Test Doc", "category": "ai"}]
        idx_dir = self.vault / "03-Index"
        idx_dir.mkdir(parents=True, exist_ok=True)
        (idx_dir / "documents.json").write_text(
            json.dumps({"documents": docs}, ensure_ascii=False), encoding="utf-8"
        )
        result = _run(self.vault, "list", check=True)
        data = _json_out(result)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["documents"][0]["title"], "Test Doc")


# ═══════════════════════════════════════════════════════════════════════
# 3. analyze-text (4 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestAnalyzeText(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_analyze_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_analyze_text_basic(self):
        mock_resp = {
            "concepts": ["concept-a", "concept-b"],
            "entities": ["entity-1"],
            "tags": ["tag-x"],
            "summary": "Mock summary text.",
            "key_points": ["point-1", "point-2"],
        }
        stdout, stderr, rc = _exec_kb(
            self.vault,
            ["kb-manager.py", "analyze-text", "--text", "Some sample content about AI", "--title", "TestTitle"],
            ns_overrides={"call_nvidia": lambda prompt, config: json.dumps(mock_resp)},
        )
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        data = json.loads(stdout.strip())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["title"], "TestTitle")
        self.assertGreater(data["concepts_count"], 0)

    def test_analyze_text_saves_file(self):
        mock_resp = {
            "concepts": ["c1"], "entities": ["e1"],
            "tags": ["t1"], "summary": "sum", "key_points": ["p1"],
        }
        stdout, stderr, rc = _exec_kb(
            self.vault,
            ["kb-manager.py", "analyze-text", "--text", "Content to save", "--title", "SaveTest"],
            ns_overrides={"call_nvidia": lambda prompt, config: json.dumps(mock_resp)},
        )
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        data = json.loads(stdout.strip())
        self.assertEqual(data["status"], "ok")
        md_files = list((self.vault / "01-Import").glob("*.md"))
        self.assertTrue(len(md_files) >= 1)

    def test_analyze_text_updates_index(self):
        mock_resp = {
            "concepts": ["c1"], "entities": ["e1"],
            "tags": ["t1"], "summary": "sum", "key_points": ["p1"],
        }
        _exec_kb(
            self.vault,
            ["kb-manager.py", "analyze-text", "--text", "Indexed content", "--title", "IdxTest"],
            ns_overrides={"call_nvidia": lambda prompt, config: json.dumps(mock_resp)},
        )
        idx_path = self.vault / "03-Index" / "documents.json"
        self.assertTrue(idx_path.exists())
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["documents"]), 1)
        self.assertEqual(data["documents"][0]["title"], "IdxTest")

    def test_analyze_text_api_failure(self):
        # Mock call_nvidia to return None (simulating API failure / no key)
        stdout, stderr, rc = _exec_kb(
            self.vault,
            ["kb-manager.py", "analyze-text", "--text", "Some text", "--title", "FailTest"],
            ns_overrides={"call_nvidia": lambda prompt, config: None},
        )
        data = json.loads(stdout.strip())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["concepts_count"], 0)
        # Verify fallback file was written
        imports_dir = self.vault / "01-Import"
        files = list(imports_dir.glob("*.md"))
        self.assertGreater(len(files), 0, "Fallback file should be written on API failure")


# ═══════════════════════════════════════════════════════════════════════
# 4. unified-search (3 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestUnifiedSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_search_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unified_search_finds_results(self):
        (self.vault / "01-Import" / "quantum.md").write_text(
            "---\ntitle: Quantum Computing\n---\n\nQuantum computing is revolutionary.\n",
            encoding="utf-8",
        )
        result = _run(self.vault, "unified-search", "quantum")
        data = _json_out(result)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) >= 1)
        self.assertIn("quantum", data[0]["snippet"].lower())

    def test_unified_search_no_results(self):
        result = _run(self.vault, "unified-search", "xyznonexistentterm")
        data = _json_out(result)
        self.assertEqual(data, [])

    def test_unified_search_vault_source_field(self):
        """Verify vault results have source='vault' and correct metadata."""
        (self.vault / "01-Import" / "test.md").write_text(
            "---\ntitle: TestDoc\n---\n\nThe alpha topic.\n", encoding="utf-8"
        )
        result = _run(self.vault, "unified-search", "alpha")
        data = _json_out(result)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) >= 1)
        self.assertEqual(data[0]["source"], "vault")
        self.assertIn("title", data[0])
        self.assertIn("snippet", data[0])
        self.assertIn("score", data[0])


# ═══════════════════════════════════════════════════════════════════════
# 5. sync-memory-to-kb (3 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestSyncMemoryToKb(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_sync2kb_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)
        self.mem = self.tmp / "fake_memory"
        self.mem.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_new_files(self):
        (self.mem / "ai").mkdir(parents=True, exist_ok=True)
        (self.mem / "ai" / "doc1.md").write_text(
            "# Doc1\n\nContent about neural nets.\n", encoding="utf-8"
        )
        result = _run(
            self.vault, "sync-memory-to-kb", "--memory-dir", str(self.mem), check=True
        )
        data = _json_out(result)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["imported"], 1)
        self.assertEqual(data["skipped"], 0)

    def test_sync_dedup(self):
        content = "# Dedup\n\nSame content here.\n"
        (self.mem / "general").mkdir(parents=True, exist_ok=True)
        (self.mem / "general" / "doc.md").write_text(content, encoding="utf-8")
        # Put same content in vault so hash matches
        (self.vault / "01-Import" / "dedup.md").write_text(content, encoding="utf-8")
        result = _run(
            self.vault, "sync-memory-to-kb", "--memory-dir", str(self.mem), check=True
        )
        data = _json_out(result)
        self.assertEqual(data["imported"], 0)
        self.assertGreaterEqual(data["skipped"], 1)

    def test_sync_empty_memory(self):
        result = _run(
            self.vault, "sync-memory-to-kb", "--memory-dir", str(self.mem), check=True
        )
        data = _json_out(result)
        self.assertEqual(data["imported"], 0)


# ═══════════════════════════════════════════════════════════════════════
# 6. sync-kb-to-memory (2 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestSyncKbToMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_sync2mem_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)
        self.mem = self.tmp / "fake_memory"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_kb_to_memory_new(self):
        (self.vault / "01-Import" / "syncme.md").write_text(
            "---\ntitle: SyncMe\ncategory: ai\n---\n\nSync this to memory.\n",
            encoding="utf-8",
        )
        result = _run(
            self.vault, "sync-kb-to-memory", "--memory-dir", str(self.mem), check=True
        )
        data = _json_out(result)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["synced"], 1)
        ai_dir = self.mem / "ai"
        self.assertTrue(ai_dir.exists())
        md_files = list(ai_dir.glob("*.md"))
        self.assertTrue(len(md_files) >= 1)

    def test_sync_kb_to_memory_dedup(self):
        content = "---\ntitle: Dup\ncategory: general\n---\n\nDedup content.\n"
        (self.vault / "01-Import" / "dup.md").write_text(content, encoding="utf-8")
        _run(self.vault, "sync-kb-to-memory", "--memory-dir", str(self.mem), check=True)
        result = _run(
            self.vault, "sync-kb-to-memory", "--memory-dir", str(self.mem), check=True
        )
        data = _json_out(result)
        self.assertEqual(data["synced"], 0)
        self.assertGreaterEqual(data["skipped"], 1)


# ═══════════════════════════════════════════════════════════════════════
# 7. rebuild-index (2 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestRebuildIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_rebuild_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)
        self.mem = self.tmp / "fake_memory"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rebuild_index_creates_file(self):
        (self.mem / "ai").mkdir(parents=True, exist_ok=True)
        (self.mem / "ai" / "topic.md").write_text(
            "# Topic\n\nAI topic.\n", encoding="utf-8"
        )
        result = _run(
            self.vault, "rebuild-index", "--memory-dir", str(self.mem), check=True
        )
        data = _json_out(result)
        self.assertEqual(data["status"], "ok")
        self.assertTrue((self.mem / "INDEX.md").exists())

    def test_rebuild_index_content(self):
        (self.mem / "tools").mkdir(parents=True, exist_ok=True)
        (self.mem / "tools" / "tool1.md").write_text(
            "# Tool1\n\nTool doc.\n", encoding="utf-8"
        )
        (self.mem / "tools" / "tool2.md").write_text(
            "# Tool2\n\nAnother tool.\n", encoding="utf-8"
        )
        _run(self.vault, "rebuild-index", "--memory-dir", str(self.mem), check=True)
        index_content = (self.mem / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("## tools", index_content)
        self.assertIn("tool1", index_content)
        self.assertIn("tool2", index_content)


# ═══════════════════════════════════════════════════════════════════════
# 8. backup (2 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_backup_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backup_git_commit(self):
        """Verify backup calls git add -A then git commit."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "add" in cmd:
                return subprocess.CompletedProcess(cmd, returncode=0)
            elif "commit" in cmd:
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="ok", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0)

        # Build a mock subprocess module with real CompletedProcess
        mock_sub = type(sys)("subprocess")
        mock_sub.run = fake_run
        mock_sub.CompletedProcess = subprocess.CompletedProcess
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired

        stdout, stderr, rc = _exec_kb(
            self.vault,
            ["kb-manager.py", "backup"],
            ns_overrides={"subprocess": mock_sub},
        )
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        data = json.loads(stdout.strip())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(calls), 2)
        self.assertIn("-A", calls[0])
        self.assertIn("commit", calls[1])

    def test_backup_no_git(self):
        """Verify graceful error when git is not found."""
        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("git not found")

        mock_sub = type(sys)("subprocess")
        mock_sub.run = fake_run
        mock_sub.CompletedProcess = subprocess.CompletedProcess
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired

        stdout, stderr, rc = _exec_kb(
            self.vault,
            ["kb-manager.py", "backup"],
            ns_overrides={"subprocess": mock_sub},
        )
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        data = json.loads(stdout.strip())
        self.assertEqual(data["status"], "error")
        self.assertIn("git not found", data["message"])


# ═══════════════════════════════════════════════════════════════════════
# 9. batch-import (4 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestBatchImport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_batch_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)
        self.src = self.tmp / "source_docs"
        self.src.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_batch_import_basic(self):
        (self.src / "file1.md").write_text(
            "Document one about Python programming.\n", encoding="utf-8"
        )
        (self.src / "file2.txt").write_text(
            "Plain text document two.\n", encoding="utf-8"
        )
        result = _run(self.vault, "batch-import", str(self.src), check=True)
        data = _json_out(result)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["imported"], 2)
        self.assertEqual(data["skipped"], 0)

    def test_batch_import_dedup(self):
        content = "Same content for dedup test.\n"
        (self.src / "file1.md").write_text(content, encoding="utf-8")
        # First import
        _run(self.vault, "batch-import", str(self.src), check=True)
        # Copy the frontmatter-wrapped file from 01-Import back to src
        # (batch-import wraps content with frontmatter, so re-import needs identical bytes)
        imported_file = list((self.vault / "01-Import").glob("*.md"))[0]
        shutil.copy2(str(imported_file), str(self.src / "file1.md"))
        # Second import -- should skip because content hash matches
        result = _run(self.vault, "batch-import", str(self.src), check=True)
        data = _json_out(result)
        self.assertEqual(data["imported"], 0)
        self.assertGreaterEqual(data["skipped"], 1)

    def test_batch_import_to_memory(self):
        mem = self.tmp / "target_memory"
        (self.src / "memfile.md").write_text(
            "Memory bound content.\n", encoding="utf-8"
        )
        result = _run(
            self.vault,
            "batch-import", str(self.src),
            "--to-memory", "--memory-dir", str(mem),
            check=True,
        )
        data = _json_out(result)
        self.assertEqual(data["status"], "ok")
        self.assertGreater(data["imported"], 0)
        self.assertTrue((mem / "INDEX.md").exists())

    def test_batch_import_category(self):
        (self.src / "aiml.md").write_text(
            "Machine learning model training.\n", encoding="utf-8"
        )
        result = _run(
            self.vault,
            "batch-import", str(self.src),
            "--category", "ai",
            check=True,
        )
        data = _json_out(result)
        self.assertEqual(data["status"], "ok")
        docs_path = self.vault / "03-Index" / "documents.json"
        docs = json.loads(docs_path.read_text(encoding="utf-8"))["documents"]
        self.assertTrue(any(d.get("category") == "ai" for d in docs))


# ═══════════════════════════════════════════════════════════════════════
# 10. Edge cases (3 tests)
# ═══════════════════════════════════════════════════════════════════════
class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb_edge_"))
        self.vault = _make_vault(self.tmp)
        _run(self.vault, "init", check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_utf8_content(self):
        chinese_text = "这是一个中文文档，包含Unicode字符：emoji测试、日文假名测试。"
        (self.vault / "01-Import" / "chinese.md").write_text(
            f"---\ntitle: Chinese\n---\n\n{chinese_text}\n", encoding="utf-8"
        )
        result = _run(self.vault, "unified-search", "中文")
        data = _json_out(result)
        self.assertTrue(len(data) >= 1)
        self.assertIn("中文", data[0]["snippet"])

    def test_missing_config(self):
        (self.vault / "config.json").unlink(missing_ok=True)
        result = _run(
            self.vault, "analyze-text",
            "--text", "Some text", "--title", "NoConfig",
        )
        data = _json_out(result)
        self.assertEqual(data["status"], "ok")

    def test_empty_file(self):
        (self.vault / "01-Import" / "empty.md").write_text("", encoding="utf-8")
        result = _run(self.vault, "unified-search", "anything")
        data = _json_out(result)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)


if __name__ == "__main__":
    unittest.main()
