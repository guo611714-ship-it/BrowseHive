"""BrowserClient — 统一CDP连接入口，供browser_tools和browser_agent共用"""

import os
import json
import time
import logging
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from ...config import CDP_PORT_FILE

logger = logging.getLogger(__name__)

# CDP配置
_CDP_PORT_FILE = str(CDP_PORT_FILE)
_CDP_PORTS = [9222, 9223, 9224, 9225]

# 连接缓存（线程安全）
_cdp_url_cache: Optional[str] = None
_cdp_cache_time: float = 0.0
_tabs_cache: Optional[list] = None
_tabs_cache_time: float = 0.0
_cache_lock = threading.Lock()
_async_cache_lock = asyncio.Lock()


def _detect_cdp_url_sync() -> Optional[str]:
    """同步检测CDP端口（带缓存5秒，线程安全）"""
    global _cdp_url_cache, _cdp_cache_time

    with _cache_lock:
        if _cdp_url_cache and (time.time() - _cdp_cache_time) < 5:
            return _cdp_url_cache

    import socket, urllib.request

    # 优先读取端口文件
    if os.path.exists(_CDP_PORT_FILE):
        try:
            saved = Path(_CDP_PORT_FILE).read_text().strip()
            if saved:
                port = int(saved.rstrip("/").split(":")[-1])
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    url = saved if saved.startswith("http") else f"http://127.0.0.1:{port}"
                    with _cache_lock:
                        _cdp_url_cache, _cdp_cache_time = url, time.time()
                    return url
        except Exception as e:
            logger.debug("caught exception: %s", e)

    for port in _CDP_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                data = json.loads(opener.open(f"http://127.0.0.1:{port}/json", timeout=1).read())
                if isinstance(data, list) and data:
                    url = f"http://127.0.0.1:{port}"
                    _cdp_url_cache, _cdp_cache_time = url, time.time()
                    return url
        except Exception as e:
            logger.debug("caught exception, continuing: %s", e)
            continue
    return None


async def detect_cdp_url() -> Optional[str]:
    """异步检测CDP端口"""
    return await asyncio.to_thread(_detect_cdp_url_sync)


async def get_tabs(cdp_url: str = None) -> list:
    """获取CDP标签页列表（带缓存3秒，线程安全）"""
    global _tabs_cache, _tabs_cache_time

    async with _async_cache_lock:
        if _tabs_cache and (time.time() - _tabs_cache_time) < 3:
            return _tabs_cache

        if not cdp_url:
            cdp_url = await detect_cdp_url()
        if not cdp_url:
            return []

        try:
            # 用subprocess curl替代httpx（Chrome CDP对httpx返回503）
            proc = await asyncio.create_subprocess_exec(
                'curl', '-s', f'{cdp_url}/json',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                tabs = json.loads(stdout.decode('utf-8'))
                _tabs_cache = tabs
                _tabs_cache_time = time.time()
                return tabs if isinstance(tabs, list) else []
        except Exception as e:
            logger.warning(f"获取标签页失败: {e}")
        return []


async def get_page_target(cdp_url: str = None) -> Optional[Dict]:
    """获取当前页面标签页"""
    tabs = await get_tabs(cdp_url)
    for tab in tabs:
        if tab.get("type") == "page" and "devtools" not in tab.get("url", ""):
            return tab
    return tabs[0] if tabs else None


async def exec_js(js_code: str, cdp_url: str = None) -> Dict[str, Any]:
    """在当前页面执行JavaScript（异步，不阻塞事件循环）"""
    from .utils import cdp_eval
    return await cdp_eval(cdp_url, js_code, timeout=15)


async def capture_screenshot(cdp_url: str = None) -> Dict[str, Any]:
    """截取页面截图"""
    if not cdp_url:
        cdp_url = await detect_cdp_url()
    if not cdp_url:
        return {"error": "浏览器未启动"}

    target = await get_page_target(cdp_url)
    if not target:
        return {"error": "无可用标签页"}

    ws_url = target.get("webSocketDebuggerUrl", "")
    if not ws_url:
        return {"error": "标签页无WebSocket连接"}

    def _ws_screenshot():
        import random
        import websocket
        ws = websocket.create_connection(ws_url, timeout=30)
        try:
            msg_id = random.randint(1, 999999)
            ws.send(json.dumps({
                "id": msg_id,
                "method": "Page.captureScreenshot",
                "params": {"format": "webp", "quality": 80}
            }))
            deadline = time.time() + 30
            while time.time() < deadline:
                msg = json.loads(ws.recv())
                if msg.get("id") == msg_id:
                    return msg
            return {"error": "CDP截图响应超时"}
        finally:
            ws.close()

    try:
        result = await asyncio.to_thread(_ws_screenshot)
        # 处理CDP错误响应
        if "error" in result:
            return {"error": f"CDP错误: {result['error'].get('message', '未知错误')}"}
        data = (result.get("result") or {}).get("data", "")
        if not data:
            return {"error": "截图失败"}

        import base64, uuid
        screenshot_dir = Path.home() / ".claude" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"screenshot_{uuid.uuid4().hex[:12]}.webp"
        filepath = screenshot_dir / filename
        filepath.write_bytes(base64.b64decode(data))
        return {"path": str(filepath), "size": filepath.stat().st_size}
    except ImportError:
        return {"error": "需要 websocket-client"}
    except Exception as e:
        return {"error": f"截图失败: {e}"}
