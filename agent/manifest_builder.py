"""ManifestAdapter — 数据源适配器基类

让不同 Skill（stocktake/autoreview/issues）共享同一个 fix_manifest 接口，
各自只需实现自己的「数据源适配器」，无需关心引擎细节。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from fix_engine.manifest import FixItem

logger = logging.getLogger(__name__)


class ManifestAdapter(ABC):
    """数据源适配器基类"""

    @abstractmethod
    def source_name(self) -> str:
        """返回数据源名称（用于日志和追踪）"""

    @abstractmethod
    def to_fix_items(self, raw_data: Any) -> List[FixItem]:
        """将原始数据转换为 FixItem 列表"""

    def filter_actionable(self, items: List[FixItem]) -> List[FixItem]:
        """过滤出可执行的任务（默认：全部保留）"""
        return items


class StocktakeAdapter(ManifestAdapter):
    """skill-stocktake 适配器

    输入：results.json 中的 verdicts
    输出：Retire/Improve/Merge 的 FixItem 列表
    """

    def source_name(self) -> str:
        return "skill-stocktake"

    def to_fix_items(self, raw_data: Dict[str, Any]) -> List[FixItem]:
        """results.json → FixItem[]"""
        items = []
        skills = raw_data.get("skills", {})

        for skill_name, info in skills.items():
            verdict = info.get("verdict", "Keep")
            reason = info.get("reason", "")
            path = info.get("path", "")

            # 如果没有 path，从 skill name 推断
            if not path:
                path = self._infer_path(skill_name)
                if not path:
                    logger.warning("skill-stocktake: %s 无法推断路径，跳过", skill_name)
                    continue

            if verdict == "Retire":
                items.append(FixItem(
                    id=f"stocktake-retire-{skill_name}",
                    file=path,
                    description=f"Retire skill '{skill_name}': {reason}",
                    agent_type="neiguan_yingzao",
                    priority=1,
                    metadata={"verdict": verdict, "skill": skill_name},
                ))
            elif verdict == "Improve":
                items.append(FixItem(
                    id=f"stocktake-improve-{skill_name}",
                    file=path,
                    description=f"Improve skill '{skill_name}': {reason}",
                    agent_type="neiguan_yingzao",
                    context=reason,
                    metadata={"verdict": verdict, "skill": skill_name},
                ))
            elif verdict.startswith("Merge into"):
                target = verdict.replace("Merge into ", "")
                items.append(FixItem(
                    id=f"stocktake-merge-{skill_name}",
                    file=path,
                    description=f"Merge '{skill_name}' into '{target}': {reason}",
                    agent_type="neiguan_yingzao",
                    context=reason,
                    metadata={"verdict": verdict, "skill": skill_name, "target": target},
                ))

        logger.info("stocktake: %d actionable items from %d skills", len(items), len(skills))
        return items

    def _infer_path(self, skill_name: str) -> str:
        """从 skill name 推断 SKILL.md 路径"""
        import os

        # 搜索顺序：项目级 > 全局级
        search_dirs = [
            os.path.join(os.getcwd(), ".claude", "skills"),
            os.path.expanduser("~/.claude/skills"),
        ]

        for skills_dir in search_dirs:
            candidate = os.path.join(skills_dir, skill_name, "SKILL.md")
            if os.path.exists(candidate):
                return candidate

        return ""


class AutoreviewAdapter(ManifestAdapter):
    """autoreview 适配器

    输入：review findings 列表
    输出：accepted findings 的 FixItem 列表
    """

    def source_name(self) -> str:
        return "autoreview"

    def to_fix_items(self, raw_data: List[Dict[str, Any]]) -> List[FixItem]:
        """findings list → FixItem[]"""
        items = []
        severity_map = {"critical": 2, "important": 1, "minor": 0}

        for f in raw_data:
            if f.get("status") != "accepted":
                continue

            severity = f.get("severity", "minor")
            items.append(FixItem(
                id=f"review-{f.get('id', 'unknown')}",
                file=f.get("file_path", "unknown"),
                description=f"[{severity}] {f.get('message', 'No message')}",
                agent_type="neiguan_yingzao",
                line_start=f.get("line_start"),
                line_end=f.get("line_end"),
                context=f.get("suggestion", ""),
                priority=severity_map.get(severity, 0),
                metadata={"finding_id": f.get("id"), "severity": severity},
            ))

        logger.info("autoreview: %d accepted findings", len(items))
        return items

    def filter_actionable(self, items: List[FixItem]) -> List[FixItem]:
        """排除 minor 级别"""
        return [i for i in items if i.priority >= 1]


class GhIssuesAdapter(ManifestAdapter):
    """gh-issues 适配器

    输入：GitHub issues 列表（from gh api）
    输出：每个 issue 一个 FixItem
    """

    def source_name(self) -> str:
        return "gh-issues"

    def to_fix_items(self, raw_data: List[Dict[str, Any]]) -> List[FixItem]:
        """issues list → FixItem[]"""
        import re

        items = []
        for issue in raw_data:
            body = issue.get("body", "") or ""
            labels = issue.get("labels") or []

            # 从 issue body 推断受影响文件
            files = self._infer_files(body)

            # 优先级：critical label → 2，否则 1
            priority = 2 if any("critical" in l.lower() for l in labels) else 1

            items.append(FixItem(
                id=f"issue-{issue['number']}",
                file=files[0] if files else "unknown",
                description=f"Fix #{issue['number']}: {issue.get('title', 'No title')}\n\n{body[:500]}",
                agent_type="neiguan_yingzao",
                context=issue.get("html_url", ""),
                priority=priority,
                metadata={
                    "issue_number": issue["number"],
                    "repo": issue.get("repository_url", ""),
                    "labels": labels,
                    "all_files": files,
                },
            ))

        logger.info("gh-issues: %d issues → FixItems", len(items))
        return items

    def _infer_files(self, body: str) -> List[str]:
        """从 issue body 推断受影响文件"""
        import re

        patterns = [
            r'`([a-zA-Z0-9_/.-]+\.(py|js|ts|tsx|jsx|java|go|rs|md))`',
            r'([a-zA-Z0-9_/.-]+\.(py|js|ts|tsx|jsx|java|go|rs)):\d+',
        ]
        files = set()
        for pattern in patterns:
            for match in re.findall(pattern, body):
                files.add(match[0] if isinstance(match, tuple) else match)
        return list(files)


# ─── 工厂函数 ───────────────────────────────────────────────

_ADAPTERS: Dict[str, type] = {
    "stocktake": StocktakeAdapter,
    "autoreview": AutoreviewAdapter,
    "issues": GhIssuesAdapter,
}


def get_adapter(source: str) -> ManifestAdapter:
    """根据数据源名称获取适配器实例"""
    adapter_cls = _ADAPTERS.get(source)
    if not adapter_cls:
        raise ValueError(
            f"Unknown source: '{source}'. Available: {list(_ADAPTERS.keys())}"
        )
    return adapter_cls()


def register_adapter(name: str, adapter_cls: type) -> None:
    """注册新的适配器（用于扩展）"""
    _ADAPTERS[name] = adapter_cls
