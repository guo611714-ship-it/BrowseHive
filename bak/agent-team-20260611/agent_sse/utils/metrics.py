import time
import asyncio
from typing import Dict, Any
from collections import defaultdict


class Metrics:
    def __init__(self):
        self._requests: Dict[str, int] = defaultdict(int)
        self._errors: Dict[str, int] = defaultdict(int)
        self._durations: list = []  # raw durations only, no sorted copy
        self._start_time = time.time()
        self._lock = asyncio.Lock()

    async def record_request(self, endpoint: str, status: str = "success"):
        async with self._lock:
            self._requests[f"{endpoint}:{status}"] += 1

    async def record_error(self, error_type: str):
        async with self._lock:
            self._errors[error_type] += 1

    async def record_response_time(self, endpoint: str, duration: float):
        async with self._lock:
            self._durations.append(duration)
            if len(self._durations) > 1000:
                self._durations = self._durations[-1000:]

    async def get_metrics(self) -> Dict[str, Any]:
        async with self._lock:
            uptime = time.time() - self._start_time
            sorted_d = sorted(self._durations) if self._durations else []
            return {
                "uptime_seconds": uptime,
                "requests_total": sum(self._requests.values()),
                "errors_total": sum(self._errors.values()),
                "requests_by_status": dict(self._requests),
                "errors_by_type": dict(self._errors),
                "avg_response_time": sum(sorted_d) / len(sorted_d) if sorted_d else 0.0,
                "p50": self._percentile(sorted_d, 50),
                "p95": self._percentile(sorted_d, 95),
                "p99": self._percentile(sorted_d, 99),
            }

    @staticmethod
    def _percentile(sorted_data: list, p: int) -> float:
        if not sorted_data:
            return 0.0
        idx = min(int(len(sorted_data) * p / 100), len(sorted_data) - 1)
        return sorted_data[idx]


metrics = Metrics()
