"""EngineProtocol — 引擎桥接抽象接口

Skill 依赖此 Protocol 而非具体实现。
通过 ContextVar 注入，支持进程内/进程外/mock 三种模式。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fix_engine.manifest import FixManifest
from fix_engine.result import FixResult


@runtime_checkable
class EngineProtocol(Protocol):
    """并行修复引擎协议

    Skill 通过此接口提交修复任务，不感知引擎内部实现。
    """

    async def submit_fix_manifest(self, manifest: FixManifest) -> FixResult:
        """提交修复清单，引擎负责调度、执行、合并，返回最终结果"""
        ...
