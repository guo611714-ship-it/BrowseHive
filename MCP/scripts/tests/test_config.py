"""Config 单元测试 + 热重载."""

import asyncio
import json
import os
import tempfile
import time
import pytest
from core.config import Config, DEFAULT_CONFIG


class TestConfig:
    """Config 基础测试."""

    def test_default_values(self):
        """Config 应加载默认值."""
        cfg = Config()
        assert cfg.get("max_retries") == DEFAULT_CONFIG["max_retries"]
        assert cfg.get("send_timeout") == 30
        assert cfg.get("cdp_default_port") == 9222

    def test_set_and_get(self):
        """set 后 get 应返回新值."""
        cfg = Config()
        cfg.set("custom_key", "custom_value")
        assert cfg.get("custom_key") == "custom_value"

    def test_get_default(self):
        """get 不存在的 key 应返回默认值."""
        cfg = Config()
        assert cfg.get("nonexistent", "fallback") == "fallback"
        assert cfg.get("nonexistent") is None

    def test_update(self):
        """update 应批量更新配置."""
        cfg = Config()
        cfg.update({"a": 1, "b": 2})
        assert cfg.get("a") == 1
        assert cfg.get("b") == 2

    def test_cache_properties(self):
        """缓存属性应返回正确值."""
        cfg = Config()
        assert cfg.cache_ttl == 300
        assert cfg.cache_max == 100
        assert cfg.tool_ttl == 60
        assert cfg.context_ttl == 600
        assert cfg.context_max == 30

    def test_rate_limit_properties(self):
        """限流属性应返回正确值."""
        cfg = Config()
        assert cfg.rate_limit_interval == 3
        assert cfg.rate_limit_window == 60
        assert cfg.rate_limit_max == 10

    def test_retry_properties(self):
        """重试属性应返回正确值."""
        cfg = Config()
        assert cfg.max_retries == 3
        assert cfg.retry_delay == 2
        assert cfg.retry_budget_max == 20
        assert cfg.retry_budget_window == 60


class TestConfigHotReload:
    """配置热重载测试."""

    def test_watch_file_change(self):
        """监听配置文件变化并自动重载."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"max_retries": 5, "send_timeout": 60}, f)
            path = f.name

        try:
            cfg = Config()
            watcher = cfg.start_watching(path)

            # 初始值应从文件加载
            assert cfg.get("max_retries") == 5
            assert cfg.get("send_timeout") == 60

            # 修改文件
            time.sleep(0.1)  # 确保 mtime 变化
            with open(path, "w") as f:
                json.dump({"max_retries": 10, "send_timeout": 120}, f)

            # 等待 watcher 检测
            watcher.check_now()
            assert cfg.get("max_retries") == 10
            assert cfg.get("send_timeout") == 120

            watcher.stop()
        finally:
            os.unlink(path)

    def test_watch_nonexistent_file(self):
        """监听不存在的文件不应崩溃."""
        cfg = Config()
        watcher = cfg.start_watching("/nonexistent/path.json")
        assert watcher is not None
        watcher.stop()

    def test_stop_watching(self):
        """stop_watching 应停止监听."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"max_retries": 5}, f)
            path = f.name

        try:
            cfg = Config()
            watcher = cfg.start_watching(path)
            assert watcher.is_running
            watcher.stop()
            assert not watcher.is_running
        finally:
            os.unlink(path)
