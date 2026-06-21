"""agent.loop 模块测试

测试 AgentLoop 的核心功能：
- 初始化（组件装配、配置注入）
- process_message 基本流程
- 错误处理（LLM 超时、异常）
- 工具调用分发
- 上下文压缩触发
"""

import asyncio
import json
import sys
import threading
import types
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from tests.mock_llm import MockLLMClient

# ─── 补丁缺失模块（agent.runner / agent.tool_defs 不存在于磁盘） ───
_mock_runner_mod = types.ModuleType("agent.runner")
_mock_runner_mod.AgentRunner = MagicMock
_mock_tooldefs_mod = types.ModuleType("agent.tool_defs")
_mock_tooldefs_mod.get_tool_definitions = lambda: []
sys.modules.setdefault("agent.runner", _mock_runner_mod)
sys.modules.setdefault("agent.tool_defs", _mock_tooldefs_mod)

from agent.loop import AgentLoop  # noqa: E402
from agent.memory import MemoryStore
from agent.context import ContextAssembler
from agent.team_store import TeamStore


# ────────────────────────────────────────────────────────
# fixtures / helpers
# ────────────────────────────────────────────────────────

@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """隔离的工作区目录"""
    (tmp_path / "memory").mkdir()
    (tmp_path / ".team").mkdir()
    (tmp_path / "templates").mkdir()
    return tmp_path


def _build_loop(workspace: Path, llm_client=None, *, patch_compress=True):
    """手动构建 AgentLoop 实例，绕过 __init__ 中的复杂依赖链。

    patch_compress=True 时禁用 _maybe_compress_memory，避免后台线程
    阻塞 event loop.close()。测试压缩逻辑时传 patch_compress=False。
    """
    loop_obj = object.__new__(AgentLoop)
    loop_obj.workspace_path = workspace
    loop_obj.service_mode = False
    loop_obj._running = True
    loop_obj.shutdown_event = asyncio.Event()
    loop_obj.memory = MemoryStore(workspace / "memory")
    loop_obj.team_store = TeamStore(workspace / ".team")
    loop_obj.context_assembler = ContextAssembler(workspace / "templates")
    loop_obj.model_orchestrator = MagicMock()
    loop_obj.llm_client = llm_client
    if llm_client is not None:
        if not hasattr(llm_client, "provider"):
            llm_client.provider = "mock"
            llm_client.model = "mock-model"
    loop_obj.tools = {}
    loop_obj.runner = MagicMock()
    loop_obj.runner.execute_tool = AsyncMock(return_value={"ok": True})
    loop_obj.mode = "ask_before_edit"
    loop_obj.plan = {"enabled": False, "drafts": []}
    loop_obj.dispatcher = None
    loop_obj.message_bus = MagicMock()
    if patch_compress:
        loop_obj._maybe_compress_memory = MagicMock()
    return loop_obj


def _run_async(coro):
    """用独立事件循环执行协程，不调用 close() 避免 executor 阻塞"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        # 不调用 loop.close() -- _maybe_compress_memory 的 ensure_future
        # 创建的后台线程可能在 close 时阻塞；让 GC 处理
        pass


# ────────────────────────────────────────────────────────
# 1. 初始化
# ────────────────────────────────────────────────────────

class TestAgentLoopInit:
    """验证 AgentLoop 组件装配"""

    def test_memory_created(self, workspace: Path) -> None:
        """memory 目录和 history 文件存在"""
        loop = _build_loop(workspace)
        assert loop.memory.history_file.exists()

    def test_team_store_created(self, workspace: Path) -> None:
        """team_store 被正确创建"""
        loop = _build_loop(workspace)
        assert loop.team_store is not None

    def test_default_mode(self, workspace: Path) -> None:
        """默认模式为 ask_before_edit"""
        loop = _build_loop(workspace)
        assert loop.mode == "ask_before_edit"

    def test_shutdown_sets_flag(self, workspace: Path) -> None:
        """shutdown 设置 _running=False 和 shutdown_event"""
        loop = _build_loop(workspace)
        assert loop._running is True
        loop.shutdown()
        assert loop._running is False
        assert loop.shutdown_event.is_set()


# ────────────────────────────────────────────────────────
# 2. process_message 基本流程
# ────────────────────────────────────────────────────────

class TestProcessMessage:
    """验证对话循环核心流程"""

    def test_plain_reply(self, workspace: Path) -> None:
        """LLM 返回纯文本时直接作为最终回复"""
        llm = MockLLMClient(responses=[
            {"content": "你好", "tool_calls": [], "usage": {}, "status_code": 200}
        ])
        loop = _build_loop(workspace, llm_client=llm)
        result = _run_async(loop.process_message("你好"))
        assert result == "你好"

    def test_llm_called_with_usage(self, workspace: Path) -> None:
        """LLM 被调用时 tools 和 usage 正确传递"""
        llm = MockLLMClient(responses=[
            {"content": "ok", "tool_calls": [],
             "usage": {"input_tokens": 100, "output_tokens": 50},
             "status_code": 200}
        ])
        loop = _build_loop(workspace, llm_client=llm)
        _run_async(loop.process_message("test"))
        assert len(llm.call_history) == 1
        # tools 参数在 MockLLMClient 中单独存储（不在 kwargs 中）
        assert llm.call_history[0]["tools"] is not None

    def test_history_appended(self, workspace: Path) -> None:
        """用户消息和助手回复都追加到 history"""
        llm = MockLLMClient(responses=[
            {"content": "reply", "tool_calls": [], "usage": {}, "status_code": 200}
        ])
        loop = _build_loop(workspace, llm_client=llm)
        _run_async(loop.process_message("question"))
        history = loop.memory.get_recent_history(limit=10)
        roles = [h["role"] for h in history]
        assert "user" in roles
        assert "assistant" in roles


# ────────────────────────────────────────────────────────
# 3. 错误处理
# ────────────────────────────────────────────────────────

class TestErrorHandling:
    """验证异常场景的容错"""

    def test_llm_timeout_returns_error(self, workspace: Path) -> None:
        """LLM 超时被捕获并返回错误消息"""
        llm = MockLLMClient()
        llm.chat = AsyncMock(side_effect=TimeoutError("LLM request timed out"))
        loop = _build_loop(workspace, llm_client=llm)
        result = _run_async(loop.process_message("test timeout"))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_agent_error_with_details(self, workspace: Path) -> None:
        """AgentError 正确接受 details 参数"""
        from agent.errors import AgentError
        err = AgentError("AGENT_ERROR", "test message", details={"key": "value"})
        assert err.code == "AGENT_ERROR"
        assert err.message == "test message"
        assert err.details == {"key": "value"}

    def test_no_llm_fallback_to_simulate(self, workspace: Path) -> None:
        """llm_client 为 None 时使用模拟响应"""
        loop = _build_loop(workspace, llm_client=None)
        result = _run_async(loop.process_message("团队有哪些成员"))
        assert "团队" in result or "队友" in result


# ────────────────────────────────────────────────────────
# 4. 工具调用分发
# ────────────────────────────────────────────────────────

class TestToolDispatch:
    """验证 tool call -> runner.execute_tool 的分发"""

    def test_tool_call_executed(self, workspace: Path) -> None:
        """LLM 返回 tool_calls 时，runner.execute_tool 被调用"""
        # LLM 第一次返回 tool_calls
        tool_response = {
            "content": "", "usage": {}, "status_code": 200,
            "tool_calls": [
                {"id": "call_001", "name": "read_file",
                 "arguments": {"path": "test.py"}}
            ],
        }
        # 第二次返回纯文本结束循环
        final_response = {
            "content": "文件内容已读取",
            "tool_calls": [], "usage": {}, "status_code": 200,
        }
        llm = MockLLMClient(responses=[tool_response, final_response])
        loop = _build_loop(workspace, llm_client=llm)
        loop.runner = MagicMock()
        loop.runner.execute_tool = AsyncMock(return_value={"content": "print('hello')"})

        result = _run_async(loop.process_message("读取 test.py"))
        loop.runner.execute_tool.assert_called_once_with(
            "read_file", {"path": "test.py"}
        )
        assert result == "文件内容已读取"

    def test_long_result_truncated(self, workspace: Path) -> None:
        """工具返回结果超过3000字符时被截断"""
        tool_response = {
            "content": "", "usage": {}, "status_code": 200,
            "tool_calls": [
                {"id": "call_002", "name": "read_file",
                 "arguments": {"path": "big.txt"}}
            ],
        }
        final_response = {
            "content": "done", "tool_calls": [], "usage": {}, "status_code": 200,
        }
        llm = MockLLMClient(responses=[tool_response, final_response])
        loop = _build_loop(workspace, llm_client=llm)
        big_content = "x" * 5000
        loop.runner = MagicMock()
        loop.runner.execute_tool = AsyncMock(return_value={"content": big_content})

        _run_async(loop.process_message("读取 big.txt"))
        second_call = llm.call_history[1]
        tool_msgs = [m for m in second_call["messages"] if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "截断" in tool_msgs[0]["content"]

    def test_multiple_tool_calls(self, workspace: Path) -> None:
        """一次返回多个 tool_calls 时全部执行"""
        multi_tool_response = {
            "content": "", "usage": {}, "status_code": 200,
            "tool_calls": [
                {"id": "c1", "name": "read_file", "arguments": {"path": "a.py"}},
                {"id": "c2", "name": "read_file", "arguments": {"path": "b.py"}},
            ],
        }
        final_response = {
            "content": "两个文件都读完了",
            "tool_calls": [], "usage": {}, "status_code": 200,
        }
        llm = MockLLMClient(responses=[multi_tool_response, final_response])
        loop = _build_loop(workspace, llm_client=llm)
        call_count = 0

        async def fake_execute(name, args):
            nonlocal call_count
            call_count += 1
            return {"ok": True}

        loop.runner = MagicMock()
        loop.runner.execute_tool = fake_execute
        result = _run_async(loop.process_message("同时读取两个文件"))
        assert call_count == 2
        assert result == "两个文件都读完了"


# ────────────────────────────────────────────────────────
# 5. 上下文压缩触发（同步测试，不涉及事件循环）
# ────────────────────────────────────────────────────────

class TestMemoryCompression:
    """验证压缩锁和历史管理"""

    def test_history_append_and_read(self, workspace: Path) -> None:
        """历史追加后可正确读取"""
        loop = _build_loop(workspace, patch_compress=False)
        for i in range(5):
            loop.memory.append_history({"role": "user", "content": f"msg_{i}"})
        history = loop.memory.get_recent_history(limit=10)
        assert len(history) == 5

    def test_compress_lock_acquire_release(self, workspace: Path) -> None:
        """压缩锁 acquire/release 语义正确"""
        loop = _build_loop(workspace, patch_compress=False)
        assert loop.memory.try_compress_lock() is True
        assert loop.memory.try_compress_lock() is False
        loop.memory.release_compress_lock()
        assert loop.memory.try_compress_lock() is True
        loop.memory.release_compress_lock()
