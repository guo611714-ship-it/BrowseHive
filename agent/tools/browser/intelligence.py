"""浏览器智能工具 — 截图+AI分析 / 页面监控"""

import json
import time
import asyncio
import logging
import base64
import hashlib
from typing import Dict, Optional
from pathlib import Path

from ..tool_registry import tool
from .browser_client import exec_js as _cdp_exec_js, detect_cdp_url
from .utils import _ok, _err, _log_operation
from .session import _record_to_session

logger = logging.getLogger(__name__)


async def _exec_js(js_code: str) -> Dict:
    """在当前页面执行 JavaScript"""
    result = await _cdp_exec_js(js_code)
    if "error" in result:
        return _err(500, result["error"])
    return _ok(result.get("data"))


@tool("screenshot_and_ask", "截取页面截图并用AI分析内容，一步完成")
async def screenshot_and_ask(question: str, area: str = "full") -> Dict:
    """截图+AI分析一步完成。

    Args:
        question: 对截图的分析问题（如"这个页面的登录表单在什么位置？"）
        area: 截图区域 — full / viewport / element(CSS选择器)
    """
    t0 = time.time()

    # 1. 截图
    try:
        from .browser_client import capture_screenshot
        screenshot_result = await capture_screenshot(area=area)
        if not screenshot_result or not Path(screenshot_result).exists():
            return _err(500, "截图失败")
    except Exception as e:
        return _err(500, f"截图失败: {e}")

    # 2. 获取页面元信息
    js_meta = """JSON.stringify({
        url: window.location.href,
        title: document.title,
        text: document.body.innerText.substring(0, 3000)
    })"""
    meta_result = await _exec_js(js_meta)
    page_meta = {}
    try:
        page_meta = json.loads(meta_result.get("data", "{}")) if isinstance(
            meta_result.get("data"), str) else meta_result.get("data", {})
    except Exception as e:
        logger.debug("caught exception: %s", e)

    # 3. 调用smart_ask分析
    try:
        from .ai_search import smart_ask
        analysis_prompt = (
            f"请分析这个网页截图。问题：{question}\n\n"
            f"页面URL: {page_meta.get('url', 'unknown')}\n"
            f"页面标题: {page_meta.get('title', 'unknown')}\n"
            f"页面文本摘要: {page_meta.get('text', '')[:1000]}"
        )
        ai_result = await smart_ask(analysis_prompt, timeout=30)
    except Exception as e:
        ai_result = {"code": 500, "msg": f"AI分析失败: {e}"}

    cost = int((time.time() - t0) * 1000)
    data = {
        "screenshot_path": screenshot_result,
        "page_url": page_meta.get("url"),
        "page_title": page_meta.get("title"),
        "analysis": ai_result.get("data", ai_result.get("msg", "")),
        "cost_time": cost,
    }
    _log_operation("screenshot_and_ask", {"question": question[:100]}, _ok(data), cost)
    _record_to_session("screenshot_and_ask", {"question": question[:100]}, _ok(data))
    return _ok(data)


@tool("page_monitor", "监控页面变化：DOM变化/URL跳转/网络请求")
async def page_monitor(action: str = "snapshot", url: str = "",
                       duration: int = 5) -> Dict:
    """页面监控。

    Args:
        action: snapshot(快照) / watch(监听变化) / diff(对比快照)
        url: 快照时的URL（可选，不填用当前页）
        duration: watch模式监听时长（秒，上限30）
    """
    t0 = time.time()
    duration = min(duration, 30)

    if action == "snapshot":
        if url:
            from .page import navigate
            nav_result = await navigate(url)
            if nav_result.get("code") != 200:
                return nav_result

        js = """JSON.stringify({
            url: location.href,
            title: document.title,
            bodyLength: document.body.innerHTML.length,
            textLength: document.body.innerText.length,
            links: document.querySelectorAll('a').length,
            images: document.querySelectorAll('img').length,
            forms: document.querySelectorAll('form').length,
            inputs: document.querySelectorAll('input').length,
            buttons: document.querySelectorAll('button').length,
            iframes: document.querySelectorAll('iframe').length,
            scripts: document.querySelectorAll('script').length,
            textHash: Array.from(document.body.innerText).reduce(
                (h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0
            ).toString(36),
            htmlHash: Array.from(document.body.innerHTML).reduce(
                (h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0
            ).toString(36)
        })"""
        result = await _exec_js(js)
        cost = int((time.time() - t0) * 1000)

        if result.get("code") == 200:
            try:
                data = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
                data["cost_time"] = cost
                _log_operation("page_monitor", {"action": "snapshot"}, _ok(data), cost)
                _record_to_session("page_monitor", {"action": "snapshot"}, _ok(data))
                return _ok(data)
            except Exception as e:
                logger.debug("caught exception: %s", e)
        return result

    elif action == "watch":
        # 监听页面变化
        snapshots = []
        for i in range(duration * 2):
            js = """JSON.stringify({
                url: location.href,
                textLen: document.body.innerText.length,
                domLen: document.body.innerHTML.length,
                textHash: Array.from(document.body.innerText).reduce(
                    (h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0
                ).toString(36),
            })"""
            result = await _exec_js(js)
            if result.get("code") == 200:
                try:
                    snap = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
                    snap["timestamp"] = i * 0.5
                    snapshots.append(snap)
                except Exception as e:
                    logger.debug("caught exception: %s", e)
            await asyncio.sleep(0.5)

        # 检测变化
        changes = []
        for i in range(1, len(snapshots)):
            prev, curr = snapshots[i - 1], snapshots[i]
            if prev.get("url") != curr.get("url"):
                changes.append({"type": "url_change", "from": prev.get("url"), "to": curr.get("url")})
            elif prev.get("textHash") != curr.get("textHash"):
                changes.append({"type": "dom_change", "at": curr.get("timestamp"),
                                "text_delta": curr.get("textLen", 0) - prev.get("textLen", 0)})

        cost = int((time.time() - t0) * 1000)
        data = {"duration": duration, "snapshots": len(snapshots),
                "changes": changes, "has_changes": len(changes) > 0, "cost_time": cost}
        _log_operation("page_monitor", {"action": "watch", "duration": duration}, _ok(data), cost)
        _record_to_session("page_monitor", {"action": "watch"}, _ok(data))
        return _ok(data)

    return _err(106, f"未知操作: {action}（支持: snapshot/watch）")
