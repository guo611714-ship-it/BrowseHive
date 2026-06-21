"""派遣子代理工具 — 向后兼容入口

原始实现已拆分为：
  agent/tools/dispatch/parallel.py   — 并行派遣核心
  agent/tools/dispatch/handoff.py    — 代理交接模式
  agent/tools/dispatch/approval.py   — 审批流程 + 共享上下文
  agent/tools/dispatch/refine.py     — 结果优化/迭代模式

本文件保留所有公共符号的 re-export，确保旧导入路径继续工作。
"""

from .dispatch import (
    # 进度事件
    AgentProgressEvent,
    claude_code_printer,
    # 核心
    SubagentDispatcher,
    get_dispatcher,
    dispatch_subagent,
    dispatch_parallel,
    _select_next_agent,
    # Handoff
    dispatch_with_handoff,
    # Approval
    dispatch_with_approval,
    _approve_task,
    get_pending_approvals,
    # Shared context
    shared_context_set,
    shared_context_get,
    shared_context_list,
    _shared_context,
    # Knowledge base
    kb_search,
    _kb_query_sync,
    # Dashboard
    get_progress_dashboard,
    get_browser_dashboard,
    # Iterative refine
    dispatch_iterative_refine,
    # Internal helpers (backward compat)
    _build_tool_schema,
    _safe_str,
    _is_simple_task,
    _validate_result,
    _global_llm_client,
    _dispatcher,
    _pending_approvals,
)

__all__ = [
    "AgentProgressEvent",
    "claude_code_printer",
    "SubagentDispatcher",
    "get_dispatcher",
    "dispatch_subagent",
    "dispatch_parallel",
    "_select_next_agent",
    "dispatch_with_handoff",
    "dispatch_with_approval",
    "_approve_task",
    "get_pending_approvals",
    "shared_context_set",
    "shared_context_get",
    "shared_context_list",
    "_shared_context",
    "kb_search",
    "_kb_query_sync",
    "get_progress_dashboard",
    "get_browser_dashboard",
    "dispatch_iterative_refine",
    "_build_tool_schema",
    "_safe_str",
    "_is_simple_task",
    "_validate_result",
    "_global_llm_client",
    "_dispatcher",
    "_pending_approvals",
]
