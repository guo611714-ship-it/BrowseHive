"""Enhanced Scheduler + Three-Way Merge + Worker Pool

Merged from scheduler.py, merge.py, and worker_pool.py.

Modules:
- EnhancedScheduler: file-aware intelligent scheduler
- ResultAggregator: merge non-conflicting modifications
- ThreeWayMerge: LCS-based three-way merge engine
- WorkerPool: agent instance pool management
"""

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .manifest import TaskManifest, Shard, SmartSharder, SchedulingStrategy
from .predictor import ConflictPredictor
from agent.tools.dispatch.parallel_core import (
    SubagentDispatcher, AgentProgressEvent, get_dispatcher
)

logger = logging.getLogger(__name__)


# ============================================================
# Part 1: Enhanced Scheduler (was scheduler.py)
# ============================================================

class EnhancedScheduler:
    """增强调度器 -- 在现有 dispatch_parallel 之上封装 shard 调度"""

    def __init__(self, dispatcher: Optional[SubagentDispatcher] = None,
                 pool: Optional[Any] = None):
        self.dispatcher = dispatcher
        self.pool = pool
        self.sharder = SmartSharder(predictor=ConflictPredictor())
        self.stats = {
            "total_shards": 0,
            "completed_shards": 0,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "serial_tasks": 0,
            "parallel_tasks": 0,
        }

    async def schedule(self, manifest: TaskManifest) -> Dict[str, Any]:
        self.stats = {
            "total_shards": 0, "completed_shards": 0,
            "total_tasks": 0, "completed_tasks": 0,
            "failed_tasks": 0, "serial_tasks": 0, "parallel_tasks": 0,
        }

        shards = self.sharder.shard(manifest)
        self.stats["total_shards"] = len(shards)
        self.stats["total_tasks"] = manifest.task_count

        logger.info("Manifest 分片完成: %d shards, %d tasks",
                     len(shards), manifest.task_count)

        all_results = []
        shard_results = []

        dispatcher = self.dispatcher or get_dispatcher()

        for shard in shards:
            shard_result = await self._execute_shard(shard, dispatcher)
            shard_results.append(shard_result)
            all_results.extend(shard_result.get("results", []))
            self.stats["completed_shards"] += 1

        failed = [r for r in all_results if r.get("status") != "success"]
        self.stats["failed_tasks"] = len(failed)
        self.stats["completed_tasks"] = len(all_results) - len(failed)

        if not failed:
            status = "success"
        elif len(failed) < len(all_results):
            status = "partial"
        else:
            status = "failed"

        return {
            "status": status,
            "shards": shard_results,
            "results": all_results,
            "stats": self.stats.copy(),
            "failed_items": failed,
        }

    async def _execute_shard(self, shard: Shard,
                              dispatcher: SubagentDispatcher) -> Dict[str, Any]:
        if not shard.tasks:
            return {"shard_id": shard.shard_id, "results": [], "status": "empty"}

        dispatcher.progress(AgentProgressEvent(
            timestamp=datetime.now(),
            agent_name="增强调度",
            step="start",
            status="running",
            message=f"Shard {shard.shard_id}: {shard.task_count} tasks ({shard.reason})",
            progress=0,
        ))

        dispatch_tasks = [t.to_dispatch_args() for t in shard.tasks]

        results = None
        if self.pool:
            try:
                results = []
                for task_args in dispatch_tasks:
                    pool_task = {
                        "task_id": task_args.get("task_id", ""),
                        "description": task_args.get("description", ""),
                        "files": task_args.get("files", []),
                        "agent_type": task_args.get("agent_type", ""),
                    }
                    try:
                        r = await self.pool.dispatch_task(pool_task)
                        results.append(r)
                    except Exception as task_err:
                        logger.warning(
                            "Pool task %s failed: %s",
                            task_args.get("task_id", "?"), task_err
                        )
                        results.append({
                            "task_id": task_args.get("task_id", ""),
                            "status": "failed",
                            "summary": f"[pool失败] {task_err}",
                        })
            except Exception as pool_err:
                logger.warning(
                    "Shard %d pool 调度失败，回退到 dispatcher: %s",
                    shard.shard_id, pool_err
                )
                results = None

        if results is None:
            try:
                results = await dispatcher.dispatch_parallel(
                    tasks=dispatch_tasks,
                    max_concurrent=min(len(dispatch_tasks), 5)
                )
            except Exception as e:
                logger.error("Shard %d 执行异常: %s", shard.shard_id, e)
                results = [
                    {"agent_type": t.agent_type, "status": "failed",
                     "summary": f"[shard异常] {e}"}
                    for t in shard.tasks
                ]

        self.stats["parallel_tasks"] += shard.task_count
        completed = sum(1 for r in results if r is not None and r.get("status") == "success")
        failed = shard.task_count - completed
        self.stats["completed_tasks"] += completed
        self.stats["failed_tasks"] += failed

        dispatcher.progress(AgentProgressEvent(
            timestamp=datetime.now(),
            agent_name="增强调度",
            step="complete",
            status="success" if failed == 0 else "error",
            message=f"Shard {shard.shard_id}: {completed}/{shard.task_count} 成功",
            progress=int(self.stats["completed_shards"] / self.stats["total_shards"] * 100)
            if self.stats["total_shards"] > 0 else 100,
        ))

        return {
            "shard_id": shard.shard_id,
            "reason": shard.reason,
            "task_count": shard.task_count,
            "completed": completed,
            "failed": failed,
            "results": results,
        }

    def get_stats(self) -> Dict[str, Any]:
        return self.stats.copy()

    def summary(self) -> str:
        s = self.stats
        return (f"Shards: {s['completed_shards']}/{s['total_shards']}, "
                f"Tasks: {s['completed_tasks']}/{s['total_tasks']} success, "
                f"Failed: {s['failed_tasks']}, "
                f"Parallel: {s['parallel_tasks']}")


# ============================================================
# Part 2: Result Aggregator (was in scheduler.py)
# ============================================================

class ResultAggregator:
    """聚合多个子代理的修改结果，自动合并非冲突项"""

    @staticmethod
    def aggregate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        file_changes: Dict[str, List[Dict]] = {}
        conflicts = []

        for r in results:
            if r.get("status") != "success":
                continue
            changes = ResultAggregator._extract_changes(r)
            for filepath, change in changes.items():
                if filepath in file_changes:
                    existing = file_changes[filepath]
                    if ResultAggregator._has_line_overlap(existing, change):
                        conflicts.append({
                            "file": filepath,
                            "existing": existing,
                            "new": change,
                            "reason": "line overlap"
                        })
                    else:
                        file_changes[filepath].append(change)
                else:
                    file_changes[filepath] = [change]

        merged = {}
        for filepath, changes in file_changes.items():
            if len(changes) == 1:
                merged[filepath] = changes[0].get("content", "")
            else:
                merged_content = ResultAggregator._merge_changes(changes)
                if merged_content is not None:
                    merged[filepath] = merged_content
                else:
                    conflicts.append({
                        "file": filepath,
                        "changes": changes,
                        "reason": "merge failed"
                    })

        return {
            "merged_files": merged,
            "conflicts": conflicts,
            "total_files": len(merged),
            "total_conflicts": len(conflicts),
            "summary": (f"{len(merged)} files merged, "
                        f"{len(conflicts)} conflicts need manual resolution"),
        }

    @staticmethod
    def _extract_changes(result: Dict) -> Dict[str, Dict]:
        changes = {}
        output = result.get("output", "") or result.get("summary", "")
        if not output:
            return changes

        import re
        patterns = [
            r"(?:修改|edited?|updated?)\s+([^\s,]+\.(?:py|js|ts|jsx|tsx|css|html|md))",
            r"(?:file|文件)[:\s]+([^\s,]+\.(?:py|js|ts|jsx|tsx|css|html|md))",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, output, re.IGNORECASE)
            for filepath in matches:
                if filepath not in changes:
                    changes[filepath] = {
                        "file": filepath,
                        "content": "",
                        "source": result.get("agent_type", "unknown"),
                    }

        return changes

    @staticmethod
    def _has_line_overlap(existing: List[Dict], new: Dict) -> bool:
        if not existing:
            return False

        new_has_lines = "start_line" in new and "end_line" in new
        new_agent = new.get("agent")

        if not new_has_lines:
            for e in existing:
                if e.get("agent") == new_agent and new_agent is not None:
                    return True
            return False

        new_start = new["start_line"]
        new_end = new["end_line"]

        for e in existing:
            if "start_line" not in e or "end_line" not in e:
                if e.get("agent") == new_agent and new_agent is not None:
                    return True
                continue
            if new_start <= e["end_line"] and e["start_line"] <= new_end:
                return True

        return False

    @staticmethod
    def _merge_changes(changes: List[Dict]) -> Optional[str]:
        if not changes:
            return None
        if len(changes) == 1:
            return changes[0].get("content", "")

        engine = ThreeWayMerge()
        base_content = changes[0].get("base", "")
        ours_content = changes[0].get("content", "")

        for i in range(1, len(changes)):
            theirs_content = changes[i].get("content", "")
            result = engine.merge(base_content, ours_content, theirs_content)
            if result.conflicts:
                return None
            ours_content = result.content

        return ours_content


# ============================================================
# Part 3: Three-Way Merge (was merge.py)
# ============================================================

@dataclass
class ConflictMarker:
    """冲突标记"""
    line_number: int
    ours_line: str
    theirs_line: str
    resolution: str         # "auto" | "manual"


@dataclass
class MergeResult:
    """合并结果"""
    content: str
    conflicts: List[ConflictMarker] = field(default_factory=list)
    success: bool = True


def _lcs_lines(a: List[str], b: List[str]) -> List[List[int]]:
    """计算两组行的 LCS 表"""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp


def _backtrack(dp: List[List[int]], a: List[str], b: List[str]) -> List[Tuple[int, int]]:
    """从 LCS 表回溯得到对齐的行对"""
    i, j = len(a), len(b)
    pairs = []
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


@dataclass
class _DiffHunk:
    """表示一个差异区间"""
    base_start: int
    base_end: int
    new_lines: List[str]


def _compute_diff_hunks(base: List[str], modified: List[str]) -> List[_DiffHunk]:
    """计算 base 到 modified 的差异区间"""
    dp = _lcs_lines(base, modified)
    pairs = _backtrack(dp, base, modified)

    hunks = []
    base_to_mod: dict = {}
    for bi, mi in pairs:
        base_to_mod[bi] = mi

    i = 0
    while i < len(base):
        if i in base_to_mod:
            i += 1
        else:
            start = i
            new_lines = []
            while i < len(base) and i not in base_to_mod:
                i += 1
            end = i

            prev_mod_idx = -1
            for bi, mi in pairs:
                if bi < start:
                    prev_mod_idx = mi
            next_mod_idx = len(modified)
            for bi, mi in pairs:
                if bi >= end:
                    next_mod_idx = mi
                    break

            new_lines = modified[prev_mod_idx + 1:next_mod_idx]
            hunks.append(_DiffHunk(base_start=start, base_end=end, new_lines=new_lines))

    return hunks


class ThreeWayMerge:
    """三路合并引擎"""

    def merge(self, base: str, ours: str, theirs: str) -> MergeResult:
        base_lines = base.splitlines(keepends=True)
        ours_lines = ours.splitlines(keepends=True)
        theirs_lines = theirs.splitlines(keepends=True)

        if not base_lines:
            return self._merge_two_way(ours_lines, theirs_lines)

        ours_hunks = _compute_diff_hunks(base_lines, ours_lines)
        theirs_hunks = _compute_diff_hunks(base_lines, theirs_lines)

        return self._apply_merge(base_lines, ours_lines, theirs_lines,
                                 ours_hunks, theirs_hunks)

    def _apply_merge(self, base_lines, ours_lines, theirs_lines,
                     ours_hunks, theirs_hunks) -> MergeResult:
        conflicts = []
        ours_hunks.sort(key=lambda h: h.base_start)
        theirs_hunks.sort(key=lambda h: h.base_start)

        if self._hunks_overlap(ours_hunks, theirs_hunks):
            return self._merge_with_overlaps(
                base_lines, ours_lines, theirs_lines,
                ours_hunks, theirs_hunks
            )

        return self._merge_non_overlapping(
            base_lines, ours_hunks, theirs_hunks
        )

    def _hunks_overlap(self, hunks_a: List[_DiffHunk],
                       hunks_b: List[_DiffHunk]) -> bool:
        for ha in hunks_a:
            for hb in hunks_b:
                if ha.base_start < hb.base_end and hb.base_start < ha.base_end:
                    return True
        return False

    def _merge_non_overlapping(self, base_lines,
                               ours_hunks, theirs_hunks) -> MergeResult:
        all_hunks = []
        for h in ours_hunks:
            all_hunks.append(("ours", h))
        for h in theirs_hunks:
            all_hunks.append(("theirs", h))
        all_hunks.sort(key=lambda x: x[1].base_start)

        result = []
        cursor = 0

        for side, hunk in all_hunks:
            result.extend(base_lines[cursor:hunk.base_start])
            result.extend(hunk.new_lines)
            cursor = hunk.base_end

        result.extend(base_lines[cursor:])

        return MergeResult(content="".join(result), conflicts=[], success=True)

    def _merge_with_overlaps(self, base_lines, ours_lines, theirs_lines,
                             ours_hunks, theirs_hunks) -> MergeResult:
        conflicts = []
        result = []

        boundaries = set()
        boundaries.add(0)
        boundaries.add(len(base_lines))
        for h in ours_hunks:
            boundaries.add(h.base_start)
            boundaries.add(h.base_end)
        for h in theirs_hunks:
            boundaries.add(h.base_start)
            boundaries.add(h.base_end)

        sorted_boundaries = sorted(boundaries)

        for idx in range(len(sorted_boundaries) - 1):
            seg_start = sorted_boundaries[idx]
            seg_end = sorted_boundaries[idx + 1]

            ours_hunk = self._find_hunk_for_range(ours_hunks, seg_start, seg_end)
            theirs_hunk = self._find_hunk_for_range(theirs_hunks, seg_start, seg_end)

            if ours_hunk is None and theirs_hunk is None:
                result.extend(base_lines[seg_start:seg_end])
            elif ours_hunk is not None and theirs_hunk is None:
                if ours_hunk.base_start == seg_start:
                    result.extend(ours_hunk.new_lines)
            elif ours_hunk is None and theirs_hunk is not None:
                if theirs_hunk.base_start == seg_start:
                    result.extend(theirs_hunk.new_lines)
            else:
                resolution = self._auto_resolve(
                    base_lines[seg_start:seg_end],
                    ours_hunk.new_lines,
                    theirs_hunk.new_lines
                )

                if resolution is not None:
                    result.extend(resolution)
                else:
                    line_num = len(result) + 1
                    ours_text = "".join(ours_hunk.new_lines)
                    theirs_text = "".join(theirs_hunk.new_lines)

                    result.append("<<<<<<< OURS\n")
                    result.extend(ours_hunk.new_lines)
                    result.append("=======\n")
                    result.extend(theirs_hunk.new_lines)
                    result.append(">>>>>>> THEIRS\n")

                    conflicts.append(ConflictMarker(
                        line_number=line_num,
                        ours_line=ours_text.rstrip("\n"),
                        theirs_line=theirs_text.rstrip("\n"),
                        resolution="manual",
                    ))

        return MergeResult(
            content="".join(result),
            conflicts=conflicts,
            success=len(conflicts) == 0,
        )

    def _find_hunk_for_range(self, hunks: List[_DiffHunk],
                             start: int, end: int) -> Optional[_DiffHunk]:
        for h in hunks:
            if h.base_start < end and h.base_end > start:
                return h
        return None

    def _auto_resolve(self, base_segment: List[str],
                      ours_new: List[str],
                      theirs_new: List[str]) -> Optional[List[str]]:
        if ours_new == theirs_new:
            return ours_new
        if len(ours_new) == 0 and len(theirs_new) > 0:
            return theirs_new
        if len(theirs_new) == 0 and len(ours_new) > 0:
            return ours_new
        return None

    def _merge_two_way(self, ours_lines: List[str],
                       theirs_lines: List[str]) -> MergeResult:
        dp = _lcs_lines(ours_lines, theirs_lines)
        pairs = _backtrack(dp, ours_lines, theirs_lines)

        conflicts = []
        result = []
        prev_oi, prev_ti = -1, -1

        for oi, ti in pairs:
            ours_only = ours_lines[prev_oi + 1:oi]
            theirs_only = theirs_lines[prev_ti + 1:ti]

            if ours_only and theirs_only:
                line_num = len(result) + 1
                ours_text = "".join(ours_only)
                theirs_text = "".join(theirs_only)
                result.append("<<<<<<< OURS\n")
                result.extend(ours_only)
                result.append("=======\n")
                result.extend(theirs_only)
                result.append(">>>>>>> THEIRS\n")
                conflicts.append(ConflictMarker(
                    line_number=line_num,
                    ours_line=ours_text.rstrip("\n"),
                    theirs_line=theirs_text.rstrip("\n"),
                    resolution="manual",
                ))
            else:
                result.extend(ours_only)
                result.extend(theirs_only)

            result.append(ours_lines[oi])
            prev_oi, prev_ti = oi, ti

        ours_only = ours_lines[prev_oi + 1:]
        theirs_only = theirs_lines[prev_ti + 1:]
        if ours_only and theirs_only:
            line_num = len(result) + 1
            ours_text = "".join(ours_only)
            theirs_text = "".join(theirs_only)
            result.append("<<<<<<< OURS\n")
            result.extend(ours_only)
            result.append("=======\n")
            result.extend(theirs_only)
            result.append(">>>>>>> THEIRS\n")
            conflicts.append(ConflictMarker(
                line_number=line_num,
                ours_line=ours_text.rstrip("\n"),
                theirs_line=theirs_text.rstrip("\n"),
                resolution="manual",
            ))
        else:
            result.extend(ours_only)
            result.extend(theirs_only)

        return MergeResult(
            content="".join(result),
            conflicts=conflicts,
            success=len(conflicts) == 0,
        )


def integrate_with_scheduler(
    filepath: str,
    agent_results: List[dict],
    base_ref: str = "HEAD",
) -> dict:
    """将三路合并集成到 ResultAggregator"""
    from . import merge as _merge_module

    if len(agent_results) == 1:
        content = agent_results[0].get("content", "")
        if content:
            return {
                "merged_content": content,
                "conflicts": [],
                "success": True,
            }

    base_content = _merge_module._git_show(base_ref, filepath)
    if base_content is None:
        base_content = ""

    if len(agent_results) == 0:
        return {
            "merged_content": base_content,
            "conflicts": [],
            "success": True,
        }

    merge_engine = ThreeWayMerge()
    current_ours = agent_results[0].get("content", base_content)
    all_conflicts = []

    for i in range(1, len(agent_results)):
        theirs_content = agent_results[i].get("content", base_content)
        result = merge_engine.merge(base_content, current_ours, theirs_content)

        all_conflicts.extend(result.conflicts)

        if result.success:
            current_ours = result.content
        else:
            current_ours = result.content
        base_content = current_ours

    return {
        "merged_content": current_ours,
        "conflicts": all_conflicts,
        "success": len(all_conflicts) == 0,
    }


# ============================================================
# Part 4: Worker Pool (was worker_pool.py)
# ============================================================

class InstanceStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    STOPPED = "stopped"


@dataclass
class AgentInstance:
    """单个代理实例"""
    instance_id: str
    agent_type: str
    status: InstanceStatus = InstanceStatus.IDLE
    current_task: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    tasks_completed: int = 0
    busy_since: Optional[float] = None

    def assign(self, task_id: str) -> None:
        self.status = InstanceStatus.BUSY
        self.current_task = task_id
        self.busy_since = time.time()

    def release(self) -> None:
        self.status = InstanceStatus.IDLE
        self.current_task = None
        self.busy_since = None
        self.tasks_completed += 1

    def is_stuck(self, timeout: float) -> bool:
        if self.status != InstanceStatus.BUSY or self.busy_since is None:
            return False
        return (time.time() - self.busy_since) > timeout

    @property
    def busy_duration(self) -> float:
        if self.busy_since is None:
            return 0.0
        return time.time() - self.busy_since


@dataclass
class PoolConfig:
    """每种 agent_type 的池配置"""
    min_size: int = 1
    max_size: int = 5
    warmup_timeout: float = 300.0


DEFAULT_POOL_CONFIGS: Dict[str, PoolConfig] = {
    "neiguan_yingzao": PoolConfig(min_size=1, max_size=5),
    "xiaohuangmen": PoolConfig(min_size=1, max_size=5),
    "dongchang_tanshi": PoolConfig(min_size=1, max_size=3),
}


class WorkerPool:
    """代理实例池 -- 管理预热的 agent 槽位"""

    def __init__(self, configs: Optional[Dict[str, PoolConfig]] = None):
        self._configs = configs or dict(DEFAULT_POOL_CONFIGS)
        self._instances: Dict[str, List[AgentInstance]] = {}
        self._lock = asyncio.Lock()
        self._instance_counter = 0
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        async with self._lock:
            for agent_type, config in self._configs.items():
                self._instances[agent_type] = []
                for _ in range(config.min_size):
                    inst = self._create_instance(agent_type)
                    self._instances[agent_type].append(inst)
            self._started = True
        logger.info("WorkerPool started, pre-warmed %d agent types",
                     len(self._configs))

    async def shutdown(self) -> None:
        async with self._lock:
            for agent_type, instances in self._instances.items():
                for inst in instances:
                    inst.status = InstanceStatus.STOPPED
                    inst.current_task = None
            self._started = False
        logger.info("WorkerPool shutdown")

    async def acquire(self, agent_type: str, task_id: str = "unknown") -> Optional[AgentInstance]:
        async with self._lock:
            instances = self._instances.get(agent_type, [])
            config = self._configs.get(agent_type, PoolConfig())

            for inst in instances:
                if inst.status == InstanceStatus.IDLE:
                    inst.assign(task_id)
                    logger.debug("Acquired instance %s for task %s",
                                 inst.instance_id, task_id)
                    return inst

            active = [i for i in instances if i.status != InstanceStatus.STOPPED]
            if len(active) < config.max_size:
                inst = self._create_instance(agent_type)
                inst.assign(task_id)
                instances.append(inst)
                logger.info("Auto-scaled %s -> %d instances (new: %s)",
                            agent_type, len(active) + 1, inst.instance_id)
                return inst

            logger.warning("Pool exhausted for %s (active=%d, max=%d)",
                           agent_type, len(active), config.max_size)
            return None

    def release(self, instance: AgentInstance) -> None:
        instance.release()
        logger.debug("Released instance %s (completed: %d)",
                     instance.instance_id, instance.tasks_completed)

    async def health_check(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        stuck = []
        async with self._lock:
            for agent_type, instances in self._instances.items():
                config = self._configs.get(agent_type, PoolConfig())
                t = timeout or config.warmup_timeout
                for inst in instances:
                    if inst.is_stuck(t):
                        stuck.append({
                            "instance_id": inst.instance_id,
                            "agent_type": inst.agent_type,
                            "task": inst.current_task,
                            "busy_duration": round(inst.busy_duration, 1),
                        })
                        inst.release()

        if stuck:
            logger.warning("Health check recovered %d stuck instances", len(stuck))

        return {
            "stuck_instances": stuck,
            "recovered": len(stuck),
        }

    def stats(self) -> Dict[str, Any]:
        total = 0
        busy = 0
        idle = 0
        tasks_completed = 0

        for instances in self._instances.values():
            for inst in instances:
                if inst.status == InstanceStatus.STOPPED:
                    continue
                total += 1
                if inst.status == InstanceStatus.BUSY:
                    busy += 1
                elif inst.status == InstanceStatus.IDLE:
                    idle += 1
                tasks_completed += inst.tasks_completed

        return {
            "total_instances": total,
            "busy_count": busy,
            "idle_count": idle,
            "tasks_completed": tasks_completed,
            "by_type": self._stats_by_type(),
        }

    def _stats_by_type(self) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = {}
        for agent_type, instances in self._instances.items():
            active = [i for i in instances if i.status != InstanceStatus.STOPPED]
            result[agent_type] = {
                "total": len(active),
                "busy": sum(1 for i in active if i.status == InstanceStatus.BUSY),
                "idle": sum(1 for i in active if i.status == InstanceStatus.IDLE),
                "completed": sum(i.tasks_completed for i in active),
            }
        return result

    def summary(self) -> str:
        s = self.stats()
        return (f"Pool: {s['total_instances']} instances "
                f"({s['idle_count']} idle, {s['busy_count']} busy), "
                f"completed={s['tasks_completed']}")

    def _create_instance(self, agent_type: str) -> AgentInstance:
        self._instance_counter += 1
        inst = AgentInstance(
            instance_id=f"{agent_type}-{self._instance_counter:04d}",
            agent_type=agent_type,
        )
        return inst

    def get_config(self, agent_type: str) -> Optional[PoolConfig]:
        return self._configs.get(agent_type)

    def register_type(self, agent_type: str, config: PoolConfig) -> None:
        self._configs[agent_type] = config
        if agent_type not in self._instances:
            self._instances[agent_type] = []
        logger.info("Registered agent type: %s (min=%d, max=%d)",
                     agent_type, config.min_size, config.max_size)
