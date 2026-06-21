"""测试执行工具 — 典簿 + 内官监"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 工具定义（供 dispatcher 注册）
TEST_TOOLS = {
    "run_tests": {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "执行 pytest 测试。典簿职责：校验执行，跑测试+覆盖率分析。",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_file": {"type": "string", "description": "测试文件路径"},
                    "test_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要运行的测试函数名列表（可选）"
                    },
                    "target_file": {"type": "string", "description": "被测业务文件路径"}
                },
                "required": ["test_file"]
            }
        }
    },
    "full_stack_verify": {
        "type": "function",
        "function": {
            "name": "full_stack_verify",
            "description": "全栈验收：pytest + 覆盖率 + lint。内官监职责：工程执行与验收。",
            "parameters": {
                "type": "object",
                "properties": {
                    "business_file": {"type": "string", "description": "业务代码文件路径"},
                    "test_file": {"type": "string", "description": "测试文件路径"},
                    "test_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "测试函数名列表（可选）"
                    },
                    "task_description": {"type": "string", "description": "任务描述"},
                    "group_id": {"type": "string", "description": "分组ID（可选）"}
                },
                "required": ["business_file"]
            }
        }
    }
}


async def run_tests(test_file: str, test_names: Optional[List[str]] = None,
                    target_file: str = "") -> Dict[str, Any]:
    """执行 pytest 测试（典簿）"""
    try:
        from ..subagents.dianbu_verify import DianbuAgent
        agent = DianbuAgent()
        test_json = {"test_file": test_file, "content": ""}
        result = await agent.execute(test_json, target_file, test_names or [])
        return result
    except Exception as e:
        logger.error(f"run_tests failed: {e}")
        return {"error": str(e)}


async def full_stack_verify(business_file: str, test_file: Optional[str] = None,
                            test_names: Optional[List[str]] = None,
                            task_description: str = "",
                            group_id: Optional[str] = None) -> Dict[str, Any]:
    """全栈验收（内官监）"""
    try:
        from ..subagents.neiguangjian import NeiguanjianAgent
        agent = NeiguanjianAgent()
        return await agent.execute(
            business_file=business_file,
            test_file=test_file,
            test_names=test_names,
            task_description=task_description,
            group_id=group_id
        )
    except Exception as e:
        logger.error(f"full_stack_verify failed: {e}")
        return {"error": str(e)}


# 工具函数映射（供 dispatcher 调用）
TEST_TOOL_FUNCTIONS = {
    "run_tests": run_tests,
    "full_stack_verify": full_stack_verify,
}
