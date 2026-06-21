"""浏览器工具 — 通用工具函数与共享状态"""

import re
import json
import time
import random
import logging
import asyncio
from typing import Dict, Any, Optional
from collections import deque

from ..checkpoint import CheckpointManager, BrowserCheckpoint
from .browser_pool import get_monitor, get_browser_pool
from ...utils import _ok, _err  # Unified response helpers

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 共享状态
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 检查点 + 监控
_checkpoint_mgr = CheckpointManager()
_current_checkpoint: Optional[BrowserCheckpoint] = None

# 操作日志
_operation_log: deque = deque(maxlen=500)

# 会话内存
_session_memories: Dict[str, Dict] = {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 基础工具函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _safe_js_str(s: str) -> str:
    """安全转义JS字符串（防注入，覆盖所有上下文）"""
    s = s.replace("\\", "\\\\")  # 先转义反斜杠
    s = s.replace('"', '\\"')    # 转义双引号
    s = s.replace("'", "\\'")    # 转义单引号
    return s.replace("`", "\\`").replace("${", "\\${").replace("\n", "\\n").replace("\r", "\\r").replace("\0", "")

def _safe_js_selector(s: str) -> str:
    """安全转义选择器（仅允许合法CSS/XPath字符，禁止引号防注入）"""
    if s.startswith("//") or s.startswith("("):
        # Preserve @ inside XPath predicates [...], strip elsewhere
        def _clean_xpath_predicate(m):
            return "[" + re.sub(r"[^a-zA-Z0-9_\-/()\[\]=*,:. >+~|@']", "", m.group(0)) + "]"
        s = re.sub(r"\[([^\]]*)\]", _clean_xpath_predicate, s)
        return re.sub(r"[^a-zA-Z0-9_\-/()\[\]=*,:. >+~|]", "", s)
    return re.sub(r"[^a-zA-Z0-9_\-#.\[\]=:, >+~|]", "", s)

def _log_operation(tool_name: str, args: Dict, result: Dict, cost_ms: int):
    """记录操作日志 + 检查点 + 监控指标"""
    entry = {
        "tool": tool_name, "args": args, "code": result.get("code"),
        "cost_ms": cost_ms, "time": time.time()
    }
    _operation_log.append(entry)

    # 写检查点
    if _current_checkpoint:
        try:
            _checkpoint_mgr.record_step(_current_checkpoint, tool_name, args, result)
            _checkpoint_mgr.save(_current_checkpoint)
        except Exception as e:
            logger.warning(f"检查点写入失败: {e}")

    # 记录监控指标
    try:
        monitor = get_monitor()
        status = "success" if result.get("code", 0) < 300 else "error"
        monitor.record(tool_name, cost_ms, {"status": status})
    except Exception as e:
        logger.debug("caught exception: %s", e)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CDP WebSocket 共享工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cdp_eval_sync(ws_url: str, expression: str, timeout: float = 15) -> Dict[str, Any]:
    """同步执行CDP JavaScript（供 asyncio.to_thread 调用）

    Args:
        ws_url: WebSocket调试URL
        expression: JavaScript表达式
        timeout: 超时秒数

    Returns:
        {"data": value} 或 {"error": message}
    """
    import websocket
    ws = None
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout)
        msg_id = random.randint(1, 999999)
        ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True, "awaitPromise": True}
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(ws.recv())
            if msg.get("id") == msg_id:
                if "error" in msg:
                    return {"error": f"CDP错误: {msg['error'].get('message', '未知错误')}"}
                value = (msg.get("result") or {}).get("result") or {}
                if value.get("type") == "undefined":
                    return {"data": None}
                return {"data": value.get("value")}
        return {"error": f"CDP响应超时 ({timeout}s)"}
    finally:
        if ws:
            ws.close()


async def cdp_eval(cdp_url: str, expression: str, timeout: float = 15) -> Dict[str, Any]:
    """异步执行CDP JavaScript（自动获取WebSocket URL）

    Args:
        cdp_url: CDP调试URL (如 http://127.0.0.1:9222)
        expression: JavaScript表达式
        timeout: 超时秒数

    Returns:
        {"data": value} 或 {"error": message}
    """
    from .browser_client import detect_cdp_url
    ws_url = cdp_url or await detect_cdp_url()
    if not ws_url:
        return {"error": "浏览器未启动"}

    try:
        result = await asyncio.to_thread(cdp_eval_sync, ws_url, expression, timeout)
        return result
    except ImportError:
        return {"error": "需要 websocket-client: pip install websocket-client"}
    except Exception as e:
        return {"error": f"JS执行失败: {e}"}
