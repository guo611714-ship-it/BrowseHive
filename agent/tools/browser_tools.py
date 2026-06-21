"""浏览器 AI 工具集 — 基于统一BrowserClient + 内置模型 + 多模态分析

此文件为向后兼容的 facade。实际实现已拆分至 browser/ 子模块：
  browser/session.py       — 会话管理
  browser/page.py          — CDP 页面操作
  browser/analysis.py      — 多模态分析
  browser/ai_search.py     — AI 搜索与对话
  browser/advanced.py      — JS执行/多标签/智能等待/表单/上传/Cookie
  browser/intelligence.py  — 截图+AI分析/页面监控
  browser/utils.py         — 通用工具函数
"""

from .browser import (
    # session
    start_browser_session,
    end_browser_session,
    get_session_memory,
    # page
    navigate,
    click_element,
    type_text,
    scroll_page,
    wait_for_element,
    download_file,
    # analysis
    screenshot_analyze,
    get_page_text,
    get_page_ocr,
    # ai_search
    ask_doubao,
    ask_deepseek_browser,
    ask_bing,
    ask_ouyi,
    ask_kimi,
    ask_chatglm,
    smart_ask,
    browser_status,
    batch_ask,
    # advanced (Phase 1+2+3)
    exec_js_tool,
    multi_tab,
    wait_for,
    fill_form,
    upload_file,
    manage_cookie,
    batch_js,
    # intelligence (Phase 3)
    screenshot_and_ask,
    page_monitor,
)

# 内部函数也保留导出，供外部直接引用时可用
from .browser.utils import (
    _ok,
    _err,
    _safe_js_str,
    _safe_js_selector,
    _log_operation,
)
from .browser.page import _exec_js
from .browser.ai_search import _get_chat_engine, _http_fallback
from .browser.session import _record_to_session

__all__ = [
    # public (original)
    "start_browser_session", "end_browser_session", "get_session_memory",
    "navigate", "click_element", "type_text", "scroll_page",
    "wait_for_element", "download_file",
    "screenshot_analyze", "get_page_text", "get_page_ocr",
    "ask_doubao", "ask_deepseek_browser", "ask_bing", "ask_ouyi",
    "ask_kimi", "ask_chatglm",
    "smart_ask", "browser_status", "batch_ask",
    # public (new: Phase 1+2+3)
    "exec_js_tool", "multi_tab", "wait_for", "fill_form",
    "upload_file", "manage_cookie", "batch_js",
    # public (new: Phase 3)
    "screenshot_and_ask", "page_monitor",
    # internal (backward compat)
    "_ok", "_err", "_safe_js_str", "_safe_js_selector", "_log_operation",
    "_exec_js", "_get_chat_engine", "_http_fallback", "_record_to_session",
]
