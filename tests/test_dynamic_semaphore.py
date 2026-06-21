"""动态信号量测试"""

import asyncio
import time
import pytest
from unittest.mock import patch

from agent.dynamic_semaphore import get_system_load, DynamicSemaphore


def test_get_system_load_returns_dict():
    """测试get_system_load返回字典"""
    result = get_system_load()
    assert isinstance(result, dict)
    assert "cpu_percent" in result
    assert "memory_percent" in result
    assert "load_avg" in result


def test_get_system_load_without_psutil():
    """测试psutil不可用时返回基本指标"""
    with patch.dict("sys.modules", {"psutil": None}):
        result = get_system_load()
        assert result["cpu_percent"] == 0
        assert result["memory_percent"] == 0
        assert result["load_avg"] == [0, 0, 0]


def test_dynamic_semaphore_initial_values():
    """测试DynamicSemaphore初始值"""
    sem = DynamicSemaphore(initial=5, min_value=1, max_value=10)
    assert sem.value == 5
    stats = sem.get_stats()
    assert stats["current_value"] == 5
    assert stats["initial"] == 5
    assert stats["min"] == 1
    assert stats["max"] == 10
    assert stats["adjustments"] == 0
    assert stats["ups"] == 0
    assert stats["downs"] == 0


def test_dynamic_semaphore_custom_values():
    """测试自定义参数"""
    sem = DynamicSemaphore(initial=3, min_value=2, max_value=8)
    assert sem.value == 3
    stats = sem.get_stats()
    assert stats["min"] == 2
    assert stats["max"] == 8


def test_acquire_release():
    """测试acquire/release基本功能"""
    sem = DynamicSemaphore(initial=2, min_value=1, max_value=5)
    sem._last_adjust_time = time.time()  # 禁用调整
    # 获取信号量
    sem.acquire()
    sem.acquire()
    # 释放信号量
    sem.release()
    sem.release()
    # 确保没有异常
    assert sem.value == 2


def test_acquire_release_multiple():
    """测试多次acquire/release"""
    sem = DynamicSemaphore(initial=3, min_value=1, max_value=10)
    sem._last_adjust_time = time.time()  # 禁用调整
    # 连续获取
    for _ in range(3):
        sem.acquire()
    # 连续释放
    for _ in range(3):
        sem.release()
    # 确保状态正确
    assert sem.value == 3
    stats = sem.get_stats()
    assert stats["adjustments"] == 0


def test_maybe_adjust_low_load():
    """测试低负载时增加并发"""
    sem = DynamicSemaphore(initial=5, min_value=1, max_value=10)
    sem._last_adjust_time = 0  # 重置时间，允许调整

    # 模拟低负载
    with patch("agent.dynamic_semaphore.get_system_load", return_value={
        "cpu_percent": 30.0,
        "memory_percent": 50.0,
        "load_avg": [0.5, 0.5, 0.5],
    }):
        sem._maybe_adjust()

    # 低负载时应该增加并发
    assert sem.value == 7  # 5 + 2
    stats = sem.get_stats()
    assert stats["adjustments"] == 1
    assert stats["ups"] == 1
    assert stats["downs"] == 0


def test_maybe_adjust_high_load():
    """测试高负载时减少并发"""
    sem = DynamicSemaphore(initial=5, min_value=1, max_value=10)
    sem._last_adjust_time = 0

    # 模拟高负载
    with patch("agent.dynamic_semaphore.get_system_load", return_value={
        "cpu_percent": 90.0,
        "memory_percent": 90.0,
        "load_avg": [5.0, 5.0, 5.0],
    }):
        sem._maybe_adjust()

    # 高负载时应该减少并发
    assert sem.value == 3  # 5 - 2
    stats = sem.get_stats()
    assert stats["adjustments"] == 1
    assert stats["ups"] == 0
    assert stats["downs"] == 1


def test_maybe_adjust_medium_load():
    """测试中等负载时不调整"""
    sem = DynamicSemaphore(initial=5, min_value=1, max_value=10)
    sem._last_adjust_time = 0

    # 模拟中等负载
    with patch("agent.dynamic_semaphore.get_system_load", return_value={
        "cpu_percent": 60.0,
        "memory_percent": 75.0,
        "load_avg": [2.0, 2.0, 2.0],
    }):
        sem._maybe_adjust()

    # 中等负载时不应该调整
    assert sem.value == 5
    stats = sem.get_stats()
    assert stats["adjustments"] == 0


def test_maybe_adjust_respects_min_max():
    """测试调整不超过最小最大值"""
    # 测试最小值限制
    sem_min = DynamicSemaphore(initial=2, min_value=1, max_value=10)
    sem_min._last_adjust_time = 0

    with patch("agent.dynamic_semaphore.get_system_load", return_value={
        "cpu_percent": 95.0,
        "memory_percent": 95.0,
        "load_avg": [10.0, 10.0, 10.0],
    }):
        sem_min._maybe_adjust()
    assert sem_min.value == 1  # 不会小于min_value

    # 测试最大值限制
    sem_max = DynamicSemaphore(initial=9, min_value=1, max_value=10)
    sem_max._last_adjust_time = 0

    with patch("agent.dynamic_semaphore.get_system_load", return_value={
        "cpu_percent": 10.0,
        "memory_percent": 20.0,
        "load_avg": [0.1, 0.1, 0.1],
    }):
        sem_max._maybe_adjust()
    assert sem_max.value == 10  # 不会大于max_value


def test_maybe_adjust_interval():
    """测试调整间隔限制"""
    sem = DynamicSemaphore(initial=5, min_value=1, max_value=10)
    # 设置上次调整时间为当前时间，确保间隔内不会调整
    import time
    sem._last_adjust_time = time.time()

    with patch("agent.dynamic_semaphore.get_system_load", return_value={
        "cpu_percent": 10.0,
        "memory_percent": 20.0,
        "load_avg": [0.1, 0.1, 0.1],
    }):
        sem._maybe_adjust()

    # 间隔内不应该调整
    assert sem.value == 5
    stats = sem.get_stats()
    assert stats["adjustments"] == 0


def test_get_stats():
    """测试get_stats返回完整统计"""
    sem = DynamicSemaphore(initial=4, min_value=2, max_value=8)
    stats = sem.get_stats()
    assert "current_value" in stats
    assert "initial" in stats
    assert "min" in stats
    assert "max" in stats
    assert "adjustments" in stats
    assert "ups" in stats
    assert "downs" in stats
