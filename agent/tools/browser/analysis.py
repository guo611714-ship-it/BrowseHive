"""浏览器工具 — 多模态分析（截图、文本提取、OCR）"""

import time
import logging
from typing import Dict

from ..tool_registry import tool, cached
from .browser_client import capture_screenshot
from .utils import _ok, _err, _log_operation
from .session import _record_to_session
from .page import _exec_js

logger = logging.getLogger(__name__)


@tool("screenshot_analyze", "截取页面截图并返回路径")
async def screenshot_analyze(area: str = "full") -> Dict:
    """截取页面截图（委托BrowserClient）"""
    t0 = time.time()
    result = await capture_screenshot()
    cost = int((time.time() - t0) * 1000)

    if "error" in result:
        _log_operation("screenshot_analyze", {"area": area}, _err(500, result["error"]), cost)
        return _err(500, result["error"])

    data = {"screenshot_path": result["path"], "size": result["size"], "cost_time": cost}
    _log_operation("screenshot_analyze", {"area": area}, _ok(data), cost)
    _record_to_session("screenshot_analyze", {"area": area}, _ok(data))
    return _ok(data)


@tool("get_page_text", "提取页面文本内容")
@cached(ttl=10)
async def get_page_text(max_length: int = 10000) -> Dict:
    """提取页面文本内容"""
    t0 = time.time()
    js = f"""(() => {{
        const text = document.body.innerText || document.body.textContent || '';
        return text.substring(0, {max_length});
    }})()"""
    result = await _exec_js(js)
    cost = int((time.time() - t0) * 1000)

    if result.get("code") == 200:
        return _ok({"content": result.get("data", ""), "length": len(result.get("data", "")), "cost_time": cost})
    return result


@tool("get_page_ocr", "获取当前浏览器页面的OCR文本")
async def get_page_ocr() -> Dict:
    """获取页面OCR文本"""
    text_result = await get_page_text(max_length=5000)
    if text_result.get("code") != 200:
        logger.warning(f"get_page_ocr: underlying page text extraction failed: {text_result.get('msg')}")
        return _err(text_result.get("code", 500), f"OCR失败: {text_result.get('msg', '未知错误')}")
    return _ok({
        "ocr_text": text_result.get("data", {}).get("content", ""),
        "cost_time": text_result.get("data", {}).get("cost_time", 0)
    })
