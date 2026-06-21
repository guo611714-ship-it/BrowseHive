"""Parallel Fix Engine — 统一入口

Skills 的一行调用入口:
    from agent.engine import fix_engine
    result = await fix_engine.submit(manifest)

内部流程:
    TaskManifest → SmartSharder → EnhancedScheduler → dispatch_parallel → ResultAggregator
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from .manifest import (
    TaskManifest, FixTask, TaskPriority, SchedulingStrategy,
    SmartSharder, Shard, create_task, create_manifest,
)
from .predictor import ConflictPredictor, ConflictPrediction
from .scheduler import EnhancedScheduler, ResultAggregator

logger = logging.getLogger(__name__)


class ParallelFixEngine:
    """自进化并行修复引擎 — Phase 1

    架构:
        Skills → submit(manifest) → Shard → Schedule → Dispatch → Aggregate

    用法:
        engine = ParallelFixEngine()
        result = await engine.submit(manifest)
    """

    def __init__(
        self,
        dispatcher: Optional[Any] = None,
        predictor: Optional[ConflictPredictor] = None,
        pool: Optional[Any] = None,
        service: Optional[Any] = None,
    ) -> None:
        """
        Args:
            dispatcher: SubagentDispatcher 实例（可选，默认自动获取）
            predictor: ConflictPredictor 实例（可选，默认 ConflictPredictor()）
            pool: DistributedWorkerPool 实例（可选）
            service: EngineService 实例（可选，用于队列式执行）
        """
        self.dispatcher = dispatcher
        self.pool = pool          # DistributedWorkerPool (optional)
        self.service = service    # EngineService (optional, for queue-based execution)
        self.scheduler = EnhancedScheduler(dispatcher=dispatcher, pool=pool)
        predictor = predictor or ConflictPredictor()
        self.sharder = SmartSharder(predictor=predictor)
        self.predictor = predictor

    async def submit(self, manifest: TaskManifest) -> Dict[str, Any]:
        """提交任务清单并执行

        这是 skills 的主要入口。整个流程:
        1. 验证 manifest
        2. 分片（SmartSharder）
        3. 冲突分析
        4. 调度执行（EnhancedScheduler）
        5. 结果聚合（ResultAggregator）
        6. 返回统一结果

        Args:
            manifest: 标准化任务清单

        Returns:
            {
                "status": "success" | "partial" | "failed",
                "results": [...],
                "merged": {...},
                "conflict_analysis": {...},
                "stats": {...}
            }
        """
        # Step 1: 验证
        if not manifest.tasks:
            return {"status": "empty", "message": "No tasks to execute"}

        # Step 2: 冲突分析
        conflict_analysis = self.predictor.analyze_manifest(manifest)
        logger.info(f"冲突分析: {conflict_analysis['total_conflicts']} conflicts "
                     f"(high={conflict_analysis['by_severity']['high']})")

        # Step 3: 调度执行
        sched_result = None
        if self.service is not None:
            try:
                sched_result = await self.service.submit_and_wait(manifest)
            except Exception as svc_err:
                logger.warning(f"服务提交失败，回退到本地调度: {svc_err}")
                sched_result = None

        if sched_result is None:
            sched_result = await self.scheduler.schedule(manifest)

        # Normalize service result to match scheduler format
        sched_result.setdefault("shards", [])
        sched_result.setdefault("results", [])
        sched_result.setdefault("status", "success" if not sched_result.get("failed_items") else "partial")
        sched_result.setdefault("stats", {
            "total_tasks": sched_result.get("total", 0),
            "completed": sched_result.get("completed", 0),
            "failed": sched_result.get("failed", 0),
        })
        sched_result.setdefault("failed_items", [
            {"summary": e} for e in sched_result.get("errors", [])
        ])

        # Step 4: 结果聚合
        aggregated = ResultAggregator.aggregate(sched_result.get("results", []))

        return {
            "status": sched_result["status"],
            "results": sched_result["results"],
            "shards": sched_result["shards"],
            "merged": aggregated,
            "conflict_analysis": conflict_analysis,
            "stats": sched_result["stats"],
            "failed_items": sched_result.get("failed_items", []),
        }

    def analyze(self, manifest: TaskManifest) -> Dict[str, Any]:
        """仅分析，不执行。用于预览分片和冲突情况。"""
        shards = self.sharder.shard(manifest)
        conflict_analysis = self.predictor.analyze_manifest(manifest)

        return {
            "manifest_summary": manifest.summary(),
            "shards": [
                {
                    "shard_id": s.shard_id,
                    "task_count": s.task_count,
                    "files": list(s.files),
                    "reason": s.reason,
                    "tasks": [t.task_id for t in s.tasks],
                }
                for s in shards
            ],
            "conflict_analysis": conflict_analysis,
            "execution_plan": {
                "total_shards": len(shards),
                "max_concurrent": manifest.max_concurrent,
                "strategy": manifest.strategy.value,
                "estimated_shards_to_serialize": sum(
                    1 for s in shards if s.task_count > 1
                ),
            },
        }

    def summary(self) -> str:
        return self.scheduler.summary()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 便捷 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 模块级引擎实例（延迟初始化）
_engine: Optional[ParallelFixEngine] = None


def get_engine(
    dispatcher: Optional[Any] = None,
    pool: Optional[Any] = None,
    service: Optional[Any] = None,
) -> ParallelFixEngine:
    """获取或创建引擎实例"""
    global _engine
    if _engine is None:
        _engine = ParallelFixEngine(dispatcher=dispatcher, pool=pool, service=service)
    else:
        if dispatcher is not None:
            _engine.dispatcher = dispatcher
            _engine.scheduler.dispatcher = dispatcher
        if pool is not None:
            _engine.pool = pool
            _engine.scheduler.pool = pool
        if service is not None:
            _engine.service = service
    return _engine


async def quick_fix(tasks: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """一行快速修复

    用法:
        result = await quick_fix([
            {"task_id": "fix-1", "description": "修复路径遍历", "files": ["a.py"]},
            {"task_id": "fix-2", "description": "添加空值检查", "files": ["b.py"]},
        ])
    """
    fix_tasks = [
        FixTask(
            task_id=t["task_id"],
            description=t["description"],
            files=t.get("files", []),
            agent_type=t.get("agent_type", "neiguan_yingzao"),
            priority=TaskPriority(t.get("priority", "normal")),
            context=t.get("context"),
            expected_output=t.get("expected_output"),
            timeout=t.get("timeout", 300.0),
            depends_on=t.get("depends_on", []),
            line_start=t.get("line_start"),
            line_end=t.get("line_end"),
        )
        for t in tasks
    ]

    # Extract engine-level kwargs before passing remaining to TaskManifest
    dispatcher = kwargs.pop("dispatcher", None)
    pool = kwargs.pop("pool", None)
    service = kwargs.pop("service", None)

    manifest = TaskManifest(tasks=fix_tasks, **kwargs)
    engine = get_engine(dispatcher=dispatcher, pool=pool, service=service)
    return await engine.submit(manifest)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 导出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    # 核心类
    "ParallelFixEngine",
    "TaskManifest",
    "FixTask",
    "TaskPriority",
    "SchedulingStrategy",
    "SmartSharder",
    "Shard",
    "ConflictPredictor",
    "ConflictPrediction",
    "EnhancedScheduler",
    "ResultAggregator",
    # 便捷函数
    "get_engine",
    "quick_fix",
    "create_task",
    "create_manifest",
]
