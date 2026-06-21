"""Skill 路由器 -- 协调 SkillIndex 匹配和内容注入"""
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
