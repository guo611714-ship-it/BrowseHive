"""ManifestAdapter 单元测试"""

import pytest
from agent.manifest_builder import (
    StocktakeAdapter,
    AutoreviewAdapter,
    GhIssuesAdapter,
    get_adapter,
    register_adapter,
)
from fix_engine.manifest import FixItem


# ─── StocktakeAdapter ──────────────────────────────────────

class TestStocktakeAdapter:
    def setup_method(self):
        self.adapter = StocktakeAdapter()

    def test_source_name(self):
        assert self.adapter.source_name() == "skill-stocktake"

    def test_retire_verdict(self):
        data = {
            "skills": {
                "old-skill": {
                    "verdict": "Retire",
                    "reason": "Superseded by new-skill",
                    "path": "~/.claude/skills/old-skill/SKILL.md",
                }
            }
        }
        items = self.adapter.to_fix_items(data)
        assert len(items) == 1
        assert items[0].id == "stocktake-retire-old-skill"
        assert items[0].priority == 1
        assert "Retire" in items[0].description

    def test_improve_verdict(self):
        data = {
            "skills": {
                "lazy-skill": {
                    "verdict": "Improve",
                    "reason": "Too long, trim to 150 lines",
                    "path": "~/.claude/skills/lazy-skill/SKILL.md",
                }
            }
        }
        items = self.adapter.to_fix_items(data)
        assert len(items) == 1
        assert items[0].id == "stocktake-improve-lazy-skill"
        assert items[0].context == "Too long, trim to 150 lines"

    def test_merge_verdict(self):
        data = {
            "skills": {
                "dup-skill": {
                    "verdict": "Merge into main-skill",
                    "reason": "42-line thin content",
                    "path": "~/.claude/skills/dup-skill/SKILL.md",
                }
            }
        }
        items = self.adapter.to_fix_items(data)
        assert len(items) == 1
        assert items[0].id == "stocktake-merge-dup-skill"
        assert items[0].metadata["target"] == "main-skill"

    def test_keep_verdict_ignored(self):
        data = {
            "skills": {
                "good-skill": {
                    "verdict": "Keep",
                    "reason": "Well-maintained",
                    "path": "~/.claude/skills/good-skill/SKILL.md",
                }
            }
        }
        items = self.adapter.to_fix_items(data)
        assert len(items) == 0

    def test_empty_skills(self):
        items = self.adapter.to_fix_items({"skills": {}})
        assert len(items) == 0

    def test_missing_path_skipped(self):
        data = {
            "skills": {
                "no-path": {"verdict": "Retire", "reason": "test"}
            }
        }
        items = self.adapter.to_fix_items(data)
        assert len(items) == 0


# ─── AutoreviewAdapter ─────────────────────────────────────

class TestAutoreviewAdapter:
    def setup_method(self):
        self.adapter = AutoreviewAdapter()

    def test_source_name(self):
        assert self.adapter.source_name() == "autoreview"

    def test_accepted_findings(self):
        findings = [
            {
                "id": "f1",
                "file_path": "src/main.py",
                "message": "Missing error handling",
                "severity": "critical",
                "status": "accepted",
                "line_start": 10,
                "line_end": 15,
                "suggestion": "Add try/except",
            },
            {
                "id": "f2",
                "file_path": "src/utils.py",
                "message": "Unused import",
                "severity": "minor",
                "status": "accepted",
            },
        ]
        items = self.adapter.to_fix_items(findings)
        assert len(items) == 2
        assert items[0].priority == 2  # critical
        assert items[1].priority == 0  # minor

    def test_rejected_findings_filtered(self):
        findings = [
            {"id": "f1", "file_path": "a.py", "message": "x", "severity": "critical", "status": "rejected"},
            {"id": "f2", "file_path": "b.py", "message": "y", "severity": "important", "status": "accepted"},
        ]
        items = self.adapter.to_fix_items(findings)
        assert len(items) == 1
        assert items[0].id == "review-f2"

    def test_filter_actionable_excludes_minor(self):
        items = [
            FixItem(id="a", file="a.py", description="a", agent_type="test", priority=2),
            FixItem(id="b", file="b.py", description="b", agent_type="test", priority=1),
            FixItem(id="c", file="c.py", description="c", agent_type="test", priority=0),
        ]
        filtered = self.adapter.filter_actionable(items)
        assert len(filtered) == 2
        assert all(i.priority >= 1 for i in filtered)


# ─── GhIssuesAdapter ───────────────────────────────────────

class TestGhIssuesAdapter:
    def setup_method(self):
        self.adapter = GhIssuesAdapter()

    def test_source_name(self):
        assert self.adapter.source_name() == "gh-issues"

    def test_basic_issue(self):
        issues = [
            {
                "number": 42,
                "title": "Fix login bug",
                "body": "Login fails on slow networks",
                "labels": ["bug"],
                "html_url": "https://github.com/owner/repo/issues/42",
            }
        ]
        items = self.adapter.to_fix_items(issues)
        assert len(items) == 1
        assert items[0].id == "issue-42"
        assert items[0].priority == 1

    def test_critical_label(self):
        issues = [
            {
                "number": 1,
                "title": "Security hole",
                "body": "SQL injection",
                "labels": ["critical", "security"],
            }
        ]
        items = self.adapter.to_fix_items(issues)
        assert items[0].priority == 2

    def test_file_inference_from_code_block(self):
        issues = [
            {
                "number": 1,
                "title": "Bug in auth",
                "body": "Error in `src/auth.py` line 42",
                "labels": [],
            }
        ]
        items = self.adapter.to_fix_items(issues)
        assert "src/auth.py" in items[0].metadata["all_files"]

    def test_empty_issues(self):
        items = self.adapter.to_fix_items([])
        assert len(items) == 0

    def test_none_labels(self):
        """labels 为 None 时不应崩溃"""
        issues = [
            {
                "number": 1,
                "title": "Bug",
                "body": "Error in `src/main.py`",
                "labels": None,
            }
        ]
        items = self.adapter.to_fix_items(issues)
        assert len(items) == 1
        assert items[0].priority == 1  # None labels -> no critical -> priority 1


# ─── 工厂函数 ──────────────────────────────────────────────

class TestFactory:
    def test_get_stocktake(self):
        adapter = get_adapter("stocktake")
        assert isinstance(adapter, StocktakeAdapter)

    def test_get_autoreview(self):
        adapter = get_adapter("autoreview")
        assert isinstance(adapter, AutoreviewAdapter)

    def test_get_issues(self):
        adapter = get_adapter("issues")
        assert isinstance(adapter, GhIssuesAdapter)

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            get_adapter("nonexistent")

    def test_register_custom_adapter(self):
        class CustomAdapter(StocktakeAdapter):
            def source_name(self):
                return "custom"

        register_adapter("custom", CustomAdapter)
        adapter = get_adapter("custom")
        assert adapter.source_name() == "custom"
