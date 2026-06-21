"""FixManifest + FixItem — 标准化修复任务格式

Skill 通过这些结构向引擎提交修复任务。
引擎根据 FixItem 的文件/行号信息进行智能分片和冲突预测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class FixStrategy(Enum):
    """调度策略"""
    AUTO = "auto"             # 引擎自行决定并/串行
    FULL_PARALLEL = "full"    # 强制全部并行
    FILE_SERIAL = "file"      # 同文件串行，不同文件并行
    FULL_SERIAL = "serial"    # 完全串行（极敏感的全局重构）


class ConflictResolution(Enum):
    """冲突处理策略"""
    AUTO_MERGE = "auto_merge"       # 自动合并非冲突修改
    FAIL_FAST = "fail"              # 发现冲突立即停止
    SERIAL_RERUN = "serial_rerun"   # 冲突项串行重跑（默认）


@dataclass
class FixItem:
    """单条修复任务

    Attributes:
        id: 唯一标识，用于追踪和结果匹配
        file: 文件路径
        description: 人类可读的修复描述
        agent_type: 执行修复的 Agent 类型
        line_start: 修复起始行（冲突检测用，可选）
        line_end: 修复结束行（可选）
        context: 附加上下文（如 review 建议原文）
        priority: 优先级（数字越大越高）
        metadata: 任意扩展数据
        group_id: 分组标识，用于关联同一批次的修复项
    """
    id: str
    file: str
    description: str
    agent_type: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    context: Optional[str] = None
    priority: int = 0
    metadata: dict = field(default_factory=dict)
    group_id: Optional[str] = None

    def to_task_dict(self) -> dict:
        """转换为引擎内部任务字典"""
        d: dict = {
            "task_id": self.id,
            "description": self.description,
            "files": [self.file],
            "agent_type": self.agent_type,
            "priority": str(self.priority),
            "context": self.context,
        }
        if self.metadata or self.group_id:
            d["metadata"] = dict(self.metadata)
            if self.group_id:
                d["metadata"]["group_id"] = self.group_id
        if self.line_start is not None:
            d["line_start"] = self.line_start
        if self.line_end is not None:
            d["line_end"] = self.line_end
        return d

    def to_json(self) -> Dict[str, Any]:
        """序列化为 JSON 可存储字典"""
        data: Dict[str, Any] = {
            "id": self.id,
            "file": self.file,
            "description": self.description,
            "agent_type": self.agent_type,
            "priority": self.priority,
        }
        if self.line_start is not None:
            data["line_start"] = self.line_start
        if self.line_end is not None:
            data["line_end"] = self.line_end
        if self.context is not None:
            data["context"] = self.context
        if self.metadata:
            data["metadata"] = self.metadata
        if self.group_id is not None:
            data["group_id"] = self.group_id
        return data

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "FixItem":
        """从 JSON 字典反序列化"""
        return cls(
            id=data["id"],
            file=data["file"],
            description=data["description"],
            agent_type=data["agent_type"],
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            context=data.get("context"),
            priority=data.get("priority", 0),
            metadata=data.get("metadata", {}),
            group_id=data.get("group_id"),
        )


@dataclass
class FixManifest:
    """提交给并行修复引擎的任务清单

    引擎根据这些信息进行智能分片、冲突预测、并行调度和结果合并。
    """
    tasks: list[FixItem]
    strategy: FixStrategy = FixStrategy.AUTO
    conflict: ConflictResolution = ConflictResolution.SERIAL_RERUN
    repo_snapshot: Optional[str] = None
    max_workers: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    @property
    def file_count(self) -> int:
        return len(set(t.file for t in self.tasks))

    def summary(self) -> str:
        return (f"FixManifest: {self.task_count} tasks, "
                f"{self.file_count} files, "
                f"strategy={self.strategy.value}")
