"""errors模块测试"""

import pytest
from agent.errors import (
    AgentError, ToolNotFoundError, ToolExecutionError,
    ModelNotAvailableError, DispatchTimeoutError,
    ConfigError, MemoryOperationError,
)


class TestAgentError:
    def test_basic(self):
        e = AgentError("TEST_CODE", "Something failed")
        assert e.code == "TEST_CODE"
        assert e.message == "Something failed"
        assert e.details == {}
        assert "[TEST_CODE] Something failed" in str(e)

    def test_with_details(self):
        e = AgentError("ERR", "msg", {"key": "value"})
        assert e.details == {"key": "value"}

    def test_to_dict(self):
        e = AgentError("ERR", "msg", {"k": "v"})
        d = e.to_dict()
        assert d["error"]["code"] == "ERR"
        assert d["error"]["message"] == "msg"
        assert d["error"]["details"] == {"k": "v"}

    def test_is_exception(self):
        with pytest.raises(AgentError):
            raise AgentError("X", "err")


class TestToolNotFoundError:
    def test_message(self):
        e = ToolNotFoundError("read_file")
        assert "read_file" in e.message
        assert e.code == "TOOL_NOT_FOUND"
        assert e.details["tool_name"] == "read_file"


class TestToolExecutionError:
    def test_message(self):
        e = ToolExecutionError("shell_exec", "permission denied")
        assert "shell_exec" in e.message
        assert "permission denied" in e.message
        assert e.code == "TOOL_EXECUTION_ERROR"


class TestModelNotAvailableError:
    def test_with_reason(self):
        e = ModelNotAvailableError("gpt-4", "rate limited")
        assert "gpt-4" in e.message
        assert "rate limited" in e.message

    def test_without_reason(self):
        e = ModelNotAvailableError("gpt-4")
        assert "gpt-4" in e.message
        assert "not available" in e.message


class TestDispatchTimeoutError:
    def test_message(self):
        e = DispatchTimeoutError("task-123", 60.0)
        assert "task-123" in e.message
        assert "60.0" in e.message
        assert e.details["timeout"] == 60.0


class TestConfigError:
    def test_basic(self):
        e = ConfigError("Missing key")
        assert e.code == "CONFIG_ERROR"


class TestMemoryOperationError:
    def test_message(self):
        e = MemoryOperationError("compress", "lock timeout")
        assert "compress" in e.message
        assert "lock timeout" in e.message
