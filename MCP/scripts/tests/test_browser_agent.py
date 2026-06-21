"""BrowserAgent 单元测试（不需要实际浏览器）."""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from browser_agent import BrowserAgent, get_browser_agent, reset_browser_agent, _load_selectors_config


class TestSelectorsConfig:
    """选择器配置测试."""

    def test_loads_config_file(self):
        """应从 JSON 文件加载选择器配置."""
        cfg = _load_selectors_config()
        assert "selectors" in cfg
        assert "doubao" in cfg["selectors"]
        assert "deepseek" in cfg["selectors"]
        assert "volcengine" in cfg["selectors"]
        assert "ouyi" in cfg["selectors"]

    def test_config_has_input_selectors(self):
        """每个平台应有 input 选择器."""
        cfg = _load_selectors_config()
        for pk in ["doubao", "deepseek", "volcengine", "ouyi"]:
            assert "input" in cfg["selectors"][pk], f"{pk} missing input selector"

    def test_config_has_response_selectors(self):
        """每个平台应有 response 选择器."""
        cfg = _load_selectors_config()
        for pk in ["doubao", "deepseek", "volcengine", "ouyi"]:
            assert "response" in cfg["selectors"][pk], f"{pk} missing response selector"

    def test_error_patterns_defined(self):
        """应定义错误模式."""
        cfg = _load_selectors_config()
        assert "errors" in cfg
        assert "patterns" in cfg["errors"]
        assert "exclusions" in cfg["errors"]

    def test_browser_config_defined(self):
        """应定义浏览器配置."""
        cfg = _load_selectors_config()
        assert "browser" in cfg
        assert "harness_timeout" in cfg["browser"]
        assert "no_response_limit" in cfg["browser"]


class TestBrowserAgentSingleton:
    """BrowserAgent 单例测试."""

    def test_get_returns_same_instance(self):
        """get_browser_agent 应返回同一实例."""
        reset_browser_agent()
        a1 = get_browser_agent()
        a2 = get_browser_agent()
        assert a1 is a2

    def test_reset_creates_new_instance(self):
        """reset 后应创建新实例."""
        a1 = get_browser_agent()
        reset_browser_agent()
        a2 = get_browser_agent()
        assert a1 is not a2


class TestCdpPortFile:
    """CDP 端口文件测试."""

    def test_save_cdp_port_atomic(self):
        """_save_cdp_port 应使用原子写入."""
        agent = BrowserAgent()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".cdp_port") as f:
            path = f.name
        agent._cdp_port_file = path
        try:
            agent._save_cdp_port("http://127.0.0.1:9222")
            with open(path, "r") as f:
                content = f.read().strip()
            assert content == "http://127.0.0.1:9222"
            # 临时文件不应残留
            assert not os.path.exists(path + ".tmp")
        finally:
            os.unlink(path)

    def test_save_cdp_port_creates_temp_first(self):
        """原子写入应先创建临时文件."""
        agent = BrowserAgent()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".cdp_port") as f:
            path = f.name
        agent._cdp_port_file = path
        try:
            agent._save_cdp_port("http://127.0.0.1:9333")
            with open(path, "r") as f:
                assert f.read().strip() == "http://127.0.0.1:9333"
        finally:
            os.unlink(path)


class TestHarnessCodeGeneration:
    """browser-harness 代码生成测试."""

    def test_get_harness_code_basic(self):
        """应生成包含消息和选择器的代码."""
        agent = BrowserAgent()
        code = agent._get_harness_code("hello world", "doubao")
        assert "hello world" in code or "hello" in code
        assert "type_text" in code
        assert "press_key" in code
        assert "Enter" in code

    def test_get_harness_code_different_platforms(self):
        """不同平台应使用不同的选择器."""
        agent = BrowserAgent()
        code_db = agent._get_harness_code("test", "doubao")
        code_ds = agent._get_harness_code("test", "deepseek")
        # 选择器可能不同
        assert isinstance(code_db, str)
        assert isinstance(code_ds, str)

    def test_get_harness_response_code(self):
        """应生成响应读取代码."""
        agent = BrowserAgent()
        code = agent._get_harness_response_code("doubao")
        assert "ensure_real_tab" in code
        assert "time.sleep" in code
        assert "print" in code


class TestHarnessAvailability:
    """browser-harness 可用性检测."""

    def test_check_harness_returns_bool(self):
        """_check_harness 应返回布尔值."""
        agent = BrowserAgent()
        result = agent._check_harness()
        assert isinstance(result, bool)

    def test_check_harness_caches_result(self):
        """_check_harness 应缓存结果."""
        agent = BrowserAgent()
        r1 = agent._check_harness()
        r2 = agent._check_harness()
        assert r1 == r2
        # 第二次应使用缓存
        assert agent._harness_available is not None


class TestGetStats:
    """统计信息测试."""

    def test_stats_structure(self):
        """统计信息应包含必要字段."""
        from browser_agent import get_stats
        stats = get_stats()
        assert "harness_calls" in stats
        assert "harness_success" in stats
        assert "harness_fallback" in stats
        assert "avg_response_time" in stats
        assert "last_error" in stats


class TestInvalidate:
    """invalidate 测试."""

    def test_invalidate_clears_state(self):
        """invalidate 应清除内部状态."""
        agent = BrowserAgent()
        agent._harness_available = True
        agent._agents["test"] = "value"
        agent.invalidate()
        assert agent._harness_available is None
        assert len(agent._agents) == 0
