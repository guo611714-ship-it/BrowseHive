"""修复工具 — 向 Agent 注册 fix_manifest 和 submit_fix_manifest 工具

Agent 通过调用这些工具使用并行修复引擎，无需手动编写 Python 代码。
- fix_manifest: 直接提交 FixItem 列表（低级接口）
- submit_fix_manifest: 从数据源自动转换（高级接口）
"""

import logging
from typing import List, Dict, Any, Optional

from agent.tools.tool_registry import tool

logger = logging.getLogger(__name__)

# strategy 别名映射（parallel → full，FixStrategy 用 FULL_PARALLEL）
STRATEGY_ALIASES = {"parallel": "full"}


@tool(
    name="fix_manifest",
    description="【工具调用】提交修复任务清单给并行修复引擎。直接调用此工具，不要写Python代码。引擎自动处理分片、冲突预测、并行调度和结果合并。",
)
async def fix_manifest(
    tasks: list,
    strategy: str = "auto",
) -> dict:
    """提交修复清单给并行修复引擎

    Args:
        tasks: 修复任务列表，每项包含:
            - id: 唯一标识 (必填)
            - file: 文件路径 (必填)
            - description: 修复描述 (必填)
            - agent_type: 代理类型 (必填，如 "neiguan_yingzao")
            - line_start: 起始行号 (可选)
            - line_end: 结束行号 (可选)
            - context: 附加上下文 (可选)
            - priority: 优先级 0=normal 1=high 2=critical (可选)
        strategy: 调度策略 - "auto"(自动) / "parallel"(强制并行) / "serial"(强制串行)

    Returns:
        {"success": bool, "summary": str, "patch": str|dict, "conflicts": list, "details": list}
    """
    from agent.dependencies import engine_ctx
    from fix_engine.manifest import FixManifest, FixItem

    # 获取引擎
    engine = engine_ctx.get()
    if engine is None:
        return {
            "success": False,
            "summary": "引擎未装配",
            "patch": None,
            "conflicts": [],
            "details": [],
        }

    # 验证 tasks
    if not tasks:
        return {
            "success": False,
            "summary": "tasks 不能为空",
            "patch": None,
            "conflicts": [],
            "details": [],
        }

    # 转换为 FixItem
    items = []
    for t in tasks:
        if not all(k in t for k in ("id", "file", "description", "agent_type")):
            return {
                "success": False,
                "summary": f"任务缺少必填字段: {t.get('id', '?')}，需要 id/file/description/agent_type",
                "patch": None,
                "conflicts": [],
                "details": [],
            }
        items.append(FixItem(
            id=t["id"],
            file=t["file"],
            description=t["description"],
            agent_type=t["agent_type"],
            line_start=t.get("line_start"),
            line_end=t.get("line_end"),
            context=t.get("context"),
            priority=t.get("priority", 0),
        ))

    # 构建 manifest（strategy string → FixStrategy enum）
    from fix_engine.manifest import FixStrategy
    strategy_normalized = STRATEGY_ALIASES.get(strategy, strategy)
    try:
        strategy_enum = FixStrategy(strategy_normalized)
    except ValueError:
        strategy_enum = FixStrategy.AUTO
    manifest = FixManifest(tasks=items, strategy=strategy_enum)

    # 执行
    try:
        result = await engine.submit_fix_manifest(manifest)
        return {
            "success": result.success,
            "summary": result.summary,
            "patch": result.patch,
            "conflicts": result.conflicts,
            "details": result.details,
        }
    except Exception as e:
        logger.error("fix_manifest 执行失败: %s", e)
        return {
            "success": False,
            "summary": f"执行异常: {e}",
            "patch": None,
            "conflicts": [],
            "details": [],
        }


@tool(
    name="submit_fix_manifest",
    description="【高级工具】从数据源（stocktake/autoreview/issues）自动转换并提交修复任务。引擎自动处理适配器选择、过滤、冲突预测、并行调度和结果合并。",
)
async def submit_fix_manifest(
    source: str,
    data: Any,
    strategy: str = "auto",
    filter_actionable: bool = True,
) -> dict:
    """从数据源自动转换并提交修复任务

    Args:
        source: 数据源类型 - "stocktake" | "autoreview" | "issues"
        data: 原始数据（dict 或 list，取决于 source）
            - stocktake: results.json 的 dict
            - autoreview: findings 列表
            - issues: GitHub issues 列表
        strategy: 调度策略 - "auto" / "parallel" / "serial" / "file"
        filter_actionable: 是否过滤出可执行任务（默认 True）

    Returns:
        {"success": bool, "summary": str, "source": str, "task_count": int,
         "patch": str|dict, "conflicts": list, "details": list}
    """
    from agent.dependencies import engine_ctx
    from agent.manifest_builder import get_adapter
    from fix_engine.manifest import FixManifest

    # 获取引擎
    engine = engine_ctx.get()
    if engine is None:
        return {
            "success": False,
            "summary": "引擎未装配",
            "source": source,
            "task_count": 0,
            "patch": None,
            "conflicts": [],
            "details": [],
        }

    # 获取适配器
    try:
        adapter = get_adapter(source)
    except ValueError as e:
        return {
            "success": False,
            "summary": str(e),
            "source": source,
            "task_count": 0,
            "patch": None,
            "conflicts": [],
            "details": [],
        }

    # 转换
    try:
        items = adapter.to_fix_items(data)
    except Exception as e:
        logger.error("适配器 %s 转换失败: %s", source, e)
        return {
            "success": False,
            "summary": f"转换失败: {e}",
            "source": source,
            "task_count": 0,
            "patch": None,
            "conflicts": [],
            "details": [],
        }

    # 过滤
    if filter_actionable:
        items = adapter.filter_actionable(items)

    if not items:
        return {
            "success": True,
            "summary": f"source={source}: 无可执行任务",
            "source": source,
            "task_count": 0,
            "patch": None,
            "conflicts": [],
            "details": [],
        }

    # 构建 manifest（strategy string → FixStrategy enum）
    from fix_engine.manifest import FixStrategy
    strategy_normalized = STRATEGY_ALIASES.get(strategy, strategy)
    try:
        strategy_enum = FixStrategy(strategy_normalized)
    except ValueError:
        strategy_enum = FixStrategy.AUTO
    manifest = FixManifest(tasks=items, strategy=strategy_enum)

    # 执行
    try:
        result = await engine.submit_fix_manifest(manifest)
        return {
            "success": result.success,
            "summary": f"source={source}: {result.summary}",
            "source": source,
            "task_count": len(items),
            "patch": result.patch,
            "conflicts": result.conflicts,
            "details": result.details,
        }
    except Exception as e:
        logger.error("submit_fix_manifest 执行失败: %s", e)
        return {
            "success": False,
            "summary": f"执行异常: {e}",
            "source": source,
            "task_count": len(items),
            "patch": None,
            "conflicts": [],
            "details": [],
        }
