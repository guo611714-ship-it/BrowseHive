"""并行派遣核心 — 辅助函数 + 进度事件 + 模块级调度入口"""

import json
import re
import time
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional
from pathlib import Path
import asyncio
import logging
from dataclasses import dataclass, field

from ...subagents.registry import SubagentRegistry, SubagentSpec
from ...config import AGENT_MEMORY_DIR
from ..tool_registry import get_tool_schemas
from ..todo_tools import get_todo_manager
from ..git_tools import create_backup_branch, git_diff_summary
from .approval import _pending_approvals, _shared_context

# SubagentDispatcher 从独立模块导入（拆分后）
from .dispatcher import SubagentDispatcher  # noqa: F401

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 统一进度事件系统（Claude Code实时输出 + SSE兼容）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class AgentProgressEvent:
    """统一进度事件结构体"""
    timestamp: datetime
    agent_name: str
    step: str        # start | tool_call | complete | failed | handoff
    status: str      # running | success | error
    message: str
    progress: int    # 0~100
    task_id: Optional[str] = None


def claude_code_printer(event: AgentProgressEvent):
    """Claude Code默认进度打印回调（stderr确保可见+彩色+emoji）"""
    import sys
    colors = {"running": "\033[33m", "success": "\033[32m", "error": "\033[31m"}
    emojis = {"start": "\U0001f504", "tool_call": "\U0001f527", "complete": "✅",
              "failed": "❌", "handoff": "\U0001f500"}
    reset = "\033[0m"
    color = colors.get(event.status, "")
    emoji = emojis.get(event.step, "ℹ️")
    msg = f"{color}[{event.timestamp.strftime('%H:%M:%S')}] [{event.agent_name}] {emoji} " \
          f"{event.message} 进度:{event.progress}%{reset}"
    print(msg, file=sys.stderr, flush=True)
    logger.info(f"AGENT_PROGRESS: {event.__dict__}")


# 全局回退 LLM client（当没有注入 model_orchestrator 时使用）
_global_llm_client = None


def _build_tool_schema(spec: SubagentSpec) -> List[Dict]:
    """为子代理生成受限的 OpenAI 工具 schema"""
    allowed = set(spec.allowed_tools)
    all_schemas = get_tool_schemas()
    return [t for t in all_schemas
            if t["function"]["name"] in allowed]


def _safe_str(value, max_len: int = 100) -> str:
    """安全转字符串，不可序列化的值用 repr 兜底"""
    try:
        s = str(value)
    except Exception as e:
        logger.debug("str() failed: %s", e)
        try:
            s = repr(value)
        except Exception as e2:
            logger.debug("repr() failed: %s", e2)
            s = "<unprintable>"
    return s[:max_len]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 简单任务识别 + 结果校验（稳定性增强）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 简单任务关键词（低复杂度、无需多步推理）
_SIMPLE_TASK_PATTERNS = [
    "读取文件", "读文件", "查看文件", "打开文件", "第一行", "前几行",
    "搜索关键词", "查找关键词", "grep", "find",
    "列出文件", "列出目录", "ls", "dir",
    "格式化", "转换格式", "统计行数", "统计字数",
    "简单问答", "简单查询", "命令补全",
    "读取", "查看", "获取",
]


def _is_simple_task(task: str) -> bool:
    """判断是否为简单任务（应快速返回、无需复杂推理）"""
    task_lower = task.lower().strip()
    # 短任务（<50字）且包含简单关键词
    if len(task_lower) < 50:
        for pattern in _SIMPLE_TASK_PATTERNS:
            if pattern in task_lower:
                return True
    return False


def _validate_result(result: str, task: str) -> bool:
    """校验简单任务结果有效性"""
    if not result or not result.strip():
        return False
    result_clean = result.strip()
    # 过滤无效结果模式
    invalid_patterns = [
        "[错误]", "[工具错误]", "[权限拒绝]", "[未知工具]",
        "LLM调用失败", "达到最大工具调用轮数",
        "[超时]", "未配置", "无法派遣",
    ]
    for pattern in invalid_patterns:
        if result_clean.startswith(pattern):
            return False
    # 简单任务结果不应为空或过短（<5字可能是无效响应）
    if len(result_clean) < 3:
        return False
    return True


def _failure_result(agent_type: str, agent_name: str, task: str, summary: str) -> Dict[str, Any]:
    """Factory for standardized failure result dicts.

    Extracted from 3 identical constructions in SubagentDispatcher.
    """
    return {
        "agent_type": agent_type, "agent_name": agent_name, "task": task,
        "status": "failed", "summary": summary,
        "turns_used": 0, "tools_used": [], "tool_calls_log": [],
        "files_modified": [], "backup_branch": None,
        "diff_summary": None, "verification": None,
    }


# ── 全局单例 + 模块级函数 ─────────────────────────────────────────

_dispatcher = None


def get_dispatcher(model_orchestrator=None, team_store=None, tools=None,
                   memory=None, progress_callback=None, skill_router=None) -> SubagentDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SubagentDispatcher(model_orchestrator, team_store, tools, memory, progress_callback, skill_router)
    else:
        # 修补延迟注入的依赖
        if model_orchestrator is not None and _dispatcher.model_orchestrator is None:
            _dispatcher.model_orchestrator = model_orchestrator
        if team_store is not None and _dispatcher.team_store is None:
            _dispatcher.team_store = team_store
        if tools is not None and not _dispatcher.tools:
            _dispatcher.tools = tools
        if memory is not None and _dispatcher.memory is None:
            _dispatcher.memory = memory
        if progress_callback is not None:
            _dispatcher.progress = progress_callback
        if skill_router is not None and _dispatcher.skill_router is None:
            _dispatcher.skill_router = skill_router
    return _dispatcher


async def dispatch_subagent(agent_type: str, task: str,
                            expected_output: str = None,
                            evidence_required: bool = True,
                            context: str = None) -> Dict[str, Any]:
    """派遣子代理的独立函数（供 AgentRunner 调用）"""
    dispatcher = get_dispatcher()
    return await dispatcher.dispatch(
        agent_type=agent_type,
        task=task,
        expected_output=expected_output,
        evidence_required=evidence_required,
        context=context
    )


async def dispatch_parallel(tasks: list, max_concurrent: int = 5) -> list:
    """并行派遣多个子代理（Concurrent模式，供 AgentRunner 调用）"""
    dispatcher = get_dispatcher()
    return await dispatcher.dispatch_parallel(
        tasks=tasks,
        max_concurrent=max_concurrent
    )


async def _select_next_agent(task: str, context: str = "",
                            candidates: list = None) -> str:
    """LLM驱动的speaker选择（内部函数，供调度逻辑调用）"""
    dispatcher = get_dispatcher()
    result = await dispatcher.select_next_agent(
        task=task, context=context, candidates=candidates
    )
    return result or "xiaohuangmen"
