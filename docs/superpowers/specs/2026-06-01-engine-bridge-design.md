# Engine Bridge 设计规范

**日期**: 2026-06-01
**状态**: 待审批
**目标**: 将 Parallel Fix Engine 接入 Agent Team，使 Skill 通过 Protocol 抽象调用引擎，零耦合

## 1. 背景

当前 Agent Team 和 Parallel Fix Engine 是两条独立的调用路径：
- Skill → `quick_fix()` → Engine → `dispatch_parallel()` → 子代理
- Skill → `AgentTeam.process_message()` → `dispatch_tools` → 子代理

引擎是 Agent Team 的一个"库调用"，不是常驻服务。目标是将引擎升级为 Skill 的标准并行调度入口，同时保留未来独立服务的能力。

## 2. 架构

```
Skill Layer
  │  from agent.dependencies import engine_ctx
  │  engine = engine_ctx.get()
  │  result = await engine.submit_fix_manifest(manifest)
  │
  │  ContextVar 注入
  ▼
Agent Team (宿主)
  │  startup:
  │    engine = ParallelFixEngine()
  │    bridge = EngineBridge(engine)
  │    engine_ctx.set(bridge)
  │
  │  agent/engine_protocol.py — EngineProtocol (抽象)
  │  agent/engine_bridge.py   — EngineBridge (实现)
  │  agent/dependencies.py    — engine_ctx (注入点)
  │
  ▼
fix_engine (独立包)
  ParallelFixEngine
  → SmartSharder → Scheduler → dispatch → Merge
  预留: serve() → 未来可启动为独立 HTTP 服务
```

## 3. 文件清单

| 文件 | 行数(估) | 职责 |
|------|---------|------|
| `fix_engine/manifest.py` | ~80 | FixManifest + FixItem + FixStrategy + ConflictResolution |
| `fix_engine/result.py` | ~30 | FixResult dataclass |
| `agent/engine_protocol.py` | ~25 | EngineProtocol 定义 |
| `agent/engine_bridge.py` | ~30 | EngineBridge 实现 |
| `agent/dependencies.py` | ~6 | engine_ctx ContextVar |
| `agent/__init__.py` | +1 | 导出 engine_ctx |

## 4. 核心接口

### 4.1 FixManifest (fix_engine/manifest.py)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class FixStrategy(Enum):
    AUTO = "auto"             # 引擎自行决定并/串行
    FULL_PARALLEL = "full"    # 强制全部并行
    FILE_SERIAL = "file"      # 同文件串行，不同文件并行
    FULL_SERIAL = "serial"    # 完全串行

class ConflictResolution(Enum):
    AUTO_MERGE = "auto_merge"       # 自动合并非冲突修改
    FAIL_FAST = "fail"              # 发现冲突立即停止
    SERIAL_RERUN = "serial_rerun"   # 冲突项串行重跑（默认）

@dataclass
class FixItem:
    id: str                                    # 唯一标识
    file: str                                  # 文件路径
    description: str                           # 修复描述
    agent_type: str                            # 执行的 Agent 类型
    line_start: Optional[int] = None           # 修复起始行（冲突检测用）
    line_end: Optional[int] = None             # 修复结束行
    context: Optional[str] = None              # 附加上下文
    priority: int = 0                          # 优先级（越大越高）
    metadata: dict = field(default_factory=dict)

@dataclass
class FixManifest:
    tasks: list[FixItem]
    strategy: FixStrategy = FixStrategy.AUTO
    conflict: ConflictResolution = ConflictResolution.SERIAL_RERUN
    repo_snapshot: Optional[str] = None        # git commit hash
    max_workers: Optional[int] = None          # 最大并行 Agent 数
    metadata: dict = field(default_factory=dict)
```

### 4.2 FixResult (fix_engine/result.py)

```python
from dataclasses import dataclass, field

@dataclass
class FixResult:
    success: bool
    summary: str                               # 人类可读摘要
    patch: Optional[str] = None                # 最终 patch
    conflicts: list[dict] = field(default_factory=list)  # 未解决冲突
    details: list[dict] = field(default_factory=list)    # 每项修复详情
```

### 4.3 EngineProtocol (agent/engine_protocol.py)

```python
from typing import Protocol, Any
from fix_engine.manifest import FixManifest
from fix_engine.result import FixResult

class EngineProtocol(Protocol):
    async def submit_fix_manifest(self, manifest: FixManifest) -> FixResult: ...
```

### 4.4 EngineBridge (agent/engine_bridge.py)

```python
from fix_engine.manifest import FixManifest
from fix_engine.result import FixResult
from .engine_protocol import EngineProtocol

class EngineBridge:
    def __init__(self, engine):
        self._engine = engine

    async def submit_fix_manifest(self, manifest: FixManifest) -> FixResult:
        raw = await self._engine.submit(manifest)
        return FixResult(
            success=raw.get("status") == "success",
            summary=raw.get("status", "unknown"),
            patch=raw.get("merged", {}).get("merged_files"),
            conflicts=raw.get("merged", {}).get("conflicts", []),
            details=raw.get("results", []),
        )
```

### 4.5 依赖注入 (agent/dependencies.py)

```python
from contextvars import ContextVar
from agent.engine_protocol import EngineProtocol

engine_ctx: ContextVar[EngineProtocol] = ContextVar('engine')
```

## 5. 启动装配

```python
# agent/loop.py 或 main 入口
from fix_engine import ParallelFixEngine
from agent.engine_bridge import EngineBridge
from agent.dependencies import engine_ctx

engine = ParallelFixEngine()
bridge = EngineBridge(engine)
engine_ctx.set(bridge)
```

## 6. Skill 改造模式

```python
# 改造前:
from agent.engine import quick_fix
result = await quick_fix(tasks)

# 改造后:
from agent.dependencies import engine_ctx
from fix_engine.manifest import FixManifest, FixItem

engine = engine_ctx.get()
manifest = FixManifest(tasks=[FixItem(...)])
result = await engine.submit_fix_manifest(manifest)
if result.success:
    apply(result.patch)
```

## 7. 测试策略

```python
# 测试时注入 mock
class MockEngine:
    async def submit_fix_manifest(self, manifest) -> FixResult:
        return FixResult(success=True, summary="ok", patch="...")

engine_ctx.set(MockEngine())
```

Protocol 是结构化子类型，MockEngine 不需要显式继承 EngineProtocol。

## 8. 未来演进

| 阶段 | 变化 | Skill 影响 |
|------|------|-----------|
| 当前 | 进程内嵌入 | 零 |
| Phase 2 | 加 `analyze()` 到 Protocol | 仅新增方法，无破坏 |
| Phase 3 | 启动 `serve()` 独立服务 | HttpEngineBridge 实现同一 Protocol，Skill 零改动 |
| Phase 4 | 分布式 Worker Pool | 引擎内部变化，Skill 零改动 |

## 9. 约束

- Protocol 当前只有一个方法 `submit_fix_manifest`，不加 `analyze()` (YAGNI)
- FixResult/FixManifest 是结构化 dataclass，不是 Dict
- engine_ctx 放在 dependencies.py，不放在 engine_bridge.py
- 引擎内部变化不影响 Skill（通过 Protocol 隔离）
