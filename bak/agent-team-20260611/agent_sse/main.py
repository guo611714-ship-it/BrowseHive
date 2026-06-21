import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from agent_sse.config import settings
from agent_sse.dependencies import init_agent_loop, shutdown_agent_loop, get_agent_loop
from agent_sse.utils.logging_config import setup_logging
from agent_sse.adapters.hermes_adapter import hermes_adapter
from agent_sse.adapters.middleware import JWTMiddleware, LoggingMiddleware, RateLimitMiddleware

logger = logging.getLogger(__name__)

setup_logging()


# --- Simple in-memory rate limiter (per-IP, sliding window) ---
class _RateLimiter:
    """Sliding window rate limiter. Max `max_requests` per `window_sec` per key."""
    def __init__(self, max_requests: int = 30, window_sec: int = 60):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._hits: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_sec
        # Prune old entries
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]
        if len(self._hits[key]) >= self.max_requests:
            return False
        self._hits[key].append(now)
        return True

_rate_limiter = _RateLimiter(max_requests=30, window_sec=60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Starting up Agent Team SSE...")
        await init_agent_loop()
        # 初始化 Hermes 适配层
        workspace_path = os.environ.get("AGENT_WORKSPACE", os.getcwd())
        await hermes_adapter.initialize(workspace_path)
        logger.info("Startup complete")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise
    yield
    try:
        logger.info("Shutting down gracefully...")
        # 1. Stop accepting new requests (FastAPI handles this)
        # 2. Wait for in-flight requests (max 10s)
        # 3. Shutdown agent loop
        await asyncio.wait_for(shutdown_agent_loop(), timeout=10)
        logger.info("Shutdown complete")
    except asyncio.TimeoutError:
        logger.warning("Shutdown timed out after 10s, forcing exit")
    except Exception as e:
        logger.error(f"Shutdown error: {e}", exc_info=True)

app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# GZip 响应压缩（阈值 1KB）
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS 配置 - 允许 Dashboard 前端访问
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)


class SessionTrackingMiddleware(BaseHTTPMiddleware):
    """Extract x-session-id header and attach to request.state for downstream use."""
    async def dispatch(self, request: Request, call_next):
        if not hasattr(request.state, "session_id"):
            session_id = request.headers.get("x-session-id", "unknown")
            request.state.session_id = session_id
        response = await call_next(request)
        return response

app.add_middleware(SessionTrackingMiddleware)

# 适配层中间件
app.add_middleware(RateLimitMiddleware, max_requests=30, window_sec=60)
app.add_middleware(LoggingMiddleware)
app.add_middleware(JWTMiddleware, secret_key=os.environ.get("JWT_SECRET", "default-secret"))


@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    trace_id = str(uuid.uuid4())[:8]
    request.state.trace_id = trace_id
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"
    # Structured request logging (skip health checks)
    if request.url.path not in ("/api/health", "/health", "/api/metrics"):
        logger.info(
            "%s %s %d %.1fms",
            request.method, request.url.path, response.status_code, duration_ms,
            extra={"trace_id": trace_id, "duration_ms": round(duration_ms, 1),
                   "status_code": response.status_code, "endpoint": request.url.path}
        )
    return response


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    # Skip rate limiting for health checks
    if request.url.path in ("/api/health", "/health"):
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(client_ip):
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded. Max 30 requests/minute."})
    return await call_next(request)

from agent_sse.routes.agent import router as agent_router
from agent_sse.routes.tools import router as tools_router
from agent_sse.routes.parallel import router as parallel_router
from agent_sse.routes.hermes import router as hermes_router
app.include_router(agent_router)
app.include_router(tools_router)
app.include_router(parallel_router)
app.include_router(hermes_router)

@app.get("/api/health")
async def health_check():
    from datetime import datetime
    loop = get_agent_loop()
    return {
        "status": "healthy",
        "agent_loop": loop is not None,
        "tools": len(loop.tools) if loop else 0,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/metrics")
async def metrics_endpoint():
    """Prometheus-compatible metrics endpoint."""
    from agent_sse.utils.metrics import metrics
    m = await metrics.get_metrics()
    error_rate = (m['errors_total'] / m['requests_total'] * 100) if m['requests_total'] > 0 else 0
    loop = get_agent_loop()
    lines = [
        "# HELP agent_team_uptime_seconds Server uptime in seconds",
        "# TYPE agent_team_uptime_seconds gauge",
        f"agent_team_uptime_seconds {m['uptime_seconds']:.1f}",
        "# HELP agent_team_requests_total Total requests",
        "# TYPE agent_team_requests_total counter",
        f"agent_team_requests_total {m['requests_total']}",
        "# HELP agent_team_errors_total Total errors",
        "# TYPE agent_team_errors_total counter",
        f"agent_team_errors_total {m['errors_total']}",
        "# HELP agent_team_error_rate_percent Error rate percentage",
        "# TYPE agent_team_error_rate_percent gauge",
        f"agent_team_error_rate_percent {error_rate:.2f}",
        "# HELP agent_team_tools_registered Number of registered tools",
        "# TYPE agent_team_tools_registered gauge",
        f"agent_team_tools_registered {len(loop.tools) if loop else 0}",
        "# HELP agent_team_agent_loop_healthy Agent loop health status",
        "# TYPE agent_team_agent_loop_healthy gauge",
        f"agent_team_agent_loop_healthy {1 if loop else 0}",
        "# HELP agent_team_response_time_seconds Response time percentiles",
        "# TYPE agent_team_response_time_seconds gauge",
        f"agent_team_response_time_seconds{{quantile=\"0.5\"}} {m['p50']/1000:.3f}",
        f"agent_team_response_time_seconds{{quantile=\"0.95\"}} {m['p95']/1000:.3f}",
        f"agent_team_response_time_seconds{{quantile=\"0.99\"}} {m['p99']/1000:.3f}",
        f"agent_team_response_time_seconds{{quantile=\"avg\"}} {m['avg_response_time']/1000:.3f}",
    ]
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
