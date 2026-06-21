"""共享测试 fixtures."""

import sys
import os
import asyncio
import pytest

# 确保 core 包可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def fresh_config():
    """每次测试返回全新的 Config 实例."""
    from core.config import Config
    return Config()


@pytest.fixture
def fresh_cache_manager():
    """每次测试返回全新的 CacheManager 实例."""
    from core.cache_manager import CacheManager
    return CacheManager()


@pytest.fixture
def fresh_chat_engine():
    """每次测试返回全新的 ChatEngine 实例（无浏览器依赖）."""
    from core.chat_engine import ChatEngine
    return ChatEngine()
