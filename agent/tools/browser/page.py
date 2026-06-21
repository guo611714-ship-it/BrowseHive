"""浏览器工具 — CDP 页面操作"""

import json
import time
import asyncio
import logging
import re
import os
from typing import Dict
from pathlib import Path

from ..tool_registry import tool
from .browser_client import exec_js as _cdp_exec_js
from .utils import _ok, _err, _safe_js_str, _safe_js_selector, _log_operation
from .session import _record_to_session

logger = logging.getLogger(__name__)


async def _exec_js(js_code: str) -> Dict:
    """在当前页面执行 JavaScript（委托BrowserClient）"""
    result = await _cdp_exec_js(js_code)
    if "error" in result:
        return _err(500, result["error"])
    return _ok(result.get("data"))


@tool("navigate", "导航到指定URL")
async def navigate(url: str) -> Dict:
    """导航到指定URL"""
    if not url.startswith(("http://", "https://")):
        return _err(101, "URL必须以http://或https://开头")
    if len(url) > 2048:
        return _err(102, "URL长度不能超过2048字符")

    t0 = time.time()
    safe_url = _safe_js_str(url)
    result = await _exec_js(f"window.location.href = '{safe_url}'; 'ok'")

    if result.get("code") == 200:
        # 等待页面加载（检测 document.readyState）
        for _ in range(10):
            await asyncio.sleep(0.5)
            ready = await _exec_js("document.readyState")
            if ready.get("data") == "complete":
                break
        page_result = await _exec_js("document.title")
        cost = int((time.time() - t0) * 1000)
        data = {"page_url": url, "title": page_result.get("data"), "cost_time": cost}
        _log_operation("navigate", {"url": url}, _ok(data), cost)
        _record_to_session("navigate", {"url": url}, _ok(data))
        return _ok(data)
    cost = int((time.time() - t0) * 1000)
    _log_operation("navigate", {"url": url}, result, cost)
    _record_to_session("navigate", {"url": url}, result)
    return result


@tool("click_element", "点击页面元素（CSS选择器或XPath）")
async def click_element(selector: str) -> Dict:
    """点击页面元素（CSS选择器或XPath）"""
    if not selector:
        return _err(103, "选择器不能为空")

    t0 = time.time()
    safe_sel = _safe_js_selector(selector)

    if selector.startswith("//") or selector.startswith("("):
        js = f"""(() => {{
            var el = document.evaluate('{safe_sel}', document, null, 9, null).singleNodeValue;
            if (!el) return null;
            el.click();
            return el.textContent.substring(0, 100);
        }})()"""
    else:
        js = f"""(() => {{
            var el = document.querySelector('{safe_sel}');
            if (!el) return null;
            el.click();
            return el.textContent.substring(0, 100);
        }})()"""

    result = await _exec_js(js)
    cost = int((time.time() - t0) * 1000)

    if result.get("code") == 200 and result.get("data") is not None and result.get("data") != {}:
        data = {"element_content": result["data"], "cost_time": cost}
        _log_operation("click_element", {"selector": selector}, _ok(data), cost)
        _record_to_session("click_element", {"selector": selector}, _ok(data))
        return _ok(data)
    elif result.get("code") == 200:
        _log_operation("click_element", {"selector": selector}, _err(302, "未找到元素"), cost)
        _record_to_session("click_element", {"selector": selector}, _err(302, "未找到元素"))
        return _err(302, f"未找到元素: {selector}")
    _log_operation("click_element", {"selector": selector}, result, cost)
    _record_to_session("click_element", {"selector": selector}, result)
    return result


@tool("type_text", "在输入框中输入文本")
async def type_text(selector: str, text: str) -> Dict:
    """在输入框中输入文本"""
    if not selector:
        return _err(103, "选择器不能为空")
    if len(text) > 10000:
        return _err(104, "输入内容不能超过10000字符")

    t0 = time.time()
    safe_sel = _safe_js_selector(selector)
    safe_text = _safe_js_str(text)

    js = f"""(() => {{
        var el = document.querySelector('{safe_sel}');
        if (!el) return null;
        el.focus();
        el.value = '{safe_text}';
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'ok';
    }})()"""

    result = await _exec_js(js)
    cost = int((time.time() - t0) * 1000)

    if result.get("code") == 200 and result.get("data") == "ok":
        _log_operation("type_text", {"selector": selector}, _ok({"cost_time": cost}), cost)
        _record_to_session("type_text", {"selector": selector}, _ok({"cost_time": cost}))
        return _ok({"cost_time": cost})
    elif result.get("code") == 200:
        return _err(302, f"未找到输入框: {selector}")
    return result


@tool("scroll_page", "滚动页面")
async def scroll_page(direction: str = "down", amount: int = 500) -> Dict:
    """滚动页面"""
    amount = max(0, min(amount, 10000))  # 限制范围
    t0 = time.time()
    js = f"window.scrollBy(0, {amount if direction == 'down' else -amount}); 'ok'"
    result = await _exec_js(js)
    cost = int((time.time() - t0) * 1000)

    if result.get("code") == 200:
        data = {"direction": direction, "amount": amount, "cost_time": cost}
        _log_operation("scroll_page", {"direction": direction}, _ok(data), cost)
        _record_to_session("scroll_page", {"direction": direction}, _ok(data))
        return _ok(data)
    return result


@tool("wait_for_element", "等待页面元素出现")
async def wait_for_element(selector: str, timeout: int = 10) -> Dict:
    """等待元素出现"""
    if not selector:
        return _err(103, "选择器不能为空")
    timeout = min(timeout, 30)
    safe_sel = _safe_js_selector(selector)

    t0 = time.time()
    # 轮询检测
    for _ in range(timeout * 2):
        js = f"""(() => {{
            var el = document.querySelector('{safe_sel}');
            if (el) return JSON.stringify({{found: true, text: el.textContent.substring(0, 200)}});
            return JSON.stringify({{found: false}});
        }})()"""
        result = await _exec_js(js)
        if result.get("code") == 200:
            try:
                data = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
                if data.get("found"):
                    cost = int((time.time() - t0) * 1000)
                    return _ok({"found": True, "element_content": data.get("text", ""), "cost_time": cost})
            except Exception as e:
                logger.debug("caught exception: %s", e)
        await asyncio.sleep(0.5)

    cost = int((time.time() - t0) * 1000)
    return _err(303, f"等待超时: {selector}")


@tool("download_file", "下载文件到指定路径")
async def download_file(url: str, save_path: str = None) -> Dict:
    """下载文件（限制100MB，路径安全检查）"""
    if not url.startswith(("http://", "https://")):
        return _err(101, "URL必须以http://或https://开头")

    t0 = time.time()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            # 流式下载，限制大小
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return _err(304, f"下载失败: HTTP {resp.status_code}")

                if not save_path:
                    filename = url.split("/")[-1].split("?")[0] or "download"
                    # 过滤不安全文件名字符
                    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                    save_path = str(Path.home() / "Downloads" / filename)

                # 路径安全检查：确保在Downloads目录内
                save_path = str(Path(save_path).resolve())
                downloads_dir = str((Path.home() / "Downloads").resolve()) + os.sep
                if not save_path.startswith(downloads_dir):
                    return _err(403, "保存路径必须在Downloads目录内")

                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                # 流式写入，限制100MB
                total = 0
                MAX_SIZE = 100 * 1024 * 1024
                with open(save_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        total += len(chunk)
                        if total > MAX_SIZE:
                            f.close()
                            Path(save_path).unlink(missing_ok=True)
                            return _err(413, f"文件超过100MB限制")
                        f.write(chunk)

            cost = int((time.time() - t0) * 1000)
            return _ok({"save_path": save_path, "size": total, "cost_time": cost})
    except Exception as e:
        return _err(500, f"下载失败: {e}")
