"""FixManifest 集成测试 — 端到端数据流验证"""

import pytest
from agent.manifest_builder import (
    StocktakeAdapter,
    AutoreviewAdapter,
    GhIssuesAdapter,
    get_adapter,
)
from fix_engine.manifest import FixManifest, FixItem


class TestStocktakeToFixManifest:
    """skill-stocktake → fix_manifest 端到端"""

    def test_full_pipeline(self):
        # 模拟 results.json
        results = {
            "skills": {
                "retire-me": {
                    "verdict": "Retire",
                    "reason": "Superseded by better-skill",
                    "path": "~/.claude/skills/retire-me/SKILL.md",
                },
                "improve-me": {
                    "verdict": "Improve",
                    "reason": "Too long, trim to 150 lines",
                    "path": "~/.claude/skills/improve-me/SKILL.md",
                },
                "keep-me": {
                    "verdict": "Keep",
                    "reason": "Good skill",
                    "path": "~/.claude/skills/keep-me/SKILL.md",
                },
            }
        }

        adapter = get_adapter("stocktake")
        items = adapter.to_fix_items(results)
        filtered = adapter.filter_actionable(items)

        # 只有 Retire 和 Improve 会被处理
        assert len(filtered) == 2
        assert filtered[0].id == "stocktake-retire-retire-me"
        assert filtered[1].id == "stocktake-improve-improve-me"

        # 构建 manifest
        manifest = FixManifest(tasks=filtered, strategy="auto")
        assert manifest.task_count == 2
        assert manifest.file_count == 2

    def test_multiple_retires_same_file(self):
        """多个 retire 指向同一文件（merge 场景）"""
        results = {
            "skills": {
                "skill-a": {
                    "verdict": "Merge into main",
                    "reason": "Overlap",
                    "path": "~/.claude/skills/main/SKILL.md",
                },
                "skill-b": {
                    "verdict": "Merge into main",
                    "reason": "Overlap",
                    "path": "~/.claude/skills/main/SKILL.md",
                },
            }
        }

        adapter = get_adapter("stocktake")
        items = adapter.to_fix_items(results)
        manifest = FixManifest(tasks=items, strategy="file")

        # 同一文件的任务会被引擎串行处理
        assert manifest.file_count == 1
        assert manifest.task_count == 2


class TestAutoreviewToFixManifest:
    """autoreview → fix_manifest 端到端"""

    def test_full_pipeline(self):
        findings = [
            {
                "id": "f1",
                "file_path": "src/auth.py",
                "message": "SQL injection risk",
                "severity": "critical",
                "status": "accepted",
                "line_start": 42,
                "line_end": 50,
                "suggestion": "Use parameterized queries",
            },
            {
                "id": "f2",
                "file_path": "src/auth.py",
                "message": "Missing error handling",
                "severity": "important",
                "status": "accepted",
                "line_start": 60,
                "line_end": 65,
                "suggestion": "Add try/except",
            },
            {
                "id": "f3",
                "file_path": "src/utils.py",
                "message": "Unused variable",
                "severity": "minor",
                "status": "accepted",
            },
            {
                "id": "f4",
                "file_path": "src/db.py",
                "message": "This is fine",
                "severity": "important",
                "status": "rejected",
            },
        ]

        adapter = get_adapter("autoreview")
        items = adapter.to_fix_items(findings)

        # 只有 accepted 的 findings
        assert len(items) == 3

        # filter_actionable 排除 minor
        filtered = adapter.filter_actionable(items)
        assert len(filtered) == 2
        assert all(i.priority >= 1 for i in filtered)

        # 构建 manifest，同文件串行
        manifest = FixManifest(tasks=filtered, strategy="file")
        assert manifest.file_count == 1  # 两个 finding 都在 src/auth.py
        assert manifest.task_count == 2


class TestGhIssuesToFixManifest:
    """gh-issues → fix_manifest 端到端"""

    def test_full_pipeline(self):
        issues = [
            {
                "number": 101,
                "title": "Login fails on mobile",
                "body": "Error in `src/auth.py` line 42",
                "labels": ["bug"],
                "html_url": "https://github.com/owner/repo/issues/101",
            },
            {
                "number": 102,
                "title": "Security: SQL injection",
                "body": "Found SQL injection in `src/db.py`",
                "labels": ["critical", "security"],
                "html_url": "https://github.com/owner/repo/issues/102",
            },
            {
                "number": 103,
                "title": "Feature: dark mode",
                "body": "Add dark mode support to `src/theme.py`",
                "labels": ["enhancement"],
                "html_url": "https://github.com/owner/repo/issues/103",
            },
        ]

        adapter = get_adapter("issues")
        items = adapter.to_fix_items(issues)
        filtered = adapter.filter_actionable(items)

        # 所有 issues 都是 actionable
        assert len(filtered) == 3

        # 优先级正确
        assert filtered[0].priority == 1  # bug
        assert filtered[1].priority == 2  # critical
        assert filtered[2].priority == 1  # enhancement

        # 文件推断正确
        assert "src/auth.py" in filtered[0].metadata["all_files"]
        assert "src/db.py" in filtered[1].metadata["all_files"]
        assert "src/theme.py" in filtered[2].metadata["all_files"]

        # 构建 manifest
        manifest = FixManifest(tasks=filtered, strategy="auto")
        assert manifest.task_count == 3
        assert manifest.file_count == 3  # 三个不同文件


class TestAdapterRegistration:
    """适配器注册和扩展"""

    def test_register_and_retrieve(self):
        from agent.manifest_builder import register_adapter

        class TestAdapter(StocktakeAdapter):
            def source_name(self):
                return "test-custom"

        register_adapter("test-custom", TestAdapter)
        adapter = get_adapter("test-custom")
        assert adapter.source_name() == "test-custom"

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            get_adapter("nonexistent")


class TestStrategyEnumConversion:
    """strategy string → FixStrategy enum 转换"""

    def test_auto_converts_to_enum(self):
        from fix_engine.manifest import FixManifest, FixItem, FixStrategy
        item = FixItem(id="t1", file="a.py", description="test", agent_type="x")
        strategy_aliases = {"parallel": "full"}
        strategy_normalized = strategy_aliases.get("auto", "auto")
        strategy_enum = FixStrategy(strategy_normalized)
        m = FixManifest(tasks=[item], strategy=strategy_enum)
        assert isinstance(m.strategy, FixStrategy)
        assert m.strategy == FixStrategy.AUTO

    def test_parallel_converts_to_full(self):
        from fix_engine.manifest import FixManifest, FixItem, FixStrategy
        item = FixItem(id="t1", file="a.py", description="test", agent_type="x")
        strategy_aliases = {"parallel": "full"}
        strategy_normalized = strategy_aliases.get("parallel", "parallel")
        strategy_enum = FixStrategy(strategy_normalized)
        m = FixManifest(tasks=[item], strategy=strategy_enum)
        assert m.strategy == FixStrategy.FULL_PARALLEL

    def test_file_converts_to_file_serial(self):
        from fix_engine.manifest import FixManifest, FixItem, FixStrategy
        item = FixItem(id="t1", file="a.py", description="test", agent_type="x")
        strategy_aliases = {"parallel": "full"}
        strategy_normalized = strategy_aliases.get("file", "file")
        strategy_enum = FixStrategy(strategy_normalized)
        m = FixManifest(tasks=[item], strategy=strategy_enum)
        assert m.strategy == FixStrategy.FILE_SERIAL

    def test_strategy_value_access_safe(self):
        """修复后 .value 不再 crash"""
        from fix_engine.manifest import FixManifest, FixItem, FixStrategy
        item = FixItem(id="t1", file="a.py", description="test", agent_type="x")
        m = FixManifest(tasks=[item], strategy=FixStrategy.AUTO)
        assert m.summary()  # .value 不再 AttributeError

    def test_file_serial_in_scheduling_strategy(self):
        from agent.engine.manifest import SchedulingStrategy
        assert SchedulingStrategy.FILE_SERIAL.value == "file"
