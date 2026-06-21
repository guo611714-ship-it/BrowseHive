"""Skill 索引 -- 扫描 SKILL.md frontmatter 构建内存索引"""
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

        name = frontmatter.get("name")
        if not name:
            logger.warning("name 缺失，fallback 为目录名: %s", dir_name)
            name = dir_name

        description = frontmatter.get("description", "")
        triggers = frontmatter.get("triggers", []) or []
        synonyms = frontmatter.get("synonyms", []) or []
        priority = frontmatter.get("priority", 0) or 0
        prompt_body = match.group(2).strip()

        if not triggers and not synonyms:
            logger.warning("triggers+synonyms empty, skip: %s", name)
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
        """Add entry and build reverse index"""
        self._entries[entry.name] = entry
        for trigger in entry.triggers:
            self._trigger_map.setdefault(trigger, []).append(entry.name)
        for synonym in entry.synonyms:
            self._synonym_map.setdefault(synonym, []).append(entry.name)

    def match(self, task_text: str) -> List[SkillEntry]:
        """Two-level match: exact -> fuzzy, return top-3"""
        task_lower = task_text.lower()

        scores: Dict[str, int] = {}

        for trigger, skill_names in self._trigger_map.items():
            if trigger in task_lower:
                for skill_name in skill_names:
                    scores[skill_name] = scores.get(skill_name, 0) + 3

        for synonym, skill_names in self._synonym_map.items():
            if synonym in task_lower:
                for skill_name in skill_names:
                    scores[skill_name] = scores.get(skill_name, 0) + 2

        for entry in self._entries.values():
            for trigger in entry.triggers + entry.synonyms:
                if trigger in task_lower:
                    scores[entry.name] = scores.get(entry.name, 0) + 1

        for name, score in scores.items():
            scores[name] = score + self._entries[name].priority

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [self._entries[name]
                for name, score in ranked[:3] if score > 0]
