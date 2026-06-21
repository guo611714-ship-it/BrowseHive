"""统一错误类型定义 — 结构化错误处理"""

from typing import Any, Dict, Optional


class AgentError(Exception):
    """Agent系统基础错误类"""

    code: str
    message: str
    details: Dict[str, Any]

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ToolNotFoundError(AgentError):
    def __init__(self, tool_name: str):
        super().__init__("TOOL_NOT_FOUND", f"Tool '{tool_name}' not found", {"tool_name": tool_name})


class ToolExecutionError(AgentError):
    def __init__(self, tool_name: str, reason: str):
        super().__init__("TOOL_EXECUTION_ERROR", f"Tool '{tool_name}' failed: {reason}",
                         {"tool_name": tool_name, "reason": reason})


class ModelNotAvailableError(AgentError):
    def __init__(self, model: str, reason: str = ""):
        super().__init__("MODEL_NOT_AVAILABLE", f"Model '{model}' is not available{': ' + reason if reason else ''}",
                         {"model": model, "reason": reason})


class DispatchTimeoutError(AgentError):
    def __init__(self, task_id: str, timeout: float):
        super().__init__("DISPATCH_TIMEOUT", f"Task '{task_id}' timed out after {timeout}s",
                         {"task_id": task_id, "timeout": timeout})


class ConfigError(AgentError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("CONFIG_ERROR", message, details)


class MemoryOperationError(AgentError):
    def __init__(self, operation: str, reason: str):
        super().__init__("MEMORY_ERROR", f"Memory operation '{operation}' failed: {reason}",
                         {"operation": operation, "reason": reason})
