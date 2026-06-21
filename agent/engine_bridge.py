"""EngineBridge — 引擎桥接实现

将 agent.engine.ParallelFixEngine 适配为 EngineProtocol 接口。
转换内部 Dict 结果为结构化 FixResult。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fix_engine.manifest import FixManifest, FixStrategy
from fix_engine.result import FixResult
from agent.engine.manifest import TaskManifest, FixTask, TaskPriority, SchedulingStrategy

logger = logging.getLogger(__name__)

PRIORITY_MAP = {0: TaskPriority.NORMAL, 1: TaskPriority.HIGH, 2: TaskPriority.CRITICAL}

STRATEGY_MAP = {
    "auto": SchedulingStrategy.AUTO,
    "full": SchedulingStrategy.PARALLEL,
    "parallel": SchedulingStrategy.PARALLEL,
    "serial": SchedulingStrategy.SERIAL,
    "file": SchedulingStrategy.FILE_SERIAL,
}


class EngineBridge:
    """引擎桥接器

    包装 ParallelFixEngine，暴露 EngineProtocol 兼容的接口。
    职责：接口翻译 + 结果结构化。不含调度逻辑。

    用法:
        from agent.engine.fix_engine import ParallelFixEngine
        from agent.engine_bridge import EngineBridge

        engine = ParallelFixEngine()
        bridge = EngineBridge(engine)
        result = await bridge.submit_fix_manifest(manifest)
    """

    def __init__(self, engine: Any):
        """
        Args:
            engine: ParallelFixEngine 实例（鸭子类型，不强制类型）
        """
        self._engine = engine

    async def submit_fix_manifest(self, manifest: FixManifest) -> FixResult:
        """提交修复清单

        将 FixManifest 转换为引擎内部格式，执行后将 Dict 结果转换为 FixResult。
        """
        tasks = []
        for item in manifest.tasks:
            priority = PRIORITY_MAP.get(item.priority, TaskPriority.NORMAL)

            tasks.append(FixTask(
                task_id=item.id,
                description=item.description,
                files=[item.file],
                agent_type=item.agent_type,
                priority=priority,
                context=item.context,
                metadata=item.metadata or {},
                line_start=item.line_start,
                line_end=item.line_end,
            ))

        strategy = STRATEGY_MAP.get(
            manifest.strategy.value if hasattr(manifest.strategy, 'value') else manifest.strategy,
            SchedulingStrategy.AUTO,
        )

        engine_manifest = TaskManifest(
            tasks=tasks,
            strategy=strategy,
            max_concurrent=manifest.max_workers or 5,
            context=manifest.repo_snapshot,
            metadata=manifest.metadata or {},
        )

        # 执行（使用注入的引擎实例，而非全局单例）
        try:
            raw = await self._engine.submit(engine_manifest)
        except Exception as e:
            return FixResult(success=False, summary=str(e))

        # Dict → FixResult
        status = raw.get("status", "unknown")
        merged = raw.get("merged", {})

        return FixResult(
            success=status in ("success", "empty"),
            summary=f"{status}: {len(raw.get('results', []))} tasks executed",
            patch=merged.get("merged_files"),
            conflicts=merged.get("conflicts", []),
            details=raw.get("results", []),
            conflict_analysis=raw.get("conflict_analysis"),
        )
