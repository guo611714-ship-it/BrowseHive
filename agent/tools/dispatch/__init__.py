"""dispatch 包 — 向后兼容导出

保持 `from agent.tools.dispatch_tools import X` 等旧导入继续工作。
"""

from .parallel import (
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
    # 内部辅助（供外部直接引用时使用）
    _build_tool_schema,
    _safe_str,
    _is_simple_task,
    _validate_result,
    _global_llm_client,
    _dispatcher,
)

from .approval import (
    # 审批
    _pending_approvals,
    _approve_task,
    get_pending_approvals,
    # 共享上下文
    _shared_context,
    shared_context_set,
    shared_context_get,
    shared_context_list,
    # 知识库
    _kb_query_sync,
    kb_search,
)

from .handoff import (
    dispatch_with_handoff,
)

from .refine import (
    dispatch_iterative_refine,
    get_progress_dashboard,
    get_browser_dashboard,
)

# 重新导出 dispatch_with_approval（它是一个 async 函数，定义在 parallel.py 的
# SubagentDispatcher 类中，同时有模块级 wrapper）
# 注意：原文件中 dispatch_with_approval 既是类方法也是模块级函数，
# 模块级函数在 parallel.py 中没有定义，需要在这里补一个 wrapper。
import asyncio as _asyncio


async def dispatch_with_approval(agent_type: str, task: str,
                                  approval_reason: str = "",
                                  timeout: float = 300.0,
                                  **kwargs) -> dict:
    """Human-in-the-loop审批（供 AgentRunner 调用）"""
    dispatcher = get_dispatcher()
    return await dispatcher.dispatch_with_approval(
        agent_type=agent_type, task=task,
        approval_reason=approval_reason,
        timeout=timeout, **kwargs
    )


# 供 `from agent.tools.dispatch_tools import *` 使用
__all__ = [
    # 进度事件
    "AgentProgressEvent",
    "claude_code_printer",
    # 核心
    "SubagentDispatcher",
    "get_dispatcher",
    "dispatch_subagent",
    "dispatch_parallel",
    "_select_next_agent",
    # Handoff
    "dispatch_with_handoff",
    # Approval
    "dispatch_with_approval",
    "_approve_task",
    "get_pending_approvals",
    "_pending_approvals",
    # Shared context
    "shared_context_set",
    "shared_context_get",
    "shared_context_list",
    "_shared_context",
    # Knowledge base
    "kb_search",
    "_kb_query_sync",
    # Dashboard
    "get_progress_dashboard",
    "get_browser_dashboard",
    # Iterative refine
    "dispatch_iterative_refine",
    # Internal helpers (backward compat)
    "_build_tool_schema",
    "_safe_str",
    "_is_simple_task",
    "_validate_result",
    "_global_llm_client",
    "_dispatcher",
]
