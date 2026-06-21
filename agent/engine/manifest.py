"""Task Manifest + Smart Sharder — 标准化任务格式 + 按文件依赖自动分片

Phase 1 of Autonomous Parallel Fix Mesh.
Skills submit TaskManifest, the engine handles scheduling.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum
from pathlib import Path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Task Manifest — 标准化任务格式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class SchedulingStrategy(str, Enum):
    AUTO = "auto"          # 引擎决定并/串行
    PARALLEL = "parallel"  # 强制并行
    SERIAL = "serial"      # 强制串行
    FILE_SERIAL = "file"   # 同文件串行，不同文件并行


@dataclass
class FixTask:
    """单个修复任务"""
    task_id: str
    description: str
    files: List[str]                    # 涉及的文件路径
    agent_type: str = "neiguan_yingzao" # 执行代理
    priority: TaskPriority = TaskPriority.NORMAL
    context: Optional[str] = None       # 额外上下文
    expected_output: Optional[str] = None
    timeout: float = 300.0
    depends_on: List[str] = field(default_factory=list)  # 依赖的 task_id 列表
    metadata: Dict[str, Any] = field(default_factory=dict)
    line_start: Optional[int] = None    # 修复起始行（冲突检测用）
    line_end: Optional[int] = None      # 修复结束行（冲突检测用）

    @property
    def file_set(self) -> Set[str]:
        return set(self.files)

    def to_dispatch_args(self) -> Dict[str, Any]:
        """转换为 dispatch_parallel 需要的格式"""
        args = {
            "agent_type": self.agent_type,
            "task": self.description,
            "timeout": self.timeout,
        }
        if self.expected_output:
            args["expected_output"] = self.expected_output
        if self.context:
            args["context"] = self.context
        return args


@dataclass
class TaskManifest:
    """任务清单 — skills 的标准输入格式"""
    tasks: List[FixTask]
    strategy: SchedulingStrategy = SchedulingStrategy.AUTO
    priority: TaskPriority = TaskPriority.NORMAL
    context: Optional[str] = None       # 全局上下文（代码快照等）
    max_concurrent: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    @property
    def file_count(self) -> int:
        return len(set(f for t in self.tasks for f in t.files))

    def summary(self) -> str:
        return (f"Manifest: {self.task_count} tasks, "
                f"{self.file_count} files, "
                f"strategy={self.strategy.value}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Smart Sharder — 按文件依赖自动分片
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class Shard:
    """一个分片：可并行执行的任务组"""
    shard_id: int
    tasks: List[FixTask]
    files: Set[str]
    reason: str  # 分片原因说明

    @property
    def task_count(self) -> int:
        return len(self.tasks)


class SmartSharder:
    """智能分片器 — 分析任务依赖，生成最优执行计划

    分片规则：
    1. 不同文件的任务 → 可并行（放入同一 shard）
    2. 同文件的任务 → 检查行号区间，无重叠仍可并行
    3. 有显式 depends_on 的 → 按依赖拓扑排序
    4. 冲突项 → 降级到下一个 shard（串行执行）
    """

    def __init__(self, predictor: Optional["ConflictPredictor"] = None) -> None:
        """
        Args:
            predictor: ConflictPredictor 实例，用于冲突预测
        """
        self.predictor = predictor

    def shard(self, manifest: TaskManifest) -> List[Shard]:
        """将 manifest 拆分为可执行的 shard 列表"""
        if manifest.strategy == SchedulingStrategy.PARALLEL:
            return self._force_parallel(manifest)
        if manifest.strategy == SchedulingStrategy.SERIAL:
            return self._force_serial(manifest)
        if manifest.strategy == SchedulingStrategy.FILE_SERIAL:
            # 同文件任务由 ConflictPredictor 分离到不同 shard（当前依赖预测器）
            return self._auto_shard(manifest)

        # AUTO 策略：智能分片
        return self._auto_shard(manifest)

    def _auto_shard(self, manifest: TaskManifest) -> List[Shard]:
        """自动分片：按依赖拓扑 + 文件冲突分组"""
        tasks = list(manifest.tasks)
        shards = []
        shard_id = 0

        # Step 1: 处理有显式依赖的任务（拓扑排序）
        independent, dependent = self._split_by_dependencies(tasks)

        # Step 2: 对独立任务进行文件级分片
        file_groups = self._group_by_file(independent)

        # Step 3: 在每个文件组内，检查行号重叠
        for group_tasks in file_groups:
            if len(group_tasks) <= 1:
                # 单任务或空组，直接成 shard
                if group_tasks:
                    shards.append(Shard(
                        shard_id=shard_id,
                        tasks=group_tasks,
                        files=group_tasks[0].file_set,
                        reason="single task / no file overlap"
                    ))
                    shard_id += 1
            else:
                # 多任务同文件，检查是否冲突
                sub_shards = self._resolve_file_conflicts(group_tasks, shard_id)
                shards.extend(sub_shards)
                shard_id += len(sub_shards)

        # Step 4: 合并无文件重叠的 shard（提升并行度）
        shards = self._merge_non_overlapping(shards, shard_id)

        # Step 5: 追加依赖任务为后续 shard
        if dependent:
            dep_shards = self._order_dependent(dependent, shard_id + len(shards))
            shards.extend(dep_shards)

        return shards

    def _split_by_dependencies(self, tasks: List[FixTask]):
        """分离有/无显式依赖的任务"""
        task_ids = {t.task_id for t in tasks}
        dependent = []
        independent = []
        for t in tasks:
            if t.depends_on and any(d in task_ids for d in t.depends_on):
                dependent.append(t)
            else:
                independent.append(t)
        return independent, dependent

    def _group_by_file(self, tasks: List[FixTask]) -> List[List[FixTask]]:
        """按文件分组：同一文件的任务归为一组"""
        file_map: Dict[str, List[FixTask]] = {}
        for t in tasks:
            for f in t.files:
                file_map.setdefault(f, []).append(t)

        # 去重：一个任务可能出现在多个文件组中
        seen = set()
        groups = []
        for f, group in file_map.items():
            key = frozenset(t.task_id for t in group)
            if key not in seen:
                seen.add(key)
                groups.append(group)
        return groups

    def _resolve_file_conflicts(self, tasks: List[FixTask],
                                 start_id: int) -> List[Shard]:
        """同文件任务：检查冲突，分组为可并行的子 shard"""
        if len(tasks) <= 1:
            return [Shard(
                shard_id=start_id,
                tasks=tasks,
                files=tasks[0].file_set if tasks else set(),
                reason="single task"
            )]

        # 用冲突预测器判断
        if self.predictor:
            conflict_groups = self.predictor.predict_conflicts(tasks)
        else:
            # 无预测器：同文件视为可能冲突，拆成独立 shard
            conflict_groups = [[t] for t in tasks]

        shards = []
        for i, group in enumerate(conflict_groups):
            shards.append(Shard(
                shard_id=start_id + i,
                tasks=group,
                files=set(f for t in group for f in t.files),
                reason=f"conflict group {i+1}/{len(conflict_groups)}"
            ))
        return shards

    def _merge_non_overlapping(self, shards: List[Shard],
                                start_id: int) -> List[Shard]:
        """合并文件集合不重叠的 shard（提升并行度）"""
        if len(shards) <= 1:
            return shards

        merged = []
        used = set()

        for i, s1 in enumerate(shards):
            if i in used:
                continue
            current_tasks = list(s1.tasks)
            current_files = set(s1.files)

            for j, s2 in enumerate(shards):
                if j <= i or j in used:
                    continue
                if not current_files & s2.files:
                    # 无文件重叠，合并
                    current_tasks.extend(s2.tasks)
                    current_files |= s2.files
                    used.add(j)

            merged.append(Shard(
                shard_id=start_id + len(merged),
                tasks=current_tasks,
                files=current_files,
                reason="merged non-overlapping"
            ))

        return merged

    def _order_dependent(self, tasks: List[FixTask],
                          start_id: int) -> List[Shard]:
        """为有依赖的任务排序（简单拓扑）"""
        # 按 depends_on 深度排序
        depth_map = {}
        task_map = {t.task_id: t for t in tasks}

        def get_depth(t: FixTask) -> int:
            if t.task_id in depth_map:
                return depth_map[t.task_id]
            if not t.depends_on:
                depth_map[t.task_id] = 0
                return 0
            max_dep = max(
                get_depth(task_map[d])
                for d in t.depends_on
                if d in task_map
            ) if any(d in task_map for d in t.depends_on) else 0
            depth_map[t.task_id] = max_dep + 1
            return max_dep + 1

        for t in tasks:
            get_depth(t)

        # 按深度分层
        depth_groups: Dict[int, List[FixTask]] = {}
        for t in tasks:
            d = depth_map.get(t.task_id, 0)
            depth_groups.setdefault(d, []).append(t)

        shards = []
        for d in sorted(depth_groups.keys()):
            group = depth_groups[d]
            shards.append(Shard(
                shard_id=start_id + len(shards),
                tasks=group,
                files=set(f for t in group for f in t.files),
                reason=f"dependency depth {d}"
            ))
        return shards

    def _force_parallel(self, manifest: TaskManifest) -> List[Shard]:
        """强制并行：所有任务放入一个 shard"""
        return [Shard(
            shard_id=0,
            tasks=manifest.tasks,
            files=set(f for t in manifest.tasks for f in t.files),
            reason="forced parallel"
        )]

    def _force_serial(self, manifest: TaskManifest) -> List[Shard]:
        """强制串行：每个任务一个 shard"""
        return [
            Shard(
                shard_id=i,
                tasks=[t],
                files=t.file_set,
                reason="forced serial"
            )
            for i, t in enumerate(manifest.tasks)
        ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工厂函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_task(task_id: str, description: str, files: List[str], **kwargs) -> FixTask:
    """快捷创建 FixTask"""
    return FixTask(task_id=task_id, description=description, files=files, **kwargs)


def create_manifest(tasks: List[FixTask], **kwargs) -> TaskManifest:
    """快捷创建 TaskManifest"""
    return TaskManifest(tasks=tasks, **kwargs)
