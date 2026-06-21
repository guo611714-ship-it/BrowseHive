"""agent/tool_loop.py 测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.tool_loop import run_tool_loop


@pytest.mark.asyncio
async def test_simple_reply_no_tools():
    """无工具调用，直接返回LLM回复"""
    mock_client = AsyncMock()
    mock_client.chat = AsyncMock(return_value={"content": "Hello!", "tool_calls": []})

    reply, completed, logs = await run_tool_loop(
        client=mock_client,
        messages=[{"role": "user", "content": "Hi"}],
        system_prompt="You are helpful.",
        tools_schema=None,
        execute_tool=None,
    )
    assert reply == "Hello!"
    assert completed is True
    assert logs == []


@pytest.mark.asyncio
async def test_tool_call_and_response():
    """LLM调用工具，返回结果后继续"""
    mock_client = AsyncMock()
    # First call: tool call (format: {id, name, arguments})
    mock_client.chat = AsyncMock(side_effect=[
        {"content": "", "tool_calls": [{"id": "t1", "name": "test_tool", "arguments": {"x": 1}}]},
        # Second call: final reply
        {"content": "Done!", "tool_calls": []},
    ])

    async def mock_execute(name, args):
        return {"result": "ok"}

    reply, completed, logs = await run_tool_loop(
        client=mock_client,
        messages=[{"role": "user", "content": "Use tool"}],
        system_prompt="test",
        tools_schema=[{"type": "function", "function": {"name": "test_tool"}}],
        execute_tool=mock_execute,
    )
    assert reply == "Done!"
    assert len(logs) == 1
    assert logs[0]["tool"] == "test_tool"


@pytest.mark.asyncio
async def test_max_turns_limit():
    """超过最大轮次停止"""
    mock_client = AsyncMock()
    # Always return tool calls
    mock_client.chat = AsyncMock(return_value={
        "content": "", "tool_calls": [{"id": "t1", "name": "test_tool", "arguments": {}}]
    })

    async def mock_execute(name, args):
        return {"result": "ok"}

    reply, completed, logs = await run_tool_loop(
        client=mock_client,
        messages=[{"role": "user", "content": "Loop"}],
        system_prompt="test",
        tools_schema=[{"type": "function", "function": {"name": "test_tool"}}],
        execute_tool=mock_execute,
        max_turns=2,
    )
    assert completed is False  # Stopped due to max turns
    assert len(logs) == 2
