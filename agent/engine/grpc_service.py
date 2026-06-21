"""gRPC-compatible HTTP Service -- engine HTTP interface + service core

Merged from grpc_service.py and service.py.

Endpoints:
    POST /engine/submit     -- submit TaskManifest, return manifest_id
    GET  /engine/status/{id} -- query execution status
    POST /engine/cancel/{id} -- cancel execution
    GET  /engine/analyze     -- analyze tasks (no execution)
    GET  /engine/progress/{id} -- SSE real-time progress stream
    GET  /engine/stats       -- engine statistics
    GET  /engine/health      -- health check
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import aiohttp
from aiohttp import web

from .manifest import TaskManifest, FixTask, SmartSharder, TaskPriority, SchedulingStrategy
from .predictor import ConflictPredictor
from .scheduler import EnhancedScheduler, ResultAggregator
from .task_queue import TaskQueue, TaskEntry, TaskStatus
from .progress_sse import ProgressBroadcaster, get_broadcaster
from .utils import manifest_from_dict, manifest_to_dict

logger = logging.getLogger(__name__)

ENGINE_VERSION = "0.2.0"


# ============================================================
# Engine Service (was service.py)
# ============================================================

class EngineService:
    """常驻修复引擎服务 -- Phase 2

    用法:
        service = EngineService()
        await service.start()
        result = await service.submit(manifest)
        status = service.status("m-1-abc123")
        await service.cancel("m-1-abc123")
        plan = service.analyze(manifest)
        await service.stop()
    """

    def __init__(self, history_path: Optional[Path] = None,
                 dispatcher=None):
        self.sharder = SmartSharder(predictor=ConflictPredictor())
        self.scheduler = EnhancedScheduler(dispatcher=dispatcher)
        self.queue = TaskQueue(history_path=history_path)
        self.broadcaster = get_broadcaster()
        self.dispatcher = dispatcher
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._results: Dict[str, Dict[str, Any]] = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Engine service started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.queue.save_history()
        logger.info("Engine service stopped")

    def analyze(self, manifest: TaskManifest) -> Dict[str, Any]:
        predictor = ConflictPredictor()
        shards = self.sharder.shard(manifest)
        conflict_analysis = predictor.analyze_manifest(manifest)

        return {
            "manifest_summary": manifest.summary(),
            "shards": [
                {
                    "shard_id": s.shard_id,
                    "task_count": s.task_count,
                    "files": list(s.files),
                    "reason": s.reason,
                    "tasks": [t.task_id for t in s.tasks],
                }
                for s in shards
            ],
            "conflict_analysis": conflict_analysis,
            "execution_plan": {
                "total_shards": len(shards),
                "max_concurrent": manifest.max_concurrent,
                "strategy": manifest.strategy.value,
            },
        }

    async def submit(self, manifest: TaskManifest) -> Dict[str, Any]:
        manifest_id = await self.queue.submit(manifest)
        self.broadcaster.publish_progress(
            manifest_id, 0, 0,
            f"已提交 {manifest.task_count} 个任务",
            status="submitted"
        )
        return {
            "manifest_id": manifest_id,
            "status": "submitted",
            "task_count": manifest.task_count,
        }

    async def submit_and_wait(self, manifest: TaskManifest,
                               timeout: float = 600.0) -> Dict[str, Any]:
        result = await self.submit(manifest)
        manifest_id = result["manifest_id"]

        start = time.time()
        while time.time() - start < timeout:
            entries = self.queue.get_manifest_entries(manifest_id)
            if not entries:
                await asyncio.sleep(0.1)
                continue

            all_done = all(
                e.status in (TaskStatus.COMPLETED, TaskStatus.FAILED,
                             TaskStatus.CANCELLED)
                for e in entries
            )
            if all_done:
                return self._aggregate_results(manifest_id, entries)

            await asyncio.sleep(0.5)

        return {
            "manifest_id": manifest_id,
            "status": "timeout",
            "message": f"执行超时 ({timeout}s)",
        }

    def status(self, manifest_id: str) -> Dict[str, Any]:
        entries = self.queue.get_manifest_entries(manifest_id)
        if not entries:
            return {"status": "not_found", "manifest_id": manifest_id}

        by_status = {}
        for e in entries:
            by_status[e.status.value] = by_status.get(e.status.value, 0) + 1

        return {
            "manifest_id": manifest_id,
            "total": len(entries),
            "by_status": by_status,
            "entries": [e.to_dict() for e in entries],
        }

    async def cancel(self, manifest_id: str) -> Dict[str, Any]:
        cancelled = await self.queue.cancel_manifest(manifest_id)
        self.broadcaster.publish_progress(
            manifest_id, 0, 0,
            f"已取消 {cancelled} 个任务",
            status="cancelled"
        )
        return {
            "manifest_id": manifest_id,
            "cancelled": cancelled,
        }

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "queue": self.queue.stats,
            "subscribers": self.broadcaster.subscriber_count,
            "running": self._running,
        }

    async def _process_loop(self):
        while self._running:
            try:
                batch = await self.queue.next_batch(batch_size=5)
                if not batch:
                    await asyncio.sleep(0.5)
                    continue

                manifest_groups: Dict[str, list] = {}
                for entry in batch:
                    manifest_groups.setdefault(entry.manifest_id, []).append(entry)

                for manifest_id, entries in manifest_groups.items():
                    asyncio.create_task(
                        self._execute_manifest_group(manifest_id, entries)
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("处理循环异常: %s", e)
                await asyncio.sleep(1)

    async def _execute_manifest_group(self, manifest_id: str,
                                       entries: List[TaskEntry]):
        for entry in entries:
            await self.queue.mark_running(entry.entry_id)
            self.broadcaster.publish_progress(
                manifest_id, 0, 0,
                f"执行中: {entry.task.description}",
                status="running"
            )

            try:
                from .manifest import TaskManifest as TM
                single_manifest = TM(
                    tasks=[entry.task],
                    max_concurrent=1,
                )
                result = await self.scheduler.schedule(single_manifest)

                if result["status"] == "success":
                    await self.queue.mark_completed(entry.entry_id, result)
                else:
                    error = result.get("failed_items", [{}])[0].get("summary", "unknown")
                    await self.queue.mark_failed(entry.entry_id, error)

            except Exception as e:
                await self.queue.mark_failed(entry.entry_id, str(e))

    def _aggregate_results(self, manifest_id: str,
                           entries: List[TaskEntry]) -> Dict[str, Any]:
        completed = [e for e in entries if e.status == TaskStatus.COMPLETED]
        failed = [e for e in entries if e.status == TaskStatus.FAILED]
        cancelled = [e for e in entries if e.status == TaskStatus.CANCELLED]

        status = "success" if not failed else "partial" if completed else "failed"

        return {
            "manifest_id": manifest_id,
            "status": status,
            "total": len(entries),
            "completed": len(completed),
            "failed": len(failed),
            "cancelled": len(cancelled),
            "results": [e.result for e in completed if e.result],
            "errors": [e.error for e in failed if e.error],
        }


# ============================================================
# CORS Middleware
# ============================================================

def create_cors_middleware(host: str = "localhost", port: int = 8001):
    """创建 CORS 中间件工厂"""
    allowed_origin = f"http://{host}:{port}"

    @web.middleware
    async def _middleware(request: web.Request, handler) -> web.StreamResponse:
        return await _cors_handler(request, handler, host, port)

    return _middleware


async def _cors_handler(request: web.Request, handler, host: str, port: int) -> web.StreamResponse:
    """CORS 核心逻辑"""
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
        except Exception as e:
            logger.debug("Request handler error: %s", e)
            response = web.json_response({"error": "Internal Server Error"}, status=500)

    origin = request.headers.get("Origin", "")
    expected_origin = f"http://{host}:{port}"
    allowed_origin = ""
    if origin == expected_origin:
        allowed_origin = origin

    if allowed_origin:
        response.headers["Access-Control-Allow-Origin"] = allowed_origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Max-Age"] = "3600"
    return response


# ============================================================
# Engine HTTP Server
# ============================================================

class EngineHTTPServer:
    """引擎 HTTP 服务端 -- 将 EngineService 暴露为 HTTP API"""

    def __init__(self, engine_service: Optional[EngineService] = None,
                 port: int = 8001, host: str = "localhost"):
        self.engine = engine_service or EngineService()
        self.port = port
        self.host = host
        self._runner: Optional[web.AppRunner] = None
        self._start_time: float = 0.0

    def create_app(self) -> web.Application:
        cors = create_cors_middleware(host=self.host, port=self.port)
        app = web.Application(middlewares=[cors])
        app.router.add_get("/engine/health", self._handle_health)
        app.router.add_get("/engine/stats", self._handle_stats)
        app.router.add_post("/engine/submit", self._handle_submit)
        app.router.add_get("/engine/status/{manifest_id}", self._handle_status)
        app.router.add_post("/engine/cancel/{manifest_id}", self._handle_cancel)
        app.router.add_post("/engine/analyze", self._handle_analyze)
        app.router.add_get("/engine/progress/{manifest_id}", self._handle_progress)
        return app

    async def start(self):
        self._start_time = time.time()
        await self.engine.start()

        app = self.create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info("Engine HTTP 服务已启动: http://%s:%d", self.host, self.port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        await self.engine.stop()
        logger.info("Engine HTTP 服务已停止")

    def _json_response(self, data: Dict[str, Any],
                       status: int = 200) -> web.Response:
        return web.json_response(data, status=status, dumps=lambda x: json.dumps(x, ensure_ascii=False))

    async def _handle_health(self, request: web.Request) -> web.Response:
        uptime = time.time() - self._start_time if self._start_time else 0
        return self._json_response({
            "healthy": True,
            "version": ENGINE_VERSION,
            "uptime_seconds": round(uptime, 2),
            "service_running": self.engine._running,
        })

    async def _handle_stats(self, request: web.Request) -> web.Response:
        return self._json_response(self.engine.stats)

    async def _handle_submit(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception) as e:
            return self._json_response({"error": f"无效的 JSON: {e}"}, status=400)

        try:
            manifest = manifest_from_dict(body)
        except (KeyError, ValueError) as e:
            return self._json_response({"error": f"manifest 格式错误: {e}"}, status=400)

        if manifest.task_count == 0:
            return self._json_response({"error": "manifest 不含任何任务"}, status=400)

        result = await self.engine.submit(manifest)
        return self._json_response(result, status=201)

    async def _handle_status(self, request: web.Request) -> web.Response:
        manifest_id = request.match_info["manifest_id"]
        result = self.engine.status(manifest_id)
        status_code = 200 if result.get("status") != "not_found" else 404
        return self._json_response(result, status=status_code)

    async def _handle_cancel(self, request: web.Request) -> web.Response:
        manifest_id = request.match_info["manifest_id"]
        result = await self.engine.cancel(manifest_id)
        return self._json_response(result)

    async def _handle_analyze(self, request: web.Request) -> web.Response:
        manifest_data = None

        manifest_json = request.query.get("manifest")
        if manifest_json:
            try:
                manifest_data = json.loads(manifest_json)
            except json.JSONDecodeError:
                return self._json_response({"error": "查询参数 manifest 不是有效 JSON"}, status=400)

        if manifest_data is None:
            try:
                manifest_data = await request.json()
            except (json.JSONDecodeError, Exception):
                return self._json_response({"error": "请提供 manifest 数据"}, status=400)

        try:
            manifest = manifest_from_dict(manifest_data)
        except (KeyError, ValueError) as e:
            return self._json_response({"error": f"manifest 格式错误: {e}"}, status=400)

        plan = self.engine.analyze(manifest)
        return self._json_response(plan)

    async def _handle_progress(self, request: web.Request) -> web.Response:
        manifest_id = request.match_info["manifest_id"]
        broadcaster = self.engine.broadcaster
        queue = await broadcaster.subscribe(manifest_id)

        async def event_stream():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield event.format()
                    except asyncio.TimeoutError:
                        yield "event: heartbeat\ndata: {}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                await broadcaster.unsubscribe(queue, manifest_id)

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)

        origin = request.headers.get("Origin", "")
        expected_origin = f"http://{self.host}:{self.port}"
        if origin == expected_origin:
            response.headers["Access-Control-Allow-Origin"] = origin

        async for chunk in event_stream():
            await response.write(chunk.encode("utf-8"))

        return response


# ============================================================
# Engine HTTP Client
# ============================================================

@dataclass
class ClientConfig:
    """客户端配置"""
    base_url: str = "http://localhost:8001"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 0.5
    pool_size: int = 10


class EngineHTTPClient:
    """引擎 HTTP 客户端 -- 连接 EngineHTTPServer"""

    def __init__(self, base_url: str = "http://localhost:8001",
                 timeout: float = 30.0, max_retries: int = 3):
        self.config = ClientConfig(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            max_retries=max_retries,
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            connector = aiohttp.TCPConnector(limit=self.config.pool_size)
            self._session = aiohttp.ClientSession(
                timeout=timeout, connector=connector
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _request(self, method: str, path: str,
                       **kwargs) -> Dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self.config.base_url}{path}"
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                async with session.request(method, url, **kwargs) as resp:
                    data = await resp.json()
                    if resp.status >= 400:
                        raise EngineClientError(
                            f"HTTP {resp.status}: {data.get('error', 'unknown')}",
                            status_code=resp.status, response=data,
                        )
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
            except EngineClientError as e:
                if e.status_code >= 500:
                    last_error = e
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    raise

        raise EngineClientError(
            f"请求失败 (重试 {self.config.max_retries} 次): {last_error}"
        )

    async def submit(self, manifest_dict: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/engine/submit", json=manifest_dict)

    async def status(self, manifest_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/engine/status/{manifest_id}")

    async def cancel(self, manifest_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/engine/cancel/{manifest_id}")

    async def analyze(self, manifest_dict: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/engine/analyze", json=manifest_dict)

    async def progress(self, manifest_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        session = await self._ensure_session()
        url = f"{self.config.base_url}/engine/progress/{manifest_id}"

        async with session.get(url) as resp:
            async for line in resp.content:
                decoded = line.decode("utf-8").strip()
                if not decoded or decoded.startswith(":"):
                    continue

                event_type = "message"
                data_lines = []

                for raw_line in decoded.split("\n"):
                    if raw_line.startswith("event: "):
                        event_type = raw_line[7:]
                    elif raw_line.startswith("data: "):
                        data_lines.append(raw_line[6:])

                if data_lines:
                    data_str = "\n".join(data_lines)
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        data = {"raw": data_str}

                    yield {"event": event_type, "data": data}

    async def stats(self) -> Dict[str, Any]:
        return await self._request("GET", "/engine/stats")

    async def health(self) -> bool:
        try:
            data = await self._request("GET", "/engine/health")
            return data.get("healthy", False)
        except EngineClientError:
            return False


# ============================================================
# Exceptions
# ============================================================

class EngineClientError(Exception):
    """引擎客户端异常"""

    def __init__(self, message: str, status_code: int = 0,
                 response: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response
