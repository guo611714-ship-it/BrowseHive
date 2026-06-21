"""Skill Auto-Router tests"""
import os
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def tmp_skills_dir():
    """Create temporary skills dir, return (skills_dir, project_root)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        yield skills_dir, tmpdir


def _write_skill(skills_dir, name, frontmatter, body="# Skill Content\n"):
    """Helper: write SKILL.md"""
    skill_dir = skills_dir / name
    skill_dir.mkdir(exist_ok=True)
    content = f"---\n{frontmatter}\n---\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


class TestSkillIndexScan:
    def test_scan_frontmatter(self, tmp_skills_dir):
        """Normal parse triggers/synonyms"""
        skills_dir, project_root = tmp_skills_dir
        _write_skill(skills_dir, "autoreview",
                     "name: autoreview\ndescription: auto code review\ntriggers: [review, audit]\nsynonyms: [check]",
                     "# Autoreview\nDo review.")

        from agent.skill_index import SkillIndex
        index = SkillIndex.scan(project_root)

        assert "autoreview" in index._entries
        entry = index._entries["autoreview"]
        assert entry.name == "autoreview"
        assert entry.description == "auto code review"
        assert entry.triggers == ["review", "audit"]
        assert entry.synonyms == ["check"]
        assert "Autoreview" in entry.prompt

    def test_scan_missing_name(self, tmp_skills_dir):
        """Missing name falls back to dir name"""
        skills_dir, project_root = tmp_skills_dir
        _write_skill(skills_dir, "my-skill",
                     "description: test skill\ntriggers: [test]")

        from agent.skill_index import SkillIndex
        index = SkillIndex.scan(project_root)

        assert "my-skill" in index._entries
        assert index._entries["my-skill"].name == "my-skill"

    def test_scan_empty_triggers(self, tmp_skills_dir):
        """Skip when triggers+synonyms both empty"""
        skills_dir, project_root = tmp_skills_dir
        _write_skill(skills_dir, "no-triggers",
                     "description: skill without triggers")

        from agent.skill_index import SkillIndex
        index = SkillIndex.scan(project_root)

        assert "no-triggers" not in index._entries

    def test_scan_bad_frontmatter(self, tmp_skills_dir):
        """Skip on frontmatter parse failure"""
        skills_dir, project_root = tmp_skills_dir
        skill_dir = skills_dir / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "not valid frontmatter\n---\n---\n# Bad", encoding="utf-8"
        )

        from agent.skill_index import SkillIndex
        index = SkillIndex.scan(project_root)
        assert "bad-skill" not in index._entries


from agent.skill_index import SkillIndex, SkillEntry


@pytest.fixture
def sample_index():
    """Pre-built test index"""
    index = SkillIndex()
    index._add_entry(SkillEntry(
        name="autoreview", description="auto code review",
        triggers=["review", "audit", "审查"], synonyms=["check", "code check", "代码审查"],
        prompt="# Autoreview", path="", priority=0,
    ))
    index._add_entry(SkillEntry(
        name="fix", description="fix code issues",
        triggers=["fix", "repair"], synonyms=["patch", "bugfix"],
        prompt="# Fix", path="", priority=0,
    ))
    index._add_entry(SkillEntry(
        name="high-priority", description="high priority skill",
        triggers=["urgent"], synonyms=["emergency"],
        prompt="# Urgent", path="", priority=5,
    ))
    return index


class TestSkillIndexMatch:
    def test_match_exact_trigger(self, sample_index):
        """Exact trigger match"""
        results = sample_index.match("please review this code")
        assert len(results) > 0
        assert results[0].name == "autoreview"

    def test_match_exact_synonym(self, sample_index):
        """Synonym match"""
        results = sample_index.match("help me check code quality")
        assert len(results) > 0
        assert results[0].name == "autoreview"

    def test_match_fuzzy_chinese(self, sample_index):
        """Chinese substring match via synonym"""
        results = sample_index.match("help check code quality")
        assert len(results) > 0
        assert results[0].name == "autoreview"

    def test_match_priority_breaks_tie(self, sample_index):
        """Priority wins on tie"""
        results = sample_index.match("urgent task")
        assert len(results) > 0
        assert results[0].name == "high-priority"

    def test_match_no_match(self, sample_index):
        """No match returns empty"""
        results = sample_index.match("nice weather today")
        assert results == []

    def test_match_duplicate_triggers(self):
        """Two skills share trigger, higher priority wins"""
        index = SkillIndex()
        index._add_entry(SkillEntry(
            name="skill-a", description="A",
            triggers=["review"], synonyms=[],
            prompt="A", path="", priority=0,
        ))
        index._add_entry(SkillEntry(
            name="skill-b", description="B",
            triggers=["review"], synonyms=[],
            prompt="B", path="", priority=3,
        ))
        results = index.match("code review")
        assert len(results) > 0
        assert results[0].name == "skill-b"


from agent.skill_router import SkillRouter


class TestSkillRouter:
    def test_router_returns_top1(self, sample_index):
        """路由返回 top-1 skill"""
        router = SkillRouter(sample_index)
        result = router.route("please review this code")

        assert result is not None
        assert result["name"] == "autoreview"
        assert result["description"] == "auto code review"
        assert "Autoreview" in result["content"]
        assert "all_matches" in result

    def test_router_no_match_none(self, sample_index):
        """无匹配返回 None"""
        router = SkillRouter(sample_index)
        result = router.route("今天天气真好")
        assert result is None

    def test_router_content_truncation(self):
        """超长内容截断"""
        index = SkillIndex()
        long_prompt = "x" * 10000
        index._add_entry(SkillEntry(
            name="long-skill", description="长技能",
            triggers=["long"], synonyms=[],
            prompt=long_prompt, path="", priority=0,
        ))
        router = SkillRouter(index)
        result = router.route("long task")

        assert result is not None
        assert len(result["content"]) <= 8020
        assert result["content"].endswith("[truncated]")

    def test_router_content_caching(self, sample_index):
        """内容缓存：同一 skill 多次路由返回相同内容"""
        router = SkillRouter(sample_index)
        r1 = router.route("help me review this")
        r2 = router.route("please audit this code")
        assert r1["content"] == r2["content"]


class TestDispatcherIntegration:
    def test_dispatcher_injects_skill(self, sample_index):
        """system_prompt 包含 skill 内容"""
        router = SkillRouter(sample_index)

        base_prompt = "你是翰林。\n【任务】\n审查代码\n"
        skill_info = router.route("审查代码")

        if skill_info:
            skill_block = f"""
## 参考 Skill: {skill_info['name']}
{skill_info['description']}

以下是该 skill 的详细指令，请遵循执行：
---
{skill_info['content']}
---
"""
            base_prompt = base_prompt + "\n\n" + skill_block

        assert "## 参考 Skill: autoreview" in base_prompt
        assert "auto code review" in base_prompt
        assert "Autoreview" in base_prompt

    def test_dispatcher_no_injection(self, sample_index):
        """无匹配时不注入"""
        router = SkillRouter(sample_index)

        base_prompt = "你是翰林。\n【任务】\n今天天气真好\n"
        skill_info = router.route("今天天气真好")

        assert skill_info is None
        assert "参考 Skill" not in base_prompt
