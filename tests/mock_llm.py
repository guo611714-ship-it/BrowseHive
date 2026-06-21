"""模拟LLM客户端，用于集成测试"""

from typing import Any, Dict, List, Optional


class MockLLMClient:
    """模拟LLM客户端，支持预设响应和默认回退"""

    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None):
        self._responses: List[Dict[str, Any]] = responses or []
        self._call_count: int = 0
        self.call_history: List[Dict[str, Any]] = []

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """模拟chat调用，按顺序返回预设响应"""
        self.call_history.append({"messages": messages, "tools": tools, "kwargs": kwargs})

        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
            self._call_count += 1
            return response

        self._call_count += 1
        return {
            "content": "Mock response",
            "tool_calls": [],
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "status_code": 200,
        }

    def reset(self) -> None:
        """重置调用计数和历史"""
        self._call_count = 0
        self.call_history = []
