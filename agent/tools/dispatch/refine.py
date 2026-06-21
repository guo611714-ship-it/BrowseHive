"""结果优化/迭代模式 — 迭代精炼 + 进度看板 + 浏览器看板

迭代精炼核心逻辑从 dispatcher.py 拆出，作为独立函数。
"""

import re
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


async def dispatch_iterative_refine_impl(dispatcher, writer_agent: str,
                                          reviewer_agent: str, task: str,
                                          max_rounds: int = 3,
                                          quality_threshold: float = 0.8) -> Dict[str, Any]:
    """多轮迭代精炼核心逻辑（writer-reviewer 循环）

    Args:
        dispatcher: SubagentDispatcher 实例
        writer_agent: 写作者 agent 类型
        reviewer_agent: 审核者 agent 类型
        task: 任务描述
        max_rounds: 最大迭代轮数
        quality_threshold: 质量阈值（审核通过的最低分）

    Returns:
        最终精炼结果
    """
    history = []
    current_content = ""

    for round_num in range(max_rounds):
        # Writer 生成/修改
        writer_context = f"第{round_num + 1}轮。"
        if history:
            last_review = history[-1].get("review", "")
            writer_context += f"上一轮审核反馈：{last_review[:500]}"

        writer_result = await dispatcher.dispatch(
            agent_type=writer_agent,
            task=task if round_num == 0 else f"根据审核反馈修改：\n{task}",
            context=writer_context
        )

        current_content = writer_result.get("summary", "")

        # Reviewer 审核
        review_task = f"审核以下内容的质量，给出0-1分数和改进建议：\n\n{current_content[:2000]}"
        reviewer_result = await dispatcher.dispatch(
            agent_type=reviewer_agent,
            task=review_task,
            expected_output="格式：分数: 0.XX\n建议: ..."
        )

        review_text = reviewer_result.get("summary", "")

        # 解析分数（支持多种格式：0.85, .85, 9/10, 80%, 85分）
        score = _parse_review_score(review_text)

        history.append({
            "round": round_num + 1,
            "content": current_content[:500],
            "review": review_text[:500],
            "score": score
        })

        # 检查是否达标
        if score >= quality_threshold:
            return {
                "status": "completed",
                "summary": current_content,
                "final_score": score,
                "rounds_used": round_num + 1,
                "history": history
            }

    # 超过最大轮数
    return {
        "status": "max_rounds",
        "summary": current_content,
        "final_score": history[-1]["score"] if history else 0.0,
        "rounds_used": max_rounds,
        "history": history
    }


def _parse_review_score(review_text: str) -> float:
    """从审核文本中解析质量分数

    支持格式：0.85, .85, 9/10, 80%, 85分
    """
    score_patterns = [
        (r'(?:分数|score)[:\s]*(\d+)\s*/\s*(\d+)', 'fraction'),   # 分数: 9/10
        (r'(?:分数|score)[:\s]*(\d+)%', 'percent'),                # 分数: 80%
        (r'(\d*\.?\d+)\s*分', 'decimal_100'),                      # 85分 -> 0.85
        (r'(?:分数|score)[:\s]*(\d*\.?\d+)', 'decimal'),           # 分数: 0.85
    ]
    for pattern, fmt in score_patterns:
        m = re.search(pattern, review_text, re.IGNORECASE)
        if m:
            groups = m.groups()
            if fmt == 'fraction':
                return float(groups[0]) / float(groups[1])
            elif fmt == 'percent':
                return float(groups[0]) / 100.0
            elif fmt == 'decimal_100':
                return float(groups[0]) / 100.0
            else:  # decimal
                val = float(groups[0])
                return val if val <= 1.0 else val / 10.0
    return 0.0


# ── 模块级 wrapper 函数（供 AgentRunner 调用）──────────────────────


async def dispatch_iterative_refine(writer_agent: str, reviewer_agent: str,
                                     task: str, max_rounds: int = 3,
                                     quality_threshold: float = 0.8) -> dict:
    """多轮迭代精炼（Group Chat模式，供 AgentRunner 调用）"""
    from .parallel import get_dispatcher
    dispatcher = get_dispatcher()
    return await dispatcher.dispatch_iterative_refine(
        writer_agent=writer_agent, reviewer_agent=reviewer_agent,
        task=task, max_rounds=max_rounds,
        quality_threshold=quality_threshold
    )


def get_progress_dashboard() -> dict:
    """进度看板（供 AgentRunner 调用）"""
    from .parallel import get_dispatcher
    dispatcher = get_dispatcher()
    return dispatcher.get_progress_dashboard()


def get_browser_dashboard() -> dict:
    """浏览器操作看板 — 整合检查点/监控/操作统计"""
    from ..browser_tools import _operation_log, _checkpoint_mgr
    from ..browser.browser_pool import get_monitor, get_browser_pool

    # 操作统计
    total_ops = len(_operation_log)
    success_ops = sum(1 for o in _operation_log if o.get("code", 0) < 300)
    failed_ops = total_ops - success_ops
    avg_latency = (sum(o.get("cost_ms", 0) for o in _operation_log) / total_ops) if total_ops else 0

    # 按工具分类
    tool_stats = {}
    for op in _operation_log:
        tool = op.get("tool", "unknown")
        if tool not in tool_stats:
            tool_stats[tool] = {"count": 0, "success": 0, "failed": 0, "total_ms": 0}
        tool_stats[tool]["count"] += 1
        if op.get("code", 0) < 300:
            tool_stats[tool]["success"] += 1
        else:
            tool_stats[tool]["failed"] += 1
        tool_stats[tool]["total_ms"] += op.get("cost_ms", 0)

    # 检查点统计
    sessions = _checkpoint_mgr.list_sessions()

    # 实例池状态
    pool = get_browser_pool()

    # 告警
    monitor = get_monitor()
    alerts = monitor.get_alerts(limit=10)

    return {
        "summary": {
            "total_operations": total_ops,
            "success": success_ops,
            "failed": failed_ops,
            "success_rate": f"{success_ops/total_ops*100:.1f}%" if total_ops else "N/A",
            "avg_latency_ms": round(avg_latency),
        },
        "tool_stats": tool_stats,
        "sessions": len(sessions),
        "pool": pool.get_stats(),
        "alerts": alerts,
    }
