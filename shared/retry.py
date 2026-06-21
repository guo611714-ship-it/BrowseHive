"""共享重试逻辑 — 指数退避 + 预算控制"""

import time
import asyncio
from typing import Callable, Any, Optional


class RetryManager:
    """重试管理器：指数退避 + 预算限制"""

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0,
                 budget_max: int = 20, budget_window: int = 60):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.budget_max = budget_max
        self.budget_window = budget_window
        self._budget: list[float] = []

    def _check_budget(self) -> bool:
        """检查重试预算是否还有余额"""
        now = time.time()
        self._budget = [t for t in self._budget if (now - t) < self.budget_window]
        if len(self._budget) >= self.budget_max:
            return False
        self._budget.append(now)
        return True

    async def execute(self, func: Callable, *args,
                      on_retry: Optional[Callable] = None, **kwargs) -> Any:
        """带重试的异步执行"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    if not self._check_budget():
                        break
                    delay = self.base_delay * (2 ** attempt)
                    if on_retry:
                        on_retry(attempt + 1, e, delay)
                    await asyncio.sleep(delay)
        raise last_error

    def execute_sync(self, func: Callable, *args,
                     on_retry: Optional[Callable] = None, **kwargs) -> Any:
        """带重试的同步执行"""
        import time as _time
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    if not self._check_budget():
                        break
                    delay = self.base_delay * (2 ** attempt)
                    if on_retry:
                        on_retry(attempt + 1, e, delay)
                    _time.sleep(delay)
        raise last_error
