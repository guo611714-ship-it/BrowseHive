# agent_sse/tests/test_routing_config.py
"""路由配置测试"""

import pytest
from agent_sse.config.routing_config import (
    ROUTING_RULES,
    KEY_ROTATION_MODE,
    KEY_ROTATION_RULES,
    get_api_keys,
)


def test_routing_rules_structure():
    """测试路由规则结构"""
    assert "agent_model_map" in ROUTING_RULES
    assert "complexity" in ROUTING_RULES
    assert isinstance(ROUTING_RULES["agent_model_map"], dict)
    assert isinstance(ROUTING_RULES["complexity"], dict)


def test_key_rotation_mode():
    """测试 Key 轮询模式"""
    assert KEY_ROTATION_MODE == "global"


def test_key_rotation_rules():
    """测试 Key 轮询规则"""
    assert "max_failure_rate" in KEY_ROTATION_RULES
    assert "max_usage_rate" in KEY_ROTATION_RULES
    assert "cooldown_seconds" in KEY_ROTATION_RULES
    assert "min_calls_for_stats" in KEY_ROTATION_RULES


def test_get_api_keys():
    """测试获取 API Key"""
    keys = get_api_keys()
    assert isinstance(keys, list)
    assert len(keys) > 0
    assert all(k.startswith("nvapi-") for k in keys)
