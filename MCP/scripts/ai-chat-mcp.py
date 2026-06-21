#!/usr/bin/env python3
"""AI Chat MCP Server - 简化架构版本.

核心功能：
- 多平台AI问答 (豆包/DeepSeek/火山引擎/欧亿AI)
- 智能路由和任务拆分
- 浏览器自动化
- 缓存、限流、重试
"""

import os
import sys
import time
import asyncio
from mcp.server.fastmcp import FastMCP

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUNBUFFERED"] = "1"

mcp = FastMCP("ai-chat")

# 延迟导入核心模块，避免启动时阻塞
_core_initialized = False
_config = None
_platforms = None
_chat_engine = None
_cache_manager = None
_monitor = None
_session_manager = None
_is_login_page = None
_assess_complexity = None
_browser_agent = None

def _info(msg):
    print(f"[{time.strftime('%H:%M:%S')}] INFO: {msg}", file=sys.stderr)

def _ensure_core():
    """延迟初始化核心模块."""
    global _core_initialized, _config, _platforms, _chat_engine, _cache_manager, _monitor, _session_manager, _is_login_page, _assess_complexity, _browser_agent
    if _core_initialized:
        return

    from core import config as _config_mod
    from core.platforms import PLATFORMS as _platforms_mod, is_login_page as _is_login_page_mod
    from core.chat_engine import chat_engine as _chat_engine_mod
    from core.cache_manager import cache_manager as _cache_manager_mod
    from core.monitor import monitor as _monitor_mod, session_manager as _session_manager_mod
    from browser_agent import get_browser_agent as _get_browser_agent

    _config = _config_mod
    _platforms = _platforms_mod
    _is_login_page = _is_login_page_mod
    _chat_engine = _chat_engine_mod
    _cache_manager = _cache_manager_mod
    _monitor = _monitor_mod
    _session_manager = _session_manager_mod
    _browser_agent = _get_browser_agent()

    _core_initialized = True

# ============== MCP 工具 ==============

@mcp.tool()
async def ask_doubao(message: str) -> str:
    """豆包：中文能力最强，润色/写作/翻译/创意."""
    _ensure_core()
    cached = await _cache_manager.get_response("doubao", message)
    if cached:
        return cached
    result = await _chat_engine.chat("doubao", message, 120)
    return result

@mcp.tool()
async def ask_deepseek(message: str) -> str:
    """DeepSeek：专业技术，代码/推理/数学/分析."""
    _ensure_core()
    cached = await _cache_manager.get_response("deepseek", message)
    if cached:
        return cached
    result = await _chat_engine.chat("deepseek", message, 120)
    return result

@mcp.tool()
async def ask_volcengine(message: str) -> str:
    """火山引擎：企业级，代码/技术分析/AI Agents."""
    _ensure_core()
    cached = await _cache_manager.get_response("volcengine", message)
    if cached:
        return cached
    result = await _chat_engine.chat("volcengine", message, 120)
    return result

@mcp.tool()
async def ask_ouyi(message: str) -> str:
    """欧亿AI：多功能，绘图/思维导图/API/框架."""
    _ensure_core()
    cached = await _cache_manager.get_response("ouyi", message)
    if cached:
        return cached
    result = await _chat_engine.chat("ouyi", message, 120)
    return result

@mcp.tool()
async def open_all_platforms() -> str:
    """打开所有AI平台，返回状态."""
    _ensure_core()
    async def _open_one(key):
        info = _platforms[key]
        try:
            if not _browser_agent.ensure_ready():
                return f"[SKIP] {info['name']}: 浏览器不可用"
            # 打开平台页面
            ok = _browser_agent.open_platform(key, info["url"])
            if not ok:
                return f"[FAIL] {info['name']}: 打开失败"
            # 检查当前 URL
            current_url = _browser_agent.get_current_url() or ""
            login = _is_login_page(current_url, key)
            status = "需要登录" if login else "已登录"
            return f"[OK] {info['name']} ({info['mode']}) — {status}"
        except Exception as e:
            return f"[FAIL] {info['name']}: {str(e)[:50]}"

    # 支持所有已配置平台，不只是固定的3个
    keys = list(_platforms.keys())
    results = await asyncio.gather(*[_open_one(k) for k in keys])
    return "=== AI平台状态 ===\n\n" + "\n\n".join(results)

@mcp.tool()
async def smart_ask(message: str) -> str:
    """智能路由：根据内容自动选平台."""
    _ensure_core()
    assessment = _chat_engine.assess_complexity(message)
    platform = assessment["platform"]
    level = assessment["level"]
    reason = assessment["reason"]

    if assessment.get("tree") and assessment.get("tree_config"):
        cfg = assessment["tree_config"]
        primary = cfg["layer1"]
        secondary = cfg.get("layer2", [])

        primary_result = await _chat_engine.chat(primary, message, 120)
        primary_name = _platforms[primary]["name"]

        if not secondary:
            return f"[L{level}|{reason}] [{primary_name}] {primary_result}"

        secondary_results = []
        for pk in secondary:
            if pk not in _platforms:
                secondary_results.append(f"[未知平台] {pk}")
                continue
            try:
                r = await _chat_engine.chat(pk, message, 120)
                secondary_results.append(f"[{_platforms[pk]['name']}] {r[:500]}")
            except Exception as e:
                secondary_results.append(f"[{_platforms[pk]['name']}] 错误: {str(e)[:100]}")

        combined = f"[L{level}|{reason}] 主平台[{primary_name}]:\n{primary_result}"
        if secondary_results:
            combined += "\n\n辅助平台:\n" + "\n".join(secondary_results)
        return combined

    platform_name = _platforms.get(platform, {}).get('name', platform)
    result = await _chat_engine.chat(platform, message, 120)
    return f"[L{level}|{reason}] [{platform_name}] {result}"

@mcp.tool()
async def batch_ask(message: str, platforms: str = "doubao,deepseek") -> str:
    """批量发送到多个平台."""
    _ensure_core()
    targets = [p.strip() for p in platforms.split(",") if p.strip()]
    invalid = [p for p in targets if p not in _platforms]
    if invalid:
        return f"未知平台: {invalid}，可选: {list(_platforms.keys())}"

    async def _ask_one(p):
        try:
            r = await _chat_engine.chat(p, message, 120)
            name = _platforms[p]["name"]
            return f"[{name}]\n{r[:800]}"
        except Exception as e:
            return f"[{_platforms[p]['name']}] 错误: {e}"

    results = await asyncio.gather(*[_ask_one(p) for p in targets], return_exceptions=True)
    parts = [f"{r}\n" if not isinstance(r, Exception) else f"[错误] {r}\n" for r in results]
    return "=== 批量结果 ===\n\n" + "\n".join(parts)

if __name__ == "__main__":
    _info("Starting AI Chat MCP Server (Simplified)...")
    try:
        mcp.run()
    except KeyboardInterrupt:
        _info("Shutting down...")
        sys.exit(0)
