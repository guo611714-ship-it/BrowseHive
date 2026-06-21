"""Key 路由轮询测试"""

import pytest
import time
from agent_sse.adapters.key_router import KeyRouter


@pytest.fixture
def router():
    keys = [f"nvapi-key-{i}" for i in range(12)]
    return KeyRouter(keys=keys, mode="global")


def test_initialization(router):
    """测试初始化"""
    assert len(router._keys) == 12
    assert router._mode == "global"


def test_get_next_key(router):
    """测试获取下一个 Key"""
    key = router.get_next_key()
    assert key.startswith("nvapi-key-")


def test_report_success(router):
    """测试报告成功"""
    key = router.get_next_key()
    router.report_success(key)
    stats = router.get_stats(key)
    assert stats["success_count"] > 0


def test_report_failure(router):
    """测试报告失败"""
    key = router.get_next_key()
    router.report_failure(key)
    stats = router.get_stats(key)
    assert stats["failure_count"] > 0


def test_auto_switch_on_high_failure_rate(router):
    """测试高失败率自动切换"""
    key = router.get_next_key()
    # 模拟连续失败
    for _ in range(25):
        router.report_failure(key)
    # 应该自动冷却该 Key
    assert router._is_cooled_down(key)


def test_cooldown_timeout(router):
    """测试冷却超时后恢复"""
    key = router.get_next_key()
    router._cooldown_until[key] = time.time() - 1  # 已过期
    assert not router._is_cooled_down(key)


def test_stats_tracking(router):
    """测试统计数据"""
    # total_count 统计 get_next_key 调用次数，success/failure 统计报告次数
    key = router.get_next_key()
    router.report_success(key)
    router.report_success(key)
    router.report_failure(key)
    stats = router.get_stats(key)
    assert stats["success_count"] == 2
    assert stats["failure_count"] == 1
    assert stats["total_count"] == 1
