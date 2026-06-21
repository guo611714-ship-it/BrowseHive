"""End-to-end test for the knowledge base system using real NVIDIA API calls."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # AI知识库/
KB_MANAGER = ROOT / "kb-manager.py"
ORIG_CONFIG = ROOT / "config.json"

# Load .env if NVIDIA_API_KEY not already in environment
if not os.environ.get("NVIDIA_API_KEY"):
    _env_file = ROOT / ".env"
    if _env_file.exists():
        for line in _env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Skip if no API key after loading .env
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
pytestmark = pytest.mark.skipif(
    not NVIDIA_API_KEY,
    reason="NVIDIA_API_KEY env var not set",
)

TEST_CONFIG = {
    "api_key_env": "NVIDIA_API_KEY",
    "base_url": "https://integrate.api.nvidia.com/v1",
    "model": "stepfun-ai/step-3.7-flash",
    "max_tokens": 4096,
    "vault_name": "AI知识库",
}

DECORATOR_CONTENT = """\
# Python装饰器详解

装饰器(Decorator)是Python中一种强大的语法特性，使用 @ 符号将一个函数"包裹"在另一个函数中，
从而在不修改原函数代码的情况下扩展其功能。

## 基本概念

1. **函数是一等对象**: Python中函数可以作为参数传递、赋值给变量、作为返回值。
2. **闭包(Closure)**: 内部函数引用外部函数的变量，即使外部函数已执行完毕。
3. **语法糖**: `@decorator` 等价于 `func = decorator(func)`。

## 常见用法

- **日志记录**: 在函数调用前后记录日志
- **权限校验**: 检查用户是否有权执行某个操作
- **缓存装饰器**: `@lru_cache` 自动缓存函数结果
- **计时装饰器**: 测量函数执行时间
- **重试机制**: 自动重试失败的操作

## 示例代码

```python
def timer(func):
    import time
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        print(f"{func.__name__} took {time.time()-start:.4f}s")
        return result
    return wrapper

@timer
def slow_function():
    import time
    time.sleep(1)
    return "done"
```
"""


def run_kb(tmp: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run kb-manager.py in the temp directory and return the result."""
    return subprocess.run(
        [sys.executable, str(tmp / "kb-manager.py"), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp),
        timeout=timeout,
    )


def parse_json_output(proc: subprocess.CompletedProcess[str]) -> dict | list:
    """Parse the JSON from stdout of a kb-manager command."""
    text = proc.stdout.strip()
    # The command writes to stdout.buffer via out(), which may include lines before JSON
    # Find the first { or [ that starts a JSON block
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            try:
                return json.loads(text[i:])
            except json.JSONDecodeError:
                continue
    # Fallback: try entire output
    return json.loads(text)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
@pytest.mark.slow
class TestE2E:
    """Full end-to-end validation of the knowledge base system."""

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(self, tmp_path: Path):
        """Create isolated temp workspace, copy tooling, clean up after."""
        self.tmp = tmp_path / "vault"
        self.tmp.mkdir()

        # Copy kb-manager.py and config.json into the temp vault
        shutil.copy2(KB_MANAGER, self.tmp / "kb-manager.py")
        (self.tmp / "config.json").write_text(
            json.dumps(TEST_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Create a separate memory dir for rebuild-index test
        self.memory_dir = tmp_path / "memory"
        self.memory_dir.mkdir()

        yield

    # ------------------------------------------------------------------
    # Step 1: init
    # ------------------------------------------------------------------
    def test_01_init(self):
        proc = run_kb(self.tmp, "init")
        assert proc.returncode == 0, f"init failed: {proc.stderr}"

        data = parse_json_output(proc)
        assert data["status"] == "ok"

        # Verify directories created inside the temp vault
        assert (self.tmp / "01-Import").is_dir()
        assert (self.tmp / "02-Notes").is_dir()
        assert (self.tmp / "03-Index").is_dir()
        assert (self.tmp / "03-Index" / "documents.json").exists()

    # ------------------------------------------------------------------
    # Step 2: analyze-text with real NVIDIA API
    # ------------------------------------------------------------------
    def test_02_analyze_text(self):
        # First init
        run_kb(self.tmp, "init")

        # Write the test content to a file
        src_file = self.tmp / "decorator.md"
        src_file.write_text(DECORATOR_CONTENT, encoding="utf-8")

        proc = run_kb(
            self.tmp,
            "analyze-text",
            "--title", "Python装饰器",
            "--category", "programming",
            "--file", str(src_file),
        )
        assert proc.returncode == 0, f"analyze-text failed: {proc.stderr}\n{proc.stdout}"

        data = parse_json_output(proc)
        assert data["status"] == "ok"
        assert data["concepts_count"] >= 1, "Expected at least 1 concept from NVIDIA analysis"
        assert len(data["tags"]) >= 1, "Expected at least 1 tag"
        assert data["title"] == "Python装饰器"

        # Verify the output .md file was created in 01-Import
        out_file = self.tmp / "01-Import" / "Python装饰器.md"
        assert out_file.exists(), "Output markdown file should exist"
        content = out_file.read_text(encoding="utf-8")
        assert "Python装饰器" in content
        assert "decorator" in content.lower() or "装饰器" in content

    # ------------------------------------------------------------------
    # Step 3: unified-search finds the just-analyzed document
    # ------------------------------------------------------------------
    def test_03_unified_search(self):
        run_kb(self.tmp, "init")

        src_file = self.tmp / "decorator.md"
        src_file.write_text(DECORATOR_CONTENT, encoding="utf-8")
        run_kb(
            self.tmp, "analyze-text",
            "--title", "Python装饰器",
            "--category", "programming",
            "--file", str(src_file),
        )

        proc = run_kb(self.tmp, "unified-search", "装饰器")
        assert proc.returncode == 0, f"unified-search failed: {proc.stderr}"

        results = json.loads(proc.stdout.strip())
        assert isinstance(results, list), "Expected a list of search results"
        assert len(results) >= 1, "Expected at least 1 search result for '装饰器'"

        # Verify the found result references the analyzed document
        titles = [r.get("title", "") for r in results]
        assert any("装饰器" in t for t in titles), (
            f"Expected '装饰器' in results, got titles: {titles}"
        )

    # ------------------------------------------------------------------
    # Step 4: list
    # ------------------------------------------------------------------
    def test_04_list(self):
        run_kb(self.tmp, "init")

        src_file = self.tmp / "decorator.md"
        src_file.write_text(DECORATOR_CONTENT, encoding="utf-8")
        run_kb(
            self.tmp, "analyze-text",
            "--title", "Python装饰器",
            "--category", "programming",
            "--file", str(src_file),
        )

        proc = run_kb(self.tmp, "list")
        assert proc.returncode == 0, f"list failed: {proc.stderr}"

        data = parse_json_output(proc)
        assert data["total"] >= 1, "Expected at least 1 document after analyze-text"
        assert any(
            "装饰器" in doc.get("title", "") for doc in data["documents"]
        ), "The analyzed document should appear in the list"

    # ------------------------------------------------------------------
    # Step 5: batch-import
    # ------------------------------------------------------------------
    def test_05_batch_import(self):
        run_kb(self.tmp, "init")

        # Create a folder with 2 .md files
        import_dir = self.tmp / "batch_src"
        import_dir.mkdir()
        (import_dir / "doc1.md").write_text(
            "# Docker基础\n\nDocker是一个开源的容器化平台，用于自动化应用程序的部署、扩展和管理。\n"
            "容器将应用程序及其依赖打包在一起，确保在任何环境中一致运行。\n",
            encoding="utf-8",
        )
        (import_dir / "doc2.md").write_text(
            "# Git分支策略\n\nGit分支策略定义了团队如何创建和合并分支。\n"
            "常见的策略有Git Flow、GitHub Flow和Trunk-Based Development。\n",
            encoding="utf-8",
        )

        proc = run_kb(
            self.tmp,
            "batch-import",
            str(import_dir),
            "--category", "tools",
        )
        assert proc.returncode == 0, f"batch-import failed: {proc.stderr}\n{proc.stdout}"

        data = parse_json_output(proc)
        assert data["status"] == "ok"
        assert data["imported"] >= 2, (
            f"Expected >= 2 imported, got {data['imported']}. Errors: {data.get('errors')}"
        )

        # Verify the documents appear in documents.json
        docs = json.loads(
            (self.tmp / "03-Index" / "documents.json").read_text(encoding="utf-8")
        ).get("documents", [])
        assert len(docs) >= 2

    # ------------------------------------------------------------------
    # Step 6: rebuild-index
    # ------------------------------------------------------------------
    def test_06_rebuild_index(self):
        # Create a subdirectory with a .md file in the memory dir
        cat_dir = self.memory_dir / "programming"
        cat_dir.mkdir()
        (cat_dir / "test-note.md").write_text(
            "# Test Note\n\nSome content about testing.\n",
            encoding="utf-8",
        )

        proc = run_kb(
            self.tmp, "rebuild-index",
            "--memory-dir", str(self.memory_dir),
        )
        assert proc.returncode == 0, f"rebuild-index failed: {proc.stderr}"

        data = parse_json_output(proc)
        assert data["status"] == "ok"

        index_file = self.memory_dir / "INDEX.md"
        assert index_file.exists(), "INDEX.md should be created"
        content = index_file.read_text(encoding="utf-8")
        assert "programming" in content, "INDEX.md should contain the category"
        assert "test-note" in content, "INDEX.md should contain the note name"

    # ------------------------------------------------------------------
    # Full pipeline: init -> analyze -> search -> list -> batch -> rebuild
    # ------------------------------------------------------------------
    def test_07_full_pipeline(self):
        """Run the entire pipeline in sequence as one integration check."""
        # 1. Init
        proc = run_kb(self.tmp, "init")
        assert proc.returncode == 0
        data = parse_json_output(proc)
        assert data["status"] == "ok"

        # 2. Analyze
        src_file = self.tmp / "decorator.md"
        src_file.write_text(DECORATOR_CONTENT, encoding="utf-8")
        proc = run_kb(
            self.tmp, "analyze-text",
            "--title", "Python装饰器",
            "--category", "programming",
            "--file", str(src_file),
        )
        assert proc.returncode == 0
        data = parse_json_output(proc)
        assert data["concepts_count"] >= 1

        # 3. Search
        proc = run_kb(self.tmp, "unified-search", "装饰器")
        assert proc.returncode == 0
        results = json.loads(proc.stdout.strip())
        assert len(results) >= 1

        # 4. List
        proc = run_kb(self.tmp, "list")
        assert proc.returncode == 0
        data = parse_json_output(proc)
        assert data["total"] >= 1

        # 5. Batch import (folder named with "python" hint to skip NVIDIA categorize calls)
        import_dir = self.tmp / "python_batch"
        import_dir.mkdir()
        (import_dir / "a.md").write_text("# Topic A\nContent A\n", encoding="utf-8")
        (import_dir / "b.md").write_text("# Topic B\nContent B\n", encoding="utf-8")
        proc = run_kb(self.tmp, "batch-import", str(import_dir), "--category", "programming")
        assert proc.returncode == 0
        data = parse_json_output(proc)
        assert data["imported"] >= 2

        # 6. Rebuild index
        cat_dir = self.memory_dir / "programming"
        cat_dir.mkdir(exist_ok=True)
        (cat_dir / "note.md").write_text("# Note\nContent\n", encoding="utf-8")
        proc = run_kb(self.tmp, "rebuild-index", "--memory-dir", str(self.memory_dir))
        assert proc.returncode == 0
        assert (self.memory_dir / "INDEX.md").exists()
