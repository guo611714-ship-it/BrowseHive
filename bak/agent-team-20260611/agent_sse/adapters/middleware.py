# agent_sse/adapters/middleware.py
"""中间件（JWT/日志/限流）"""

import time
import logging
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class JWTMiddleware(BaseHTTPMiddleware):
    """JWT 鉴权中间件"""

    def __init__(self, app, secret_key: str = None):
        super().__init__(app)
        self.secret_key = secret_key or "default-secret-key"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过健康检查和文档路径
        if request.url.path in ("/api/health", "/health", "/docs", "/openapi.json"):
            return await call_next(request)

        # 获取 Token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return Response(
                content='{"error": "Missing or invalid Authorization header"}',
                status_code=401,
                media_type="application/json"
            )

        token = auth_header[7:]
        try:
            # TODO: 实现 JWT 校验逻辑
            # decoded = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            # request.state.user = decoded
            pass
        except Exception as e:
            return Response(
                content='{"error": "Invalid token"}',
                status_code=401,
                media_type="application/json"
            )

        return await call_next(request)


class LoggingMiddleware(BaseHTTPMiddleware):
    """日志中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        logger.info(
            f"{request.method} {request.url.path} {response.status_code} {duration:.3f}s"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件"""

    def __init__(self, app, max_requests: int = 30, window_sec: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._hits = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # 清理过期记录
        if client_ip in self._hits:
            self._hits[client_ip] = [t for t in self._hits[client_ip] if now - t < self.window_sec]
        else:
            self._hits[client_ip] = []

        # 检查限流
        if len(self._hits[client_ip]) >= self.max_requests:
            return Response(
                content='{"error": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json"
            )

        self._hits[client_ip].append(now)
        return await call_next(request)
