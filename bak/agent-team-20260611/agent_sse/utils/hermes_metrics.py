"""Hermes 集成监控指标"""

import time
import logging
from typing import Dict, Any
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class HermesMetrics:
    """Hermes 集成监控指标"""

    def __init__(self):
        self._start_time = time.time()
        self._request_count = 0
        self._error_count = 0
        self._response_times = []
        self._api_calls = defaultdict(int)
        self._errors = defaultdict(int)

    def record_request(self, endpoint: str, response_time: float, success: bool = True):
        """记录请求"""
        self._request_count += 1
        self._response_times.append(response_time)
        self._api_calls[endpoint] += 1

        if not success:
            self._error_count += 1
            self._errors[endpoint] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """获取监控指标"""
        uptime = time.time() - self._start_time
        avg_response_time = sum(self._response_times) / len(self._response_times) if self._response_times else 0
        error_rate = (self._error_count / self._request_count * 100) if self._request_count > 0 else 0

        return {
            "uptime_seconds": uptime,
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "error_rate_percent": error_rate,
            "avg_response_time_ms": avg_response_time * 1000,
            "api_calls": dict(self._api_calls),
            "errors": dict(self._errors),
            "timestamp": datetime.now().isoformat()
        }

    def get_prometheus_metrics(self) -> str:
        """获取 Prometheus 格式指标"""
        metrics = self.get_metrics()
        lines = [
            "# HELP hermes_uptime_seconds Hermes uptime in seconds",
            "# TYPE hermes_uptime_seconds gauge",
            f"hermes_uptime_seconds {metrics['uptime_seconds']:.1f}",
            "# HELP hermes_requests_total Total requests",
            "# TYPE hermes_requests_total counter",
            f"hermes_requests_total {metrics['total_requests']}",
            "# HELP hermes_errors_total Total errors",
            "# TYPE hermes_errors_total counter",
            f"hermes_errors_total {metrics['total_errors']}",
            "# HELP hermes_error_rate_percent Error rate percentage",
            "# TYPE hermes_error_rate_percent gauge",
            f"hermes_error_rate_percent {metrics['error_rate_percent']:.2f}",
            "# HELP hermes_avg_response_time_seconds Average response time",
            "# TYPE hermes_avg_response_time_seconds gauge",
            f"hermes_avg_response_time_seconds {metrics['avg_response_time_ms']/1000:.3f}",
        ]

        # API 调用统计
        for endpoint, count in metrics["api_calls"].items():
            lines.append(f'# HELP hermes_api_calls_total API calls for {endpoint}')
            lines.append(f'# TYPE hermes_api_calls_total counter')
            lines.append(f'hermes_api_calls_total{{endpoint="{endpoint}"}} {count}')

        return "\n".join(lines) + "\n"


# 全局实例
hermes_metrics = HermesMetrics()
