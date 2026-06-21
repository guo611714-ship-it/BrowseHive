"""Worker Pool -- backward-compatible re-export from scheduler module."""

from .scheduler import (
    WorkerPool,
    AgentInstance,
    InstanceStatus,
    PoolConfig,
    DEFAULT_POOL_CONFIGS,
)

__all__ = [
    "WorkerPool",
    "AgentInstance",
    "InstanceStatus",
    "PoolConfig",
    "DEFAULT_POOL_CONFIGS",
]
