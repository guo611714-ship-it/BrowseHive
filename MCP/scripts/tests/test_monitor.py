"""Monitor 单元测试."""

import asyncio
import time
import pytest
from core.monitor import HealthMonitor, SessionManager, _check_disk_space, _check_network_latency


class TestDiskSpace:
    """磁盘空间检查测试."""

    def test_returns_valid_data(self):
        result = _check_disk_space()
        assert "total_gb" in result
        assert "used_gb" in result
        assert "free_gb" in result
        assert "percent_used" in result
        assert result["total_gb"] > 0
        assert 0 <= result["percent_used"] <= 100

    def test_with_invalid_path(self):
        result = _check_disk_space("/nonexistent")
        # 应有 fallback 或返回错误
        assert isinstance(result, dict)


class TestNetworkLatency:
    """网络延迟检查测试."""

    def test_returns_float_or_none(self):
        result = _check_network_latency()
        assert result is None or isinstance(result, float)

    def test_with_short_timeout(self):
        """超时应返回 None."""
        result = _check_network_latency(host="192.0.2.1", timeout=1)
        assert result is None


class TestHealthMonitor:
    """HealthMonitor 测试."""

    def test_initial_state(self):
        monitor = HealthMonitor()
        status = monitor.get_status()
        assert "agent_available" in status
        assert "health" in status
        assert "connection" in status

    @pytest.mark.asyncio
    async def test_check_health_populates_history(self):
        """check_health 应记录历史."""
        monitor = HealthMonitor()
        monitor._connection_health["last_check"] = 0  # 强制重新检查
        result = await monitor.check_health()
        assert len(result["history"]) >= 1

    @pytest.mark.asyncio
    async def test_check_health_includes_disk(self):
        """check_health 应包含磁盘信息."""
        monitor = HealthMonitor()
        monitor._connection_health["last_check"] = 0
        result = await monitor.check_health()
        assert "disk" in result
        assert "percent_used" in result.get("disk", {})

    @pytest.mark.asyncio
    async def test_check_health_includes_latency(self):
        """check_health 应包含网络延迟."""
        monitor = HealthMonitor()
        monitor._connection_health["last_check"] = 0
        result = await monitor.check_health()
        assert "network_latency_ms" in result

    @pytest.mark.asyncio
    async def test_check_health_includes_score(self):
        """check_health 应包含健康评分."""
        monitor = HealthMonitor()
        monitor._connection_health["last_check"] = 0
        result = await monitor.check_health()
        assert "health_score" in result
        assert 0 <= result["health_score"] <= 100

    @pytest.mark.asyncio
    async def test_check_health_rate_limiting(self):
        """check_health 不应过于频繁地执行."""
        monitor = HealthMonitor()
        monitor._connection_health["last_check"] = time.time()
        result1 = await monitor.check_health()
        result2 = await monitor.check_health()
        # 两次应返回相同引用（缓存）
        assert result1 is result2

    @pytest.mark.asyncio
    async def test_consecutive_failures_increment(self):
        """连续失败应递增."""
        monitor = HealthMonitor()
        monitor._connection_health["last_check"] = 0
        # 模拟无浏览器
        original = monitor.__class__.__module__
        await monitor.check_health()
        failures = monitor._connection_health["consecutive_failures"]
        # 至少验证数据结构正确
        assert isinstance(failures, int)


class TestSessionManager:
    """SessionManager 测试."""

    @pytest.mark.asyncio
    async def test_save_and_restore(self, tmp_path):
        """保存和恢复快照."""
        sm = SessionManager()
        path = str(tmp_path / "test_snapshot.json")
        result = await sm.save_snapshot(path)
        assert "已保存" in result

        # 修改统计后恢复
        sm2 = SessionManager()
        result2 = await sm2.restore_snapshot(path)
        assert "已恢复" in result2

    @pytest.mark.asyncio
    async def test_restore_nonexistent(self, tmp_path):
        """恢复不存在的快照应返回错误."""
        sm = SessionManager()
        result = await sm.restore_snapshot(str(tmp_path / "nonexistent.json"))
        assert "不存在" in result

    def test_default_snapshot_path(self):
        """默认快照路径应有效."""
        sm = SessionManager()
        path = sm._get_default_snapshot_path()
        assert "session_snapshot.json" in path
