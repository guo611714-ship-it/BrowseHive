"""agent.engine -- 自进化并行修复引擎 (Autonomous Parallel Fix Mesh)

Phase 1: 标准化 Task Manifest + 智能分片 + 规则冲突预测 + 文件感知调度
Phase 2: 常驻服务 + TaskQueue + SSE进度 + CLI入口
Phase 3: Worker Pool 预热实例池 + 分布式跨节点
Phase 4: 自进化指标 + ML冲突预测 + 策略自动调整 + gRPC接口

用法:
    from agent.engine import quick_fix, ParallelFixEngine, TaskManifest, FixTask

    # 快速修复（一行）
    result = await quick_fix([
        {"task_id": "fix-1", "description": "...", "files": ["a.py"]},
    ])

    # 完整控制
    engine = ParallelFixEngine()
    manifest = TaskManifest(tasks=[...], strategy="auto")
    result = await engine.submit(manifest)

    # 仅分析（不执行）
    plan = engine.analyze(manifest)

    # 常驻服务模式
    from agent.engine import EngineService
    service = EngineService()
    await service.start()
    result = await service.submit(manifest)

    # 分布式模式
    from agent.engine import DistributedWorkerPool
    pool = DistributedWorkerPool.from_config("nodes.json")

    # HTTP API 模式
    from agent.engine import EngineHTTPServer, EngineHTTPClient
    server = EngineHTTPServer(port=8001)
    client = EngineHTTPClient("http://localhost:8001")
"""

from .manifest import (
    TaskManifest, FixTask, TaskPriority, SchedulingStrategy,
    SmartSharder, Shard, create_task, create_manifest,
)
from .predictor import (
    ConflictPredictor, ConflictPrediction,
    MLConflictPredictor, MLConflictRecord,
    ConflictFeatures, ConflictPredictionResult, FeatureExtractor, LinearModel, MLModel,
    EvolutionMetrics,
)
from .scheduler import (
    EnhancedScheduler, ResultAggregator,
    ThreeWayMerge, MergeResult, ConflictMarker, integrate_with_scheduler,
    WorkerPool, AgentInstance, InstanceStatus, PoolConfig, DEFAULT_POOL_CONFIGS,
)
from .fix_engine import (
    ParallelFixEngine, get_engine, quick_fix,
)
from .task_queue import TaskQueue, TaskEntry, TaskStatus
from .progress_sse import ProgressBroadcaster, SSEEvent, get_broadcaster
from .grpc_service import (
    EngineService, EngineHTTPServer, EngineHTTPClient, EngineClientError,
    manifest_from_dict, manifest_to_dict,
)
from .distributed import (
    DistributedWorkerPool, NodeConfig, NodeRegistry,
    FileHashRouter, CrossNodeDispatcher,
)

# Phase 3+4: 可选依赖，导入失败不影响核心功能
try:
    from .metrics import (
        TaskRecord, ConflictRecord, AggregatedMetrics, EvolutionReport,
        create_metrics, RETENTION_DAYS,
    )
except ImportError:
    TaskRecord = None
    ConflictRecord = None
    AggregatedMetrics = None
    EvolutionReport = None
    create_metrics = None
    RETENTION_DAYS = None

__all__ = [
    # Phase 1: 核心类
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
    "ThreeWayMerge",
    "MergeResult",
    "ConflictMarker",
    "integrate_with_scheduler",
    # Phase 2: 服务化
    "EngineService",
    "EngineHTTPServer",
    "EngineHTTPClient",
    "EngineClientError",
    "manifest_from_dict",
    "manifest_to_dict",
    "TaskQueue",
    "TaskEntry",
    "TaskStatus",
    "ProgressBroadcaster",
    "SSEEvent",
    "get_broadcaster",
    # Phase 3: Worker Pool
    "WorkerPool",
    "AgentInstance",
    "InstanceStatus",
    "PoolConfig",
    "DEFAULT_POOL_CONFIGS",
    "DistributedWorkerPool",
    "NodeConfig",
    "NodeRegistry",
    "FileHashRouter",
    "CrossNodeDispatcher",
    # Phase 4: 自进化
    "EvolutionMetrics",
    "MLConflictPredictor",
    "MLConflictRecord",
    "ConflictFeatures",
    "ConflictPredictionResult",
    "FeatureExtractor",
    "LinearModel",
    "MLModel",
    "TaskRecord",
    "ConflictRecord",
    "AggregatedMetrics",
    "EvolutionReport",
    "create_metrics",
    "RETENTION_DAYS",
    # 便捷函数
    "get_engine",
    "quick_fix",
    "create_task",
    "create_manifest",
]
