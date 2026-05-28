"""派遣子代理工具"""

from typing import Dict, Any, List
from pathlib import Path
import asyncio

from ..subagents.registry import SubagentRegistry
from .todo_tools import get_todo_manager

# 全局 LLM client（旧接口）
_global_llm_client = None
# 新接口：模型编排器
_model_orchestrator = None
# TeamStore（用于映射 agent_type -> teammate 配置）
_team_store = None


def set_global_llm_client(client):
    """注入全局 LLM 客户端"""
    global _global_llm_client
    _global_llm_client = client


def set_model_orchestrator(orchestrator):
    """注入模型编排器"""
    global _model_orchestrator
    _model_orchestrator = orchestrator


def set_team_store(ts):
    """注入团队配置存储"""
    global _team_store
    _team_store = ts


class SubagentDispatcher:
    """子代理调度器"""

    def __init__(self):
        self.registry = SubagentRegistry
        # 不在这里创建 client，使用注入的全局 client

    async def dispatch(self, agent_type: str, task: str,
                      expected_output: str = None,
                      evidence_required: bool = True,
                      context: str = None) -> Dict[str, Any]:
        """
        派遣子代理执行任务（单轮真实调用）

        Returns:
            子代理的执行结果摘要
        """
        from datetime import datetime

        spec = self.registry.get_spec(agent_type)
        if not spec:
            return {"error": f"Unknown agent type: {agent_type}"}

        # 选择 LLM client（支持多模型路由）
        client = None
        if _model_orchestrator and _team_store:
            # 从 team_store 查找对应 agent_type 的 teammate 配置
            teammates = _team_store.teammates if hasattr(_team_store, 'teammates') else []
            tm = None
            for t in teammates:
                if t.get("agent_type") == agent_type or t.get("name") == agent_type:
                    tm = t
                    break
            if tm:
                client = _model_orchestrator.get_client_for_agent(tm.get("name"), tm)
        if not client:
            client = _global_llm_client

        if not client:
            return {
                "agent_type": agent_type,
                "agent_name": spec.display_name,
                "task": task,
                "status": "failed",
                "summary": "[错误] LLM 客户端未配置，无法派遣子代理。",
                "turns_used": 0
            }

        # 构造子代理系统提示
        system_prompt = f"""\
你是 {spec.display_name}。

【身份说明】
{spec.description}

【工具权限】
你可以使用以下工具：{', '.join(spec.allowed_tools)}。

【任务】
{task}
"""
        if expected_output:
            system_prompt += f"\n【期望输出】{expected_output}\n"
        if evidence_required:
            system_prompt += "\n请在回复中包含关键证据或文件路径。"
        if context:
            system_prompt += f"\n【上下文信息】\n{context}\n"

        # 调用 LLM
        try:
            response = await client.chat(
                messages=[{"role": "user", "content": task}],
                system=system_prompt.strip()
            )
            content = response.get("content", "")
            status = "completed"
        except Exception as e:
            content = f"LLM调用失败: {e}"
            status = "failed"

        result = {
            "agent_type": agent_type,
            "agent_name": spec.display_name,
            "task": task,
            "status": status,
            "summary": content,
            "turns_used": 1
        }

        if expected_output:
            result["expected_output"] = expected_output

        return result

    def list_available_agents(self) -> List[Dict]:
        """列出所有可用的子代理"""
        return self.registry.list_available()


# 全局单例
_dispatcher = None

def get_dispatcher() -> SubagentDispatcher:
    """获取全局 Dispatcher"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SubagentDispatcher()
    return _dispatcher


# 工具函数（供 tools/__init__.py 导出）

async def dispatch_subagent(agent_type: str, task: str,
                           expected_output: str = None,
                           evidence_required: bool = True,
                           context: str = None) -> Dict[str, Any]:
    """
    派遣子代理的独立函数

    这是实际被 AgentRunner 调用的工具函数
    """
    dispatcher = get_dispatcher()
    return await dispatcher.dispatch(
        agent_type=agent_type,
        task=task,
        expected_output=expected_output,
        evidence_required=evidence_required,
        context=context
    )
