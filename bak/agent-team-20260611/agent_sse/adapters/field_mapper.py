# agent_sse/adapters/field_mapper.py
"""字段映射转换器"""

from typing import Dict, Any, List


class FieldMapper:
    """新旧系统字段映射"""

    @staticmethod
    def map_chat_request(old_request: Dict[str, Any]) -> Dict[str, Any]:
        """映射对话请求字段"""
        return {
            "prompt": old_request.get("message", ""),
            "session_id": old_request.get("user_id", ""),
            "system": old_request.get("system", ""),
            "tools": old_request.get("tools", []),
            "stream": old_request.get("stream", False),
        }

    @staticmethod
    def map_chat_response(hermes_response: Dict[str, Any]) -> Dict[str, Any]:
        """映射对话响应字段"""
        return {
            "content": hermes_response.get("response", ""),
            "finish_reason": hermes_response.get("stop_reason", ""),
            "usage": hermes_response.get("usage", {}),
            "tool_calls": hermes_response.get("tool_calls", []),
        }

    @staticmethod
    def map_tool_request(old_request: Dict[str, Any]) -> Dict[str, Any]:
        """映射工具调用请求字段"""
        return {
            "tool_name": old_request.get("tool", ""),
            "parameters": old_request.get("args", {}),
            "context": old_request.get("context", {}),
        }

    @staticmethod
    def map_tool_response(hermes_response: Dict[str, Any]) -> Dict[str, Any]:
        """映射工具调用响应字段

        覆盖所有已知格式:
        - Hermes 格式: {"status", "output", "error"}
        - Agent Team 格式: {"result", "code", "error"}
        - 原始格式: {"content", "finish_reason"}
        - 扁平字符串: 直接作为 result
        """
        # 格式 1: Hermes 标准格式
        if "status" in hermes_response:
            status = hermes_response.get("status", "error")
            error_msg = ""
            if hermes_response.get("error"):
                if isinstance(hermes_response["error"], dict):
                    error_msg = hermes_response["error"].get("message", "")
                else:
                    error_msg = str(hermes_response["error"])
            return {
                "result": hermes_response.get("output", ""),
                "code": 0 if status == "success" else 1,
                "error": error_msg,
            }

        # 格式 2: Agent Team / 已映射格式
        if "result" in hermes_response:
            return {
                "result": hermes_response["result"],
                "code": hermes_response.get("code", 0),
                "error": hermes_response.get("error", ""),
            }

        # 格式 3: 对话响应格式 (tool_calls 场景)
        if "content" in hermes_response:
            return {
                "result": hermes_response.get("content", ""),
                "code": 0,
                "error": hermes_response.get("error", ""),
            }

        # 格式 4: 扁平字符串
        if isinstance(hermes_response, str):
            return {
                "result": hermes_response,
                "code": 0,
                "error": "",
            }

        # 格式 5: 未知格式，序列化返回
        import json
        return {
            "result": json.dumps(hermes_response, ensure_ascii=False, default=str),
            "code": 0,
            "error": "",
        }

    @staticmethod
    def map_sse_chunk(hermes_chunk: Dict[str, Any]) -> Dict[str, Any]:
        """映射 SSE 流式字段"""
        return {
            "content": hermes_chunk.get("delta", ""),
            "tool_calls": hermes_chunk.get("tool_calls", []),
            "usage": hermes_chunk.get("usage", {}),
            "finish_reason": hermes_chunk.get("stop_reason", ""),
        }

    @staticmethod
    def map_sse_error(error_message: str, code: int = 500) -> str:
        """映射 SSE 错误格式（合法 JSON）"""
        import json
        return f"data: {json.dumps({'error': error_message, 'code': code})}\n\n"
