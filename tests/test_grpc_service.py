"""测试 gRPC-compatible HTTP Service

测试 EngineHTTPServer 和 EngineHTTPClient 的功能:
- 服务启动/停止
- submit 端点
- status 端点
- analyze 端点
- health 端点
- stats 端点
- cancel 端点
- 客户端-服务端完整往返
- 错误处理
"""

import asyncio
import json
import pytest
import aiohttp
from aiohttp import web

from agent.engine.grpc_service import (
    EngineHTTPServer,
    EngineHTTPClient,
    EngineClientError,
    manifest_from_dict,
    manifest_to_dict,
)
from agent.engine.manifest import TaskManifest, FixTask, SchedulingStrategy, TaskPriority


# ============================================================
# 测试数据
# ============================================================

def _make_manifest_dict() -> dict:
    """构造测试用 TaskManifest 字典"""
    return {
        "tasks": [
            {
                "task_id": "fix-1",
                "description": "修复类型错误",
                "files": ["src/app.py"],
                "agent_type": "neiguan_yingzao",
                "priority": "high",
                "timeout": 120.0,
            },
            {
                "task_id": "fix-2",
                "description": "添加单元测试",
                "files": ["tests/test_app.py"],
                "agent_type": "neiguan_yingzao",
                "priority": "normal",
            },
        ],
        "strategy": "auto",
        "max_concurrent": 3,
    }


def _make_single_task_dict() -> dict:
    """构造单任务 manifest 字典"""
    return {
        "tasks": [
            {
                "task_id": "fix-1",
                "description": "修复类型错误",
                "files": ["src/app.py"],
            },
        ],
        "strategy": "auto",
    }


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def server():
    """启动和停止测试服务器"""
    from agent.engine.service import EngineService
    engine_service = EngineService()

    # 使用临时端口（0 = 系统分配空闲端口）
    # 先绑定获取端口，再创建服务
    import socket
    temp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    temp.bind(("127.0.0.1", 0))
    actual_port = temp.getsockname()[1]
    temp.close()

    server_instance = EngineHTTPServer(
        engine_service=engine_service,
        port=actual_port,
        host="127.0.0.1",
    )

    app = server_instance.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", actual_port)
    await site.start()
    server_instance._start_time = asyncio.get_event_loop().time()

    yield server_instance

    await runner.cleanup()
    await engine_service.stop()


@pytest.fixture
async def client(server):
    """创建连接到测试服务器的客户端"""
    base_url = f"http://127.0.0.1:{server.port}"
    c = EngineHTTPClient(base_url=base_url, timeout=5.0, max_retries=1)
    yield c
    await c.close()


# ============================================================
# 测试: manifest 序列化/反序列化
# ============================================================

def test_manifest_roundtrip():
    """manifest_dict -> TaskManifest -> manifest_dict 往返一致性"""
    original = _make_manifest_dict()
    manifest = manifest_from_dict(original)
    result = manifest_to_dict(manifest)

    assert len(result["tasks"]) == 2
    assert result["tasks"][0]["task_id"] == "fix-1"
    assert result["tasks"][0]["files"] == ["src/app.py"]
    assert result["strategy"] == "auto"
    assert result["max_concurrent"] == 3


def test_manifest_from_dict_with_defaults():
    """manifest_from_dict 处理缺失字段时使用默认值"""
    minimal = {
        "tasks": [
            {"task_id": "t-1", "description": "test", "files": []},
        ]
    }
    manifest = manifest_from_dict(minimal)
    assert manifest.strategy == SchedulingStrategy.AUTO
    assert manifest.max_concurrent == 5
    assert manifest.tasks[0].agent_type == "neiguan_yingzao"
    assert manifest.tasks[0].timeout == 300.0


# ============================================================
# 测试: 服务端点
# ============================================================

@pytest.mark.anyio
async def test_health_endpoint(client, server):
    """GET /engine/health 返回健康状态"""
    data = await client.health()
    assert data is True


@pytest.mark.anyio
async def test_health_response_structure(client, server):
    """GET /engine/health 返回完整结构"""
    result = await client._request("GET", "/engine/health")
    assert "healthy" in result
    assert "version" in result
    assert "uptime_seconds" in result
    assert result["healthy"] is True


@pytest.mark.anyio
async def test_submit_endpoint(client, server):
    """POST /engine/submit 接受 manifest 并返回 manifest_id"""
    manifest_dict = _make_single_task_dict()
    result = await client.submit(manifest_dict)

    assert "manifest_id" in result
    assert result["status"] == "submitted"
    assert result["task_count"] == 1
    assert isinstance(result["manifest_id"], str)
    assert len(result["manifest_id"]) > 0


@pytest.mark.anyio
async def test_submit_empty_manifest_rejected(client, server):
    """POST /engine/submit 拒绝空 manifest"""
    empty = {"tasks": []}
    with pytest.raises(EngineClientError) as exc_info:
        await client.submit(empty)
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_submit_invalid_json_rejected(client, server):
    """POST /engine/submit 拒绝无效 JSON"""
    session = await client._ensure_session()
    url = f"{client.config.base_url}/engine/submit"

    async with session.post(url, data="not json", headers={"Content-Type": "application/json"}) as resp:
        assert resp.status == 400


@pytest.mark.anyio
async def test_status_endpoint(client, server):
    """GET /engine/status/{manifest_id} 返回任务状态"""
    # 先提交一个任务
    result = await client.submit(_make_single_task_dict())
    manifest_id = result["manifest_id"]

    status = await client.status(manifest_id)
    assert status["manifest_id"] == manifest_id
    assert "total" in status
    assert "entries" in status


@pytest.mark.anyio
async def test_status_not_found(client, server):
    """GET /engine/status/{manifest_id} 对不存在的 ID 返回 404"""
    with pytest.raises(EngineClientError) as exc_info:
        await client.status("nonexistent-manifest-id")
    assert exc_info.value.status_code == 404


@pytest.mark.anyio
async def test_cancel_endpoint(client, server):
    """POST /engine/cancel/{manifest_id} 取消任务"""
    result = await client.submit(_make_single_task_dict())
    manifest_id = result["manifest_id"]

    cancel_result = await client.cancel(manifest_id)
    assert cancel_result["manifest_id"] == manifest_id
    assert "cancelled" in cancel_result


@pytest.mark.anyio
async def test_analyze_endpoint(client, server):
    """GET /engine/analyze 返回执行计划"""
    manifest_dict = _make_manifest_dict()
    plan = await client.analyze(manifest_dict)

    assert "manifest_summary" in plan
    assert "shards" in plan
    assert "execution_plan" in plan
    assert plan["execution_plan"]["max_concurrent"] == 3


@pytest.mark.anyio
async def test_stats_endpoint(client, server):
    """GET /engine/stats 返回引擎统计"""
    stats = await client.stats()
    assert "queue" in stats
    assert "running" in stats


@pytest.mark.anyio
async def test_cors_headers(client, server):
    """CORS 头正确设置 — 仅允许与服务器 host:port 精确匹配的来源"""
    session = await client._ensure_session()
    url = f"{client.config.base_url}/engine/health"
    server_origin = f"http://{server.host}:{server.port}"

    # 正确的 origin 应被允许
    async with session.options(url, headers={"Origin": server_origin}) as resp:
        assert resp.headers.get("Access-Control-Allow-Origin") == server_origin
        assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")

    # localhost 但端口不匹配 → 拒绝
    async with session.options(url, headers={"Origin": "http://localhost:3000"}) as resp:
        assert resp.headers.get("Access-Control-Allow-Origin") is None

    # 非 localhost 来源 → 拒绝
    async with session.options(url, headers={"Origin": "https://evil.com"}) as resp:
        assert resp.headers.get("Access-Control-Allow-Origin") is None


@pytest.mark.anyio
async def test_cors_headers_no_origin(client, server):
    """无 Origin 头时不设置 Allow-Origin"""
    session = await client._ensure_session()
    url = f"{client.config.base_url}/engine/health"

    async with session.options(url) as resp:
        assert resp.headers.get("Access-Control-Allow-Origin") is None


@pytest.mark.anyio
async def test_client_server_full_roundtrip(client, server):
    """完整往返: submit -> status -> cancel -> analyze"""
    # 1. 提交
    manifest_dict = _make_manifest_dict()
    submit_result = await client.submit(manifest_dict)
    manifest_id = submit_result["manifest_id"]

    # 2. 查询状态
    status = await client.status(manifest_id)
    assert status["manifest_id"] == manifest_id

    # 3. 取消
    cancel_result = await client.cancel(manifest_id)
    assert cancel_result["manifest_id"] == manifest_id

    # 4. 分析另一个 manifest
    plan = await client.analyze(manifest_dict)
    assert len(plan["shards"]) > 0


@pytest.mark.anyio
async def test_server_start_stop():
    """服务可以正常启动和停止"""
    import socket
    from agent.engine.service import EngineService

    # 获取空闲端口
    temp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    temp.bind(("127.0.0.1", 0))
    port = temp.getsockname()[1]
    temp.close()

    engine = EngineService()
    server = EngineHTTPServer(engine_service=engine, port=port, host="127.0.0.1")

    app = server.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()

    # 验证服务运行: 通过 HTTP 请求确认
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{port}/engine/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["healthy"] is True

    await runner.cleanup()
    await engine.stop()


@pytest.mark.anyio
async def test_client_context_manager():
    """客户端支持 async with 上下文管理器"""
    async with EngineHTTPClient("http://127.0.0.1:19999") as client:
        assert client._session is not None
    # 退出后会话已关闭
    assert client._session is None or client._session.closed


@pytest.mark.anyio
async def test_client_health_unreachable():
    """客户端连接不可达服务器时返回 False"""
    client = EngineHTTPClient("http://127.0.0.1:19998", timeout=1.0, max_retries=1)
    result = await client.health()
    assert result is False
    await client.close()
