"""浏览器工具子模块 — 导出所有公共函数"""

from .session import start_browser_session, end_browser_session, get_session_memory
from .page import navigate, click_element, type_text, scroll_page, wait_for_element, download_file
from .analysis import screenshot_analyze, get_page_text, get_page_ocr
from .ai_search import (
    ask_doubao, ask_deepseek_browser, ask_bing, ask_ouyi,
    ask_kimi, ask_chatglm,
    smart_ask, browser_status, batch_ask,
)
from .advanced import (
    exec_js_tool, multi_tab, wait_for, fill_form, upload_file, manage_cookie,
    batch_js,
)
from .intelligence import screenshot_and_ask, page_monitor
from .platform_router import TaskRouter, RouteResult, get_router

__all__ = [
    # session
    "start_browser_session", "end_browser_session", "get_session_memory",
    # page
    "navigate", "click_element", "type_text", "scroll_page",
    "wait_for_element", "download_file",
    # analysis
    "screenshot_analyze", "get_page_text", "get_page_ocr",
    # ai_search
    "ask_doubao", "ask_deepseek_browser", "ask_bing", "ask_ouyi",
    "ask_kimi", "ask_chatglm",
    "smart_ask", "browser_status", "batch_ask",
    # advanced (Phase 1+2+3)
    "exec_js_tool", "multi_tab", "wait_for", "fill_form",
    "upload_file", "manage_cookie", "batch_js",
    # intelligence (Phase 3)
    "screenshot_and_ask", "page_monitor",
    # platform router
    "TaskRouter", "RouteResult", "get_router",
]
