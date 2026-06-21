# agent_sse/tests/test_hermes_adapter.py
"""Hermes 适配器测试"""

import pytest
from agent_sse.adapters.hermes_adapter import HermesAdapter


@pytest.fixture
def adapter():
    return HermesAdapter()


def test_adapter_initialization(adapter):
    """测试适配器初始化"""
    assert adapter._initialized is False


def test_fallback_enabled(adapter):
    """测试兜底开关"""
    assert adapter.enable_fallback is True


def test_timeout_config(adapter):
    """测试超时配置"""
    assert adapter.timeout == 10


@pytest.mark.asyncio
async def test_chat_returns_error_when_not_initialized(adapter):
    """测试未初始化时返回错误"""
    result = await adapter.chat("hello")
    assert "error" in result
    assert "Hermes" in result


@pytest.mark.asyncio
async def test_execute_tool_returns_error_when_not_initialized(adapter):
    """测试未初始化时工具调用返回错误"""
    result = await adapter.execute_tool("test", {}, {})
    assert "error" in result
