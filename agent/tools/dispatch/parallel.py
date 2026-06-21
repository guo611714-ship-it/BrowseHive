"""并行派遣核心 — SubagentDispatcher 类 + 进度事件 + 工具调度

Thin facade that re-exports everything from parallel_core for backward compatibility.
"""

from .parallel_core import (  # noqa: F401
    # 数据类 + 进度
    AgentProgressEvent,
    claude_code_printer,
    # 核心调度器
    SubagentDispatcher,
    get_dispatcher,
    # 模块级派遣函数
    dispatch_subagent,
    dispatch_parallel,
    _select_next_agent,
    # 内部辅助
    _build_tool_schema,
    _safe_str,
    _is_simple_task,
    _validate_result,
    _global_llm_client,
    _dispatcher,
    # 常量
    _SIMPLE_TASK_PATTERNS,
)

__all__ = [
    "AgentProgressEvent",
    "claude_code_printer",
    "SubagentDispatcher",
    "get_dispatcher",
    "dispatch_subagent",
    "dispatch_parallel",
    "_select_next_agent",
    "_build_tool_schema",
    "_safe_str",
    "_is_simple_task",
    "_validate_result",
    "_global_llm_client",
    "_dispatcher",
    "_SIMPLE_TASK_PATTERNS",
]
