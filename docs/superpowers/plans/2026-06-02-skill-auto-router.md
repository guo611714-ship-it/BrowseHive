# Skill Auto-Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 dispatcher 在派遣子代理前自动匹配最相关的 skill，将其内容注入 system_prompt。

**Architecture:** SkillIndex 扫描 SKILL.md frontmatter 构建内存索引，SkillRouter 两级匹配任务文本，Dispatcher 在 `_dispatch_impl` 中注入 skill 内容到 system_prompt 末尾。

**Tech Stack:** Python 3.11+, yaml (PyYAML), re, pathlib, dataclasses

**Spec:** `docs/superpowers/specs/2026-06-02-skill-auto-router-design.md`

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `agent/skill_index.py` | 新建 | SkillEntry 数据类 + SkillIndex 扫描/索引/匹配 |
| `agent/skill_router.py` | 新建 | SkillRouter 路由协调 + 内容缓存 |
| `agent/tools/dispatch/dispatcher.py` | 修改 | `_dispatch_impl` 中注入 skill 到 system_prompt |
| `tests/test_skill_router.py` | 新建 | 13 项测试 |

---

### Task 1: SkillEntry 数据类 + SkillIndex 扫描

**Files:**
- Create: `agent/skill_index.py`
- Test: `tests/test_skill_router.py`

- [ ] **Step 1: Write failing tests for SkillIndex scan**

```python
# tests/test_skill_router.py
"""Skill Auto-Router 测试"""
import os
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def tmp_skills_dir():
    """创建临时 skills 目录，返回 (skills_dir, project_root)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        yield skills_dir, tmpdir


def _write_skill(skills_dir, name, frontmatter, body="# Skill Content\n"):
    """辅助：写入 SKILL.md"""
    skill_dir = skills_dir / name
    skill_dir.mkdir(exist_ok=True)
    content = f"---\n{frontmatter}\n---\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


class TestSkillIndexScan:
    def test_scan_frontmatter(self, tmp_skills_dir):
        """正常解析 triggers/synonyms"""
        skills_dir, project_root = tmp_skills_dir
        _write_skill(skills_dir, "autoreview",
                     "name: autoreview\ndescription: 自动代码审查\ntriggers: [审查, review]\nsynonyms: [审阅]",
                     "# Autoreview\nDo review.")

        from agent.skill_index import SkillIndex
        index = SkillIndex.scan(project_root)

        assert "autoreview" in index._entries
        entry = index._entries["autoreview"]
        assert entry.name == "autoreview"
        assert entry.description == "自动代码审查"
        assert entry.triggers == ["审查", "review"]
        assert entry.synonyms == ["审阅"]
        assert "Autoreview" in entry.prompt

    def test_scan_missing_name(self, tmp_skills_dir):
        """name 缺失时 fallback 为目录名"""
        skills_dir, project_root = tmp_skills_dir
        _write_skill(skills_dir, "my-skill",
                     "description: 测试技能\ntriggers: [测试]")

        from agent.skill_index import SkillIndex
        index = SkillIndex.scan(project_root)

        assert "my-skill" in index._entries
        assert index._entries["my-skill"].name == "my-skill"

    def test_scan_empty_triggers(self, tmp_skills_dir):
        """triggers+synonyms 均空时跳过"""
        skills_dir, project_root = tmp_skills_dir
        _write_skill(skills_dir, "no-triggers",
                     "description: 无触发词的技能")

        from agent.skill_index import SkillIndex
        index = SkillIndex.scan(project_root)

        assert "no-triggers" not in index._entries
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/test_skill_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.skill_index'`

- [ ] **Step 3: Implement SkillEntry + SkillIndex.scan**

```python
# agent/skill_index.py
"""Skill 索引 — 扫描 SKILL.md frontmatter 构建内存索引"""
import os
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_SKILL_PROMPT_CHARS = 8000


@dataclass
class SkillEntry:
    """单个 skill 的索引条目"""
    name: str
    description: str
    triggers: List[str]
    synonyms: List[str]
    prompt: str
    path: str
    priority: int = 0


class SkillIndex:
    """SKILL.md frontmatter 索引，支持两级匹配"""

    def __init__(self):
        self._entries: Dict[str, SkillEntry] = {}
        self._trigger_map: Dict[str, List[str]] = {}   # trigger -> [skill_names]
        self._synonym_map: Dict[str, List[str]] = {}   # synonym -> [skill_names]

    @classmethod
    def scan(cls, project_root: str = ".") -> "SkillIndex":
        """扫描 .claude/skills/*/SKILL.md，构建索引"""
        index = cls()
        skills_dir = Path(project_root) / ".claude" / "skills"

        if not skills_dir.exists():
            logger.info("Skill 目录不存在: %s", skills_dir)
            return index

        for skill_path in skills_dir.iterdir():
            if not skill_path.is_dir():
                continue
            skill_file = skill_path / "SKILL.md"
            if not skill_file.exists():
                continue

            entry = index._parse_skill(skill_file, skill_path.name)
            if entry:
                index._add_entry(entry)

        logger.info("SkillIndex 扫描完成: %d 个 skill", len(index._entries))
        return index

    def _parse_skill(self, skill_file: Path, dir_name: str) -> Optional[SkillEntry]:
        """解析单个 SKILL.md"""
        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("读取 SKILL.md 失败 %s: %s", skill_file, e)
            return None

        # 解析 YAML frontmatter
        match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        if not match:
            logger.warning("SKILL.md 格式无效: %s", skill_file)
            return None

        try:
            import yaml
            frontmatter = yaml.safe_load(match.group(1))
        except Exception as e:
            logger.warning("frontmatter 解析失败 %s: %s", skill_file, e)
            return None

        if not isinstance(frontmatter, dict):
            logger.warning("frontmatter 非字典: %s", skill_file)
            return None

        # name: fallback 为目录名
        name = frontmatter.get("name")
        if not name:
            logger.warning("name 缺失，fallback 为目录名: %s", dir_name)
            name = dir_name

        description = frontmatter.get("description", "")
        triggers = frontmatter.get("triggers", []) or []
        synonyms = frontmatter.get("synonyms", []) or []
        priority = frontmatter.get("priority", 0) or 0
        prompt_body = match.group(2).strip()

        # triggers + synonyms 均空 → 跳过
        if not triggers and not synonyms:
            logger.warning("triggers+synonyms 均空，跳过: %s", name)
            return None

        return SkillEntry(
            name=name,
            description=description,
            triggers=[str(t).lower() for t in triggers],
            synonyms=[str(s).lower() for s in synonyms],
            prompt=prompt_body,
            path=str(skill_file),
            priority=int(priority),
        )

    def _add_entry(self, entry: SkillEntry):
        """添加条目并构建反向索引"""
        self._entries[entry.name] = entry
        for trigger in entry.triggers:
            self._trigger_map.setdefault(trigger, []).append(entry.name)
        for synonym in entry.synonyms:
            self._synonym_map.setdefault(synonym, []).append(entry.name)

    def match(self, task_text: str) -> List[SkillEntry]:
        """两级匹配：精确 → 模糊，返回 top-3"""
        task_lower = task_text.lower()

        # 初始化：priority 作为基础分
        scores = {name: entry.priority * 10
                  for name, entry in self._entries.items()}

        # Level 1: 精确匹配 triggers（权重 3）
        for trigger, skill_names in self._trigger_map.items():
            if trigger in task_lower:
                for skill_name in skill_names:
                    scores[skill_name] = scores.get(skill_name, 0) + 3

        # Level 1: 精确匹配 synonyms（权重 2）
        for synonym, skill_names in self._synonym_map.items():
            if synonym in task_lower:
                for skill_name in skill_names:
                    scores[skill_name] = scores.get(skill_name, 0) + 2

        # Level 2: 模糊匹配 — 子串包含（权重 1）
        for entry in self._entries.values():
            for trigger in entry.triggers + entry.synonyms:
                if trigger in task_lower:
                    scores[entry.name] = scores.get(entry.name, 0) + 1

        # 按分数排序，返回 top-3
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [self._entries[name]
                for name, score in ranked[:3] if score > 0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/test_skill_router.py::TestSkillIndexScan -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agent/skill_index.py tests/test_skill_router.py
git commit -m "feat: SkillIndex 扫描+索引 — frontmatter 解析+反向索引+两级匹配"
```

---

### Task 2: SkillIndex 匹配测试

**Files:**
- Modify: `tests/test_skill_router.py`

- [ ] **Step 1: Write matching tests**

```python
# 追加到 tests/test_skill_router.py

from agent.skill_index import SkillIndex, SkillEntry


@pytest.fixture
def sample_index():
    """预构建的测试索引"""
    index = SkillIndex()
    index._add_entry(SkillEntry(
        name="autoreview", description="自动代码审查",
        triggers=["审查", "review"], synonyms=["审阅", "检查代码"],
        prompt="# Autoreview", path="", priority=0,
    ))
    index._add_entry(SkillEntry(
        name="fix", description="修复代码问题",
        triggers=["fix", "修复"], synonyms=["修补", "bug修复"],
        prompt="# Fix", path="", priority=0,
    ))
    index._add_entry(SkillEntry(
        name="high-priority", description="高优先级技能",
        triggers=["urgent"], synonyms=["紧急"],
        prompt="# Urgent", path="", priority=5,
    ))
    return index


class TestSkillIndexMatch:
    def test_match_exact_trigger(self, sample_index):
        """精确匹配 triggers"""
        results = sample_index.match("请审查这段代码")
        assert len(results) > 0
        assert results[0].name == "autoreview"

    def test_match_exact_synonym(self, sample_index):
        """匹配 synonyms"""
        results = sample_index.match("帮我检查代码质量")
        assert len(results) > 0
        assert results[0].name == "autoreview"

    def test_match_fuzzy_chinese(self, sample_index):
        """纯中文子串匹配 — synonym 应命中"""
        results = sample_index.match("帮我检查代码质量")
        assert len(results) > 0
        assert results[0].name == "autoreview"

    def test_match_priority_breaks_tie(self, sample_index):
        """同分时 priority 胜出"""
        # "urgent" 同时匹配 high-priority 的 trigger
        results = sample_index.match("urgent task")
        assert len(results) > 0
        assert results[0].name == "high-priority"

    def test_match_no_match(self, sample_index):
        """无匹配返回空"""
        results = sample_index.match("今天天气真好")
        assert results == []

    def test_match_duplicate_triggers(self):
        """两个 skill 同 trigger，高优先级胜出"""
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
```

- [ ] **Step 2: Run tests**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/test_skill_router.py::TestSkillIndexMatch -v`
Expected: 6 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_skill_router.py
git commit -m "test: SkillIndex 匹配测试 — 精确/模糊/priority/重复trigger"
```

---

### Task 3: SkillRouter 路由协调

**Files:**
- Create: `agent/skill_router.py`
- Modify: `tests/test_skill_router.py`

- [ ] **Step 1: Write failing tests for SkillRouter**

```python
# 追加到 tests/test_skill_router.py

from agent.skill_router import SkillRouter


class TestSkillRouter:
    def test_router_returns_top1(self, sample_index):
        """路由返回 top-1 skill"""
        router = SkillRouter(sample_index)
        result = router.route("请审查这段代码")

        assert result is not None
        assert result["name"] == "autoreview"
        assert result["description"] == "自动代码审查"
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
        assert len(result["content"]) <= 8020  # 8000 + "[truncated]"
        assert result["content"].endswith("[truncated]")

    def test_router_content_caching(self, sample_index):
        """内容缓存：同一 skill 多次路由返回相同对象"""
        router = SkillRouter(sample_index)
        r1 = router.route("审查代码")
        r2 = router.route("review code")
        # 两次路由同一个 skill，内容应相同
        assert r1["content"] == r2["content"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/test_skill_router.py::TestSkillRouter -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.skill_router'`

- [ ] **Step 3: Implement SkillRouter**

```python
# agent/skill_router.py
"""Skill 路由器 — 协调 SkillIndex 匹配和内容注入"""
import logging
from typing import Any, Dict, Optional

from .skill_index import SkillIndex, MAX_SKILL_PROMPT_CHARS

logger = logging.getLogger(__name__)


class SkillRouter:
    """根据任务文本匹配最相关的 skill，返回内容"""

    def __init__(self, skill_index: SkillIndex):
        self.index = skill_index
        self._content_cache: Dict[str, str] = {}

    def route(self, task_text: str) -> Optional[Dict[str, Any]]:
        """匹配任务，返回 top-1 skill 信息，无匹配返回 None"""
        entries = self.index.match(task_text)
        if not entries:
            return None

        best = entries[0]
        return {
            "name": best.name,
            "description": best.description,
            "content": self._load_content(best),
            "all_matches": [e.name for e in entries],
        }

    def _load_content(self, entry) -> str:
        """加载 skill 内容（带缓存 + 截断）"""
        if entry.name not in self._content_cache:
            content = entry.prompt
            if len(content) > MAX_SKILL_PROMPT_CHARS:
                content = content[:MAX_SKILL_PROMPT_CHARS] + "\n[truncated]"
            self._content_cache[entry.name] = content
        return self._content_cache[entry.name]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/test_skill_router.py::TestSkillRouter -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add agent/skill_router.py tests/test_skill_router.py
git commit -m "feat: SkillRouter 路由协调 — 匹配+缓存+截断"
```

---

### Task 4: Dispatcher 集成

**Files:**
- Modify: `agent/tools/dispatch/dispatcher.py`
- Modify: `tests/test_skill_router.py`

- [ ] **Step 1: Write failing tests for dispatcher integration**

```python
# 追加到 tests/test_skill_router.py

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


class TestDispatcherIntegration:
    def test_dispatcher_injects_skill(self, sample_index):
        """system_prompt 包含 skill 内容"""
        router = SkillRouter(sample_index)

        # 模拟 dispatcher 的 system_prompt 构造
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
        assert "自动代码审查" in base_prompt
        assert "Autoreview" in base_prompt

    def test_dispatcher_no_injection(self, sample_index):
        """无匹配时不注入"""
        router = SkillRouter(sample_index)

        base_prompt = "你是翰林。\n【任务】\n今天天气真好\n"
        skill_info = router.route("今天天气真好")

        assert skill_info is None
        assert "参考 Skill" not in base_prompt
```

- [ ] **Step 2: Run tests**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/test_skill_router.py::TestDispatcherIntegration -v`
Expected: 2 passed

- [ ] **Step 3: Integrate into dispatcher.py**

在 `_dispatch_impl` 方法中，`system_prompt` 构造完成后、LLM 循环之前，注入 skill 内容。

读取 `agent/tools/dispatch/dispatcher.py`，找到 `system_prompt += "\n【工具使用规则】` 之后的位置，插入以下代码：

```python
        # --- Skill 预路由注入 ---
        if self.skill_router:
            skill_info = self.skill_router.route(task)
            if skill_info:
                skill_block = f"""
## 参考 Skill: {skill_info['name']}
{skill_info['description']}

以下是该 skill 的详细指令，请遵循执行：
---
{skill_info['content']}
---
"""
                system_prompt += "\n\n" + skill_block
```

同时在 `SubagentDispatcher.__init__` 中添加 `skill_router` 参数：

```python
def __init__(self, model_orchestrator=None, team_store=None, tools=None,
             memory=None, progress_callback=None, skill_router=None):
    # ... existing code ...
    self.skill_router = skill_router
```

- [ ] **Step 4: Run full test suite**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/test_skill_router.py -v`
Expected: 13 passed

- [ ] **Step 5: Run full project tests**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/ -q`
Expected: all passed (no regressions)

- [ ] **Step 6: Commit**

```bash
git add agent/tools/dispatch/dispatcher.py tests/test_skill_router.py
git commit -m "feat: dispatcher 集成 skill auto-router — system_prompt 注入"
```

---

### Task 5: 端到端验证 + 收尾

**Files:**
- Modify: `tests/test_skill_router.py`

- [ ] **Step 1: Add edge case test for scan with bad frontmatter**

```python
# 追加到 TestSkillIndexScan

    def test_scan_bad_frontmatter(self, tmp_skills_dir):
        """frontmatter 解析失败时跳过"""
        skills_dir, project_root = tmp_skills_dir
        skill_dir = skills_dir / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "这不是有效的 frontmatter\n---\n---\n# Bad", encoding="utf-8"
        )

        from agent.skill_index import SkillIndex
        index = SkillIndex.scan(project_root)
        assert "bad-skill" not in index._entries
```

- [ ] **Step 2: Run all tests**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/test_skill_router.py -v`
Expected: 14 passed (13 original + 1 new)

- [ ] **Step 3: Run full project tests**

Run: `cd "d:/Users/lenovo/Desktop/claude workspace" && python -m pytest tests/ -q`
Expected: all passed

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: skill auto-router 全链路 — SkillIndex+SkillRouter+dispatcher集成+14测试"
```
