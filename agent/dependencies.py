"""依赖注入 — ContextVar 管理

所有跨模块共享的上下文变量统一在此管理。
Skill 从这里获取注入的依赖，不直接 import 具体实现。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine_protocol import EngineProtocol

# 引擎实例注入点
# Skill 使用: from agent.dependencies import engine_ctx; engine = engine_ctx.get()
# 启动装配: engine_ctx.set(EngineBridge(engine))
engine_ctx: ContextVar["EngineProtocol"] = ContextVar("engine", default=None)
