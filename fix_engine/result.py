"""FixResult — 结构化修复结果

Skill 通过 FixResult 获取引擎执行结果，无需解析裸 Dict。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class FixResult:
    """修复结果

    Attributes:
        success: 是否全部成功
        summary: 人类可读的摘要
        patch: 最终 patch（自动合并后），可能为 None
        conflicts: 未解决的冲突列表
        details: 每项修复的详情
        conflict_analysis: 冲突分析（含 by_severity 分类）
    """
    success: bool
    summary: str
    patch: Optional[Union[str, dict]] = None
    conflicts: list[dict] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)
    conflict_analysis: Optional[dict] = None  # 冲突分析（含 by_severity 分类）

    @property
    def failed_count(self) -> int:
        return sum(1 for d in self.details if d.get("status") == "failed")

    @property
    def succeeded_count(self) -> int:
        return sum(1 for d in self.details if d.get("status") == "success")
