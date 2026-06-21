"""Shared Utilities -- engine module common helpers

Extracted from grpc_service.py and merge.py to reduce duplication.
"""

import json
import subprocess
import logging
from typing import Dict, Any, Optional, List

from .manifest import TaskManifest, FixTask, TaskPriority, SchedulingStrategy

logger = logging.getLogger(__name__)


# ============================================================
# Manifest Serialization: TaskManifest <-> dict
# ============================================================

def manifest_from_dict(data: Dict[str, Any]) -> TaskManifest:
    """从字典构建 TaskManifest"""
    tasks = []
    for t in data.get("tasks", []):
        tasks.append(FixTask(
            task_id=t["task_id"],
            description=t["description"],
            files=t.get("files", []),
            agent_type=t.get("agent_type", "neiguan_yingzao"),
            priority=TaskPriority(t.get("priority", "normal")),
            context=t.get("context"),
            expected_output=t.get("expected_output"),
            timeout=t.get("timeout", 300.0),
            depends_on=t.get("depends_on", []),
            metadata=t.get("metadata", {}),
            line_start=t.get("line_start"),
            line_end=t.get("line_end"),
        ))

    strategy = SchedulingStrategy(data.get("strategy", "auto"))
    priority = TaskPriority(data.get("priority", "normal"))

    return TaskManifest(
        tasks=tasks,
        strategy=strategy,
        priority=priority,
        context=data.get("context"),
        max_concurrent=data.get("max_concurrent", 5),
        metadata=data.get("metadata", {}),
    )


def manifest_to_dict(manifest: TaskManifest) -> Dict[str, Any]:
    """将 TaskManifest 转为字典"""
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "description": t.description,
                "files": t.files,
                "agent_type": t.agent_type,
                "priority": t.priority.value,
                "context": t.context,
                "expected_output": t.expected_output,
                "timeout": t.timeout,
                "depends_on": t.depends_on,
                "metadata": t.metadata,
                "line_start": t.line_start,
                "line_end": t.line_end,
            }
            for t in manifest.tasks
        ],
        "strategy": manifest.strategy.value,
        "priority": manifest.priority.value,
        "context": manifest.context,
        "max_concurrent": manifest.max_concurrent,
        "metadata": manifest.metadata,
    }


# ============================================================
# Git Helpers
# ============================================================

def git_show(base_ref: str, filepath: str) -> Optional[str]:
    """从 git 读取文件内容

    Args:
        base_ref: git 引用，如 HEAD, HEAD~1, commit SHA
        filepath: 仓库内文件路径

    Returns:
        文件内容，失败返回 None
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{base_ref}:{filepath}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


__all__ = [
    "manifest_from_dict",
    "manifest_to_dict",
    "git_show",
]
