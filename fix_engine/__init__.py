"""fix_engine — 独立修复引擎包

暴露 ParallelFixEngine 和结构化类型（FixManifest, FixResult）。
可嵌入 Agent Team 或独立运行。
"""

from .manifest import FixManifest, FixItem, FixStrategy, ConflictResolution
from .result import FixResult

__all__ = [
    "FixManifest",
    "FixItem",
    "FixStrategy",
    "ConflictResolution",
    "FixResult",
]
