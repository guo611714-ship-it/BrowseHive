"""Agent Runner：单轮执行编排、工具调用循环"""

import asyncio
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
import json


class AgentRunner:
    """单轮执行器"""

    def __init__(self, tools: Dict[str, Callable], max_workers: int = 5):
        """
        初始化 Runner

        Args:
            tools: 工具字典 {name: callable}
            max_workers: 并发工作线程数
        """
        self.tools = tools
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def _is_concurrency_safe(self, tool_name: str) -> bool:
        """判断工具是否并发安全"""
        # 并发安全的工具列表
        safe_tools = {
            "read_file", "web_fetch", "glob", "grep", "load_skill",
            "dispatch_subagent", "list_teammates"
        }
        return tool_name in safe_tools

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行单个工具（异步）"""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            func = self.tools[tool_name]
            loop = asyncio.get_event_loop()

            # 判断是否为异步函数（coroutine function）
            if asyncio.iscoroutinefunction(func):
                # 异步函数直接在当前事件循环中 await
                result = await func(**arguments)
            else:
                # 同步函数扔进线程池
                result = await loop.run_in_executor(
                    self.executor,
                    func,
                    **arguments
                )
            return result
        except Exception as e:
            return {"error": str(e)}

    async def execute_tool_sequence(self, tool_calls: List[Dict[str, Any]]) -> List[Any]:
        """
        执行工具调用序列
        同一帧内的并发安全工具会并行执行
        """
        # 分组：连续的并发安全工具合并为一个 batch
        batches = []
        current_batch = []

        for call in tool_calls:
            tool_name = call.get("name", "")
            if self._is_concurrency_safe(tool_name):
                current_batch.append(call)
            else:
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                batches.append([call])  # 非并发安全工具单独成批

        if current_batch:
            batches.append(current_batch)

        # 按批次顺序执行
        results = []
        for batch in batches:
            if len(batch) > 1:
                # 并发执行 batch 内的工具
                tasks = [
                    self.execute_tool(call["name"], call.get("arguments", {}))
                    for call in batch
                ]
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
            else:
                # 顺序执行
                call = batch[0]
                result = await self.execute_tool(call["name"], call.get("arguments", {}))
                results.append(result)

        return results

    def shutdown(self):
        """关闭执行器"""
        self.executor.shutdown(wait=True)
