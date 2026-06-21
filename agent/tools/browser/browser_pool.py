"""浏览器实例池 + 监控告警"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 浏览器实例池
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class BrowserInstance:
    """浏览器实例"""
    instance_id: str
    cdp_url: str
    status: str = "idle"  # idle | busy | error
    created_at: float = field(default_factory=time.time)
    last_used: float = 0
    request_count: int = 0


class BrowserPool:
    """浏览器实例池 — 复用连接，避免重复启动"""

    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self._instances: Dict[str, BrowserInstance] = {}

    def get_or_create(self, cdp_url: str = None) -> Optional[BrowserInstance]:
        """获取空闲实例或创建新实例"""
        # 复用空闲实例
        for inst in self._instances.values():
            if inst.status == "idle":
                inst.status = "busy"
                inst.last_used = time.time()
                inst.request_count += 1
                return inst

        # 创建新实例
        if len(self._instances) < self.max_size:
            inst_id = f"browser_{len(self._instances) + 1}"
            inst = BrowserInstance(
                instance_id=inst_id,
                cdp_url=cdp_url or "",
                status="busy",
                last_used=time.time()
            )
            self._instances[inst_id] = inst
            return inst

        return None  # 池已满

    def release(self, instance_id: str):
        """释放实例"""
        inst = self._instances.get(instance_id)
        if inst:
            inst.status = "idle"

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total": len(self._instances),
            "idle": sum(1 for i in self._instances.values() if i.status == "idle"),
            "busy": sum(1 for i in self._instances.values() if i.status == "busy"),
            "max_size": self.max_size
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 监控告警
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class AlertRule:
    """告警规则"""
    name: str
    condition: str  # "fail_rate>=0.01", "latency>=5000", "token_usage>=1.2*threshold"
    threshold: float
    window_seconds: int = 300  # 5分钟窗口
    cooldown_seconds: int = 300


class Monitor:
    """监控告警系统"""

    def __init__(self):
        self._metrics: Dict[str, deque] = {}
        self._alerts: List[Dict] = []
        self._alert_cooldowns: Dict[str, float] = {}
        self._rules: List[AlertRule] = [
            AlertRule("browser_fail_rate", "fail_rate", 0.01, 300, 300),
            AlertRule("browser_high_latency", "latency", 5000, 300, 300),
        ]

    def record(self, metric_name: str, value: float, tags: Dict = None):
        """记录指标"""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = deque(maxlen=1000)
        self._metrics[metric_name].append({
            "value": value, "tags": tags or {},
            "timestamp": time.time()
        })
        self._check_alerts(metric_name)

    def _check_alerts(self, metric_name: str):
        """检查告警规则"""
        now = time.time()
        for rule in self._rules:
            if rule.name not in metric_name:
                continue

            # 检查冷却期
            if now - self._alert_cooldowns.get(rule.name, 0) < rule.cooldown_seconds:
                continue

            # 计算窗口内指标
            values = self._metrics.get(metric_name, [])
            window_values = [v["value"] for v in values
                           if now - v["timestamp"] < rule.window_seconds]
            if not window_values:
                continue

            if rule.condition == "fail_rate":
                fails = sum(1 for v in window_values if v > 0)
                rate = fails / len(window_values) if window_values else 0
                if rate >= rule.threshold:
                    self._fire_alert(rule.name, f"失败率 {rate:.1%} >= {rule.threshold:.1%}")
            elif rule.condition == "latency":
                avg = sum(window_values) / len(window_values)
                if avg >= rule.threshold:
                    self._fire_alert(rule.name, f"平均延迟 {avg:.0f}ms >= {rule.threshold}ms")

    def _fire_alert(self, rule_name: str, message: str):
        """触发告警"""
        self._alert_cooldowns[rule_name] = time.time()
        alert = {
            "rule": rule_name, "message": message,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        self._alerts.append(alert)
        if len(self._alerts) > 50:
            self._alerts.pop(0)
        logger.warning(f"[ALERT] {rule_name}: {message}")

    def get_alerts(self, limit: int = 10) -> List[Dict]:
        return self._alerts[-limit:]

    def get_metrics_summary(self) -> Dict[str, Any]:
        summary = {}
        for name, values in self._metrics.items():
            recent = [v["value"] for v in values if time.time() - v["timestamp"] < 300]
            if recent:
                summary[name] = {
                    "count": len(recent),
                    "avg": sum(recent) / len(recent),
                    "max": max(recent),
                    "min": min(recent)
                }
        return summary


# 全局单例
_browser_pool: Optional[BrowserPool] = None
_monitor: Optional[Monitor] = None


def get_browser_pool() -> BrowserPool:
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = BrowserPool()
    return _browser_pool


def get_monitor() -> Monitor:
    global _monitor
    if _monitor is None:
        _monitor = Monitor()
    return _monitor
