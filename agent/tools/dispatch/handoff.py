"""代理交接模式 — Handoff 函数"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


async def dispatch_with_handoff(start_agent: str, task: str,
                                 handoff_rules: dict = None,
                                 max_handoffs: int = 5,
                                 expected_output: str = None) -> dict:
    """Handoff模式（供 AgentRunner 调用）"""
    from .parallel import get_dispatcher
    dispatcher = get_dispatcher()
    return await dispatcher.dispatch_with_handoff(
        start_agent=start_agent, task=task,
        handoff_rules=handoff_rules,
        max_handoffs=max_handoffs,
        expected_output=expected_output
    )
