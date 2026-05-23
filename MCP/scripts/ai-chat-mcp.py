#!/usr/bin/env python3
"""AI Chat MCP Server — 一键调用豆包/DeepSeek/欧亿AI/火山引擎."""

import asyncio
import gc
import os
import time
import threading
import sys
import hashlib
import json
import re
import random
import datetime
from functools import wraps

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUNBUFFERED"] = "1"

# 结构化日志
_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai-chat-mcp.log")
_LOG_LEVEL = os.environ.get("AI_CHAT_LOG_LEVEL", "INFO").upper()

_LOG_MAX_SIZE = 5 * 1024 * 1024  # 5MB轮转

def _log(level: str, msg: str, **kwargs):
    """结构化日志：[时间] [级别] 消息 {额外数据}"""
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        level = "INFO"
    levels = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
    if levels.get(level, 1) < levels.get(_LOG_LEVEL, 1):
        return
    # 日志轮转
    try:
        if os.path.exists(_LOG) and os.path.getsize(_LOG) > _LOG_MAX_SIZE:
            backup = _LOG + ".1"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(_LOG, backup)
    except Exception:
        pass
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S.') + f"{int(time.time()*1000)%1000:03d}"
    extra = f" {kwargs}" if kwargs else ""
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level}] {msg}{extra}\n")

def _dbg(msg, **kwargs):
    _log("DEBUG", msg, **kwargs)

def _info(msg, **kwargs):
    _log("INFO", msg, **kwargs)

def _warn(msg, **kwargs):
    _log("WARNING", msg, **kwargs)

def _err(msg, **kwargs):
    _log("ERROR", msg, **kwargs)
_info("=== MCP SERVER START ===")
_info(f"Python: {sys.executable}")
_info(f"Args: {sys.argv}")

from mcp.server.fastmcp import FastMCP

# ── browser-harness/browser-use 集成 ──────────────────────────────
try:
    from browser_agent import get_browser_agent, BrowserAgent, get_stats as get_browser_use_stats, reset_browser_agent
    _BROWSER_USE_AVAILABLE = True
    _info("browser-harness/browser-use module loaded successfully")
except ImportError as e:
    _BROWSER_USE_AVAILABLE = False
    _warn(f"browser-harness/browser-use not available: {e}")
    def get_browser_use_stats():
        return {"error": "browser-harness/browser-use not available"}
    def reset_browser_agent():
        pass

# ── MCP Server ──────────────────────────────────────────────────
mcp = FastMCP("ai-chat")
_info("FastMCP created")

# ── Global state ────────────────────────────────────────────────
_browser = None
_playwright_obj = None
# 使用与Playwright MCP相同的持久化目录，共享cookies/登录状态
_fetch_stats = {}  # {platform: {"success": N, "fail": N, "total_time": float}}
_CDP_ENDPOINT = os.environ.get("AI_CHAT_CDP_ENDPOINT", "")  # CDP端点，优先使用
_error_stats = {}  # {platform: {"login": N, "timeout": N, "error": N, "unknown": N}}
_error_log = []  # [{"platform": str, "type": str, "msg": str, "ts": float}]
_checkpoints = {}  # {task_id: {"task": str, "platform_results": dict, "iteration": int}}
_perf_log = []  # [{"tool": str, "time": float, "ok": bool, "ts": str}]  最近100条
_PERF_MAX = 100
_task_queue = []  # [{"task": str, "platforms": list, "priority": int, "ts": str, "status": str}]
_QUEUE_MAX = 20
_response_cache = {}  # {(platform, message_hash): {"result": str, "ts": float, "hits": int}}
_CACHE_TTL = 300  # 缓存有效期5分钟
_CACHE_MAX = 100  # 最大缓存条目数
_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}  # 缓存统计
_tool_call_cache = {}  # {(tool_name, args_hash): {"result": str, "ts": float}}
_TOOL_CACHE_TTL = 60  # 工具调用缓存60秒
_active_requests = {}  # {platform: {"count": int, "start": float, "total": int}}
_page_pool = {}  # {platform: {"page": Page, "last_used": float, "ready": bool}} 页面池
_PAGE_POOL_TTL = 300  # 页面池条目5分钟过期
_usage_tracker = {
    "platform_queries": {},  # {platform: {"count": int, "last_used": str}}
    "message_patterns": [],  # [{"prefix": str, "platform": str, "ts": str}] 最近50条
    "hourly_pattern": {},    # {hour: {"platform": int}} 按小时统计平台使用
}
_USAGE_MAX = 50  # message_patterns最大条目数

# 上下文缓存：缓存高频重复的上下文片段，减少Token消耗
_context_cache = {}  # {"context_key": {"text": str, "hits": int, "tokens": int, "ts": float}}
_CONTEXT_CACHE_TTL = 600  # 上下文缓存10分钟过期
_CONTEXT_CACHE_MAX = 30  # 最大缓存条目数
_context_cache_stats = {"hits": 0, "misses": 0, "tokens_saved": 0}

# 请求合并：相同请求并发时共享结果
_inflight_requests = {}  # {(platform, msg_hash): {"future": asyncio.Future, "count": int}}
_coalesced_stats = {"saved": 0, "total": 0}


def _evict_cache():
    """LRU缓存淘汰：移除过期和最少使用的条目。"""
    now = time.time()
    # 1. 移除过期条目
    expired = [k for k, v in _response_cache.items() if (now - v["ts"]) > _CACHE_TTL]
    for k in expired:
        del _response_cache[k]
        _cache_stats["evictions"] += 1

    # 2. 如果超过限制，移除最少使用的
    if len(_response_cache) > _CACHE_MAX:
        sorted_keys = sorted(_response_cache.keys(), key=lambda k: _response_cache[k].get("hits", 0))
        while len(_response_cache) > _CACHE_MAX:
            del _response_cache[sorted_keys.pop(0)]
            _cache_stats["evictions"] += 1


def _invalidate_platform_cache(platform: str):
    """清除指定平台的所有缓存条目（平台状态变化时调用）。"""
    keys_to_remove = [k for k in _response_cache if k[0] == platform]
    for k in keys_to_remove:
        del _response_cache[k]
        _cache_stats["evictions"] += 1
    # 同时清除页面池
    if platform in _page_pool:
        del _page_pool[platform]
    return len(keys_to_remove)


def _invalidate_by_pattern(pattern: str):
    """按消息模式前缀清除缓存。"""
    keys_to_remove = []
    for k, v in _response_cache.items():
        if pattern in v.get("message", ""):
            keys_to_remove.append(k)
    for k in keys_to_remove:
        del _response_cache[k]
        _cache_stats["evictions"] += 1
    return len(keys_to_remove)


def _clear_all_cache():
    """完全清除所有缓存（响应缓存+工具缓存+消息去重+页面池）。"""
    counts = {
        "response": len(_response_cache),
        "tool": len(_tool_call_cache),
        "dedup": len(_message_dedup),
        "page_pool": len(_page_pool),
    }
    _response_cache.clear()
    _tool_call_cache.clear()
    _message_dedup.clear()
    _page_pool.clear()
    _cache_stats["evictions"] += counts["response"]
    return counts


def _track_usage(platform: str, message: str):
    """记录查询使用模式，用于智能缓存预热。"""
    now_str = time.strftime("%Y-%m-%dT%H:%M:%S")
    hour = time.strftime("%H")
    # 平台查询计数
    if platform not in _usage_tracker["platform_queries"]:
        _usage_tracker["platform_queries"][platform] = {"count": 0, "last_used": ""}
    _usage_tracker["platform_queries"][platform]["count"] += 1
    _usage_tracker["platform_queries"][platform]["last_used"] = now_str
    # 消息模式提取（取前20字符作为模式前缀）
    prefix = message[:20].strip()
    _usage_tracker["message_patterns"].append({"prefix": prefix, "platform": platform, "ts": now_str})
    if len(_usage_tracker["message_patterns"]) > _USAGE_MAX:
        _usage_tracker["message_patterns"].pop(0)
    # 小时使用模式
    if hour not in _usage_tracker["hourly_pattern"]:
        _usage_tracker["hourly_pattern"][hour] = {}
    _usage_tracker["hourly_pattern"][hour][platform] = _usage_tracker["hourly_pattern"][hour].get(platform, 0) + 1


def _get_context_cache_key(text: str) -> str:
    """生成上下文缓存键：基于内容的MD5哈希。"""
    normalized = text.strip().lower()[:200]  # 取前200字符标准化
    return hashlib.md5(normalized.encode()).hexdigest()


def _evict_context_cache():
    """清理过期的上下文缓存条目。"""
    now = time.time()
    expired = [k for k, v in _context_cache.items() if (now - v["ts"]) > _CONTEXT_CACHE_TTL]
    for k in expired:
        del _context_cache[k]

    # 超限时按命中率淘汰
    if len(_context_cache) > _CONTEXT_CACHE_MAX:
        sorted_keys = sorted(_context_cache.keys(), key=lambda k: _context_cache[k]["hits"])
        while len(_context_cache) > _CONTEXT_CACHE_MAX:
            del _context_cache[sorted_keys.pop(0)]


def _get_cached_context(text: str) -> str | None:
    """从上下文缓存获取。返回缓存文本或None。"""
    key = _get_context_cache_key(text)
    if key in _context_cache:
        entry = _context_cache[key]
        entry["hits"] += 1
        _context_cache_stats["hits"] += 1
        _context_cache_stats["tokens_saved"] += entry["tokens"]
        return entry["text"]
    _context_cache_stats["misses"] += 1
    return None


def _save_context_cache(text: str, tokens: int = 0):
    """保存到上下文缓存。"""
    key = _get_context_cache_key(text)
    _evict_context_cache()
    if tokens == 0:
        tokens = len(text) // 4  # 估算token数
    _context_cache[key] = {
        "text": text,
        "hits": 0,
        "tokens": tokens,
        "ts": time.time()
    }


_response_times = {}  # {platform: [float, ...]} 最近10次响应时间
_rate_limiter = {}  # {platform: [float, ...]} 最近请求时间戳
_message_dedup = {}  # {(platform, message_hash): float} 已发送消息时间戳
_message_dedup_content = {}  # {(platform, message_hash): str} 近似匹配用的消息内容
_cost_log = []  # [{"tool": str, "time": float, "tokens": int, "cached": bool, "ts": str}]  最近200条
_COST_MAX = 200
_reconnect_count = 0  # 浏览器重连次数
_health_status = {}  # {platform: {"ok": bool, "last_check": float, "latency": float}}
_audit_log = []  # [{"ts": str, "tool": str, "args": dict, "result_preview": str, "time": float, "ok": bool}]  最近50条
_AUDIT_MAX = 50
_response_trend = {}  # {platform: [(ts, latency), ...]} 按小时聚合的响应时间
_health_score_history = []  # [{"ts": str, "score": int, "details": dict}]  最近50次评分
_connection_health = {
    "last_check": 0,  # 上次检查时间
    "check_interval": 60,  # 检查间隔(秒)
    "consecutive_failures": 0,  # 连续检查失败次数
    "last_reconnect": 0,  # 上次重连时间
    "history": [],  # [{"ts": float, "ok": bool, "pages": int, "memory_mb": float}]
}

# 任务链引擎
_task_chains = {}  # {chain_id: {"name": str, "steps": [...], "results": [...], "status": str}}
_chain_counter = 0

# 工作流模板
_WORKFLOW_TEMPLATES = {
    "research_write": {
        "name": "调研+写作",
        "description": "先用DeepSeek调研，再用豆包润色",
        "steps": [
            {"platform": "deepseek", "message": "调研以下主题并给出详细分析：{topic}"},
            {"platform": "doubao", "message": "将以下调研内容润色改写成专业文案：\n{result}"},
        ],
    },
    "compare_analyze": {
        "name": "对比分析",
        "description": "双平台对比分析同一问题",
        "steps": [
            {"platform": "deepseek", "message": "从技术角度分析：{topic}"},
            {"platform": "doubao", "message": "从产品角度分析：{topic}"},
        ],
    },
    "translate_polish": {
        "name": "翻译+润色",
        "description": "先翻译再润色",
        "steps": [
            {"platform": "deepseek", "message": "将以下内容翻译成英文：{text}"},
            {"platform": "doubao", "message": "润色以下英文翻译，使其更地道：\n{result}"},
        ],
    },
    "code_review": {
        "name": "代码审查",
        "description": "DeepSeek代码分析+豆包文档生成",
        "steps": [
            {"platform": "deepseek", "message": "审查以下代码并给出改进建议：\n{code}"},
            {"platform": "doubao", "message": "根据以下代码审查结果，生成代码审查报告：\n{result}"},
        ],
    },
}

# ── 热更新配置 ──────────────────────────────────────────────────
_config = {
    "max_retries": 3,
    "retry_delay": 2,
    "max_pages": 5,
    "page_idle_timeout": 600,
    "chat_timeout": 120,
    "streaming_timeout": 30,
    "no_response_timeout": 15,
    "log_level": "INFO",
    "max_response_length": 2000,  # 工具响应最大字符数
    "schema_version": "1.1.0",    # 工具schema版本
    "tool_mode": "full",           # 工具集模式: full/browser-only/api-only/smart
    "headless": False,             # 无头浏览器模式（CI/CD用）
    "memory_warn_mb": 1500,        # 内存告警阈值(MB)
    "memory_critical_mb": 2000,    # 内存严重告警阈值(MB)
    "rate_limit_interval": 3,      # 同一平台最小请求间隔(秒)
    "rate_limit_window": 60,       # 限流窗口(秒)
    "rate_limit_max": 10,          # 窗口内最大请求数
    "dedup_window": 300,           # 重复消息检测窗口(秒)
    "session_save_path": "",       # 会话保存路径（空=不保存）
    "screenshot_dir": "",          # 截图保存目录（空=不保存）
    "screenshot_on_error": True,   # 错误时自动截图
    "proxy_pool": [],              # 代理池 ["http://host:port", ...]
    "proxy_index": 0,              # 当前代理索引
    "proxy_enabled": False,        # 是否启用代理
    "retry_budget_max": 20,        # 全局重试预算上限
    "retry_budget_window": 60,     # 重试预算窗口(秒)
    "browser_use_enabled": True,   # 启用browser-use AI操控（失败自动降级到JS）
}

# 全局重试预算
_retry_budget = []  # [float, ...] 最近的重试时间戳

# 指纹轮换追踪
_FINGERPRINT_VIEWPORTS = [
    {"width": 1280, "height": 800},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
]
_FINGERPRINT_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]
_fingerprint_history = []  # [{"ts": str, "viewport": str, "ua": str, "mode": str}]  最近20次轮换记录
_FINGERPRINT_HISTORY_MAX = 20

# ── 工具集定义 ──────────────────────────────────────────────────
TOOL_SETS = {
    "full": None,  # None表示不过滤，使用全部工具
    "browser-only": [
        "ask_doubao", "ask_deepseek", "ask_volcengine", "smart_ask",
        "open_all_platforms", "login_platform", "check_login", "list_tabs",
    ],
    "api-only": [
        "execute_split", "run_benchmark", "get_fetch_stats",
        "get_config", "set_config", "get_coordination_status",
        "set_task", "get_context", "report_result", "split_task_tool",
    ],
    "smart": None,  # 动态检测任务类型
}

# ── 任务类型关键词映射 ──────────────────────────────────────────
TASK_KEYWORDS = {
    "browser": ["打开", "浏览", "页面", "标签", "截图", "抓取", "scroll", "navigate", "click"],
    "api": ["统计", "配置", "任务", "协调", "拆分", "基准", "config", "stats", "benchmark"],
}

# ── 双引擎协调状态 ──────────────────────────────────────────────
_coordination = {
    "current_task": "",           # 当前任务描述
    "platform_results": {},       # {platform: {"result": str, "context": str, "status": str}}
    "shared_context": {},         # 引擎间共享数据
    "iteration": 0,               # 当前迭代轮次
    "pending_tasks": [],          # 待执行任务队列
    "completed_tasks": [],        # 已完成任务
}

# ── 错误分类与检查点 ──────────────────────────────────────────
def _record_perf(tool: str, elapsed: float, ok: bool):
    """记录工具调用性能"""
    _perf_log.append({
        "tool": tool,
        "time": round(elapsed, 2),
        "ok": ok,
        "ts": time.strftime('%H:%M:%S'),
    })
    if len(_perf_log) > _PERF_MAX:
        _perf_log.pop(0)


def _record_cost(tool: str, elapsed: float, tokens: int = 0, cached: bool = False):
    """记录工具调用成本：耗时+token+缓存状态。"""
    _cost_log.append({
        "tool": tool,
        "time": round(elapsed, 2),
        "tokens": tokens,
        "cached": cached,
        "ts": time.strftime('%H:%M:%S'),
    })
    if len(_cost_log) > _COST_MAX:
        _cost_log.pop(0)


def _record_audit(tool: str, args: dict, result: str, elapsed: float, ok: bool):
    """记录工具调用审计日志：完整调用链路。"""
    _audit_log.append({
        "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
        "tool": tool,
        "args": {k: str(v)[:100] for k, v in args.items()},
        "result_preview": result[:200] if result else "",
        "time": round(elapsed, 2),
        "ok": ok,
    })
    if len(_audit_log) > _AUDIT_MAX:
        _audit_log.pop(0)


def _classify_error(platform: str, error_msg: str) -> str:
    """分类错误类型并记录统计"""
    msg = error_msg.lower()
    if "login" in msg or "登录" in msg or "sign" in msg:
        err_type = "login"
    elif "timeout" in msg or "超时" in msg:
        err_type = "timeout"
    elif "error" in msg or "错误" in msg:
        err_type = "error"
    else:
        err_type = "unknown"

    if platform not in _error_stats:
        _error_stats[platform] = {"login": 0, "timeout": 0, "error": 0, "unknown": 0}
    _error_stats[platform][err_type] += 1
    _error_log.append({"platform": platform, "type": err_type, "msg": error_msg[:200], "ts": time.time()})
    if len(_error_log) > 100:
        _error_log.pop(0)
    return err_type


def _decay_error_stats():
    """错误统计衰减：每30秒将错误计数减半，让平台有机会恢复。"""
    now = time.time()
    if not hasattr(_decay_error_stats, "_last_decay"):
        _decay_error_stats._last_decay = now
        return
    if now - _decay_error_stats._last_decay < 30:
        return
    _decay_error_stats._last_decay = now

    for pk in _error_stats:
        for err_type in _error_stats[pk]:
            if _error_stats[pk][err_type] > 0:
                _error_stats[pk][err_type] = max(0, _error_stats[pk][err_type] - 1)

def _save_checkpoint(task_id: str):
    """保存当前任务检查点"""
    _checkpoints[task_id] = {
        "task": _coordination.get("current_task", ""),
        "platform_results": dict(_coordination.get("platform_results", {})),
        "iteration": _coordination.get("iteration", 0),
    }

def _restore_checkpoint(task_id: str) -> bool:
    """恢复任务检查点"""
    cp = _checkpoints.get(task_id)
    if not cp:
        return False
    _coordination["current_task"] = cp["task"]
    _coordination["platform_results"] = dict(cp["platform_results"])
    _coordination["iteration"] = cp["iteration"]
    return True


# ── 工具过滤 ──────────────────────────────────────────────────
def _detect_task_type(task: str) -> str:
    """检测任务类型：browser/api/mixed"""
    if not task:
        return "mixed"
    task_lower = task.lower()
    has_browser = any(kw in task_lower for kw in TASK_KEYWORDS["browser"])
    has_api = any(kw in task_lower for kw in TASK_KEYWORDS["api"])
    if has_browser and not has_api:
        return "browser"
    elif has_api and not has_browser:
        return "api"
    return "mixed"


# 平台能力关键词映射
_PLATFORM_STRENGTHS = {
    "doubao": ["润色", "写作", "文案", "中文", "创意", "改写", "翻译", "总结", "简化"],
    "volcengine": ["代码", "编程", "算法", "技术", "分析", "推理", "调试", "架构", "优化"],
    "ouyi": ["图片", "图像", "画", "思维导图", "流程图", "可视化"],
    "deepseek": ["报告", "文档", "专业", "论文", "实验", "数据", "统计", "研究"],
}


def _recommend_platform(task: str) -> str:
    """智能平台推荐：结合任务匹配度+健康评分+历史表现，返回最优平台key。"""
    if not task:
        return ""
    task_lower = task.lower()

    # 1. 关键词匹配分 (0-10)
    keyword_scores = {}
    for platform, keywords in _PLATFORM_STRENGTHS.items():
        score = sum(1 for kw in keywords if kw in task_lower)
        keyword_scores[platform] = min(score * 2, 10)

    # 2. 健康评分 (0-10)
    health_scores = {}
    for pk in PLATFORMS:
        health = 10

        # 错误扣分
        stats = _error_stats.get(pk, {})
        total_err = sum(stats.values())
        if total_err > 5:
            health -= min(total_err * 0.5, 5)

        # 响应时间扣分
        times = _response_times.get(pk, [])
        if times:
            avg_time = sum(times) / len(times)
            if avg_time > 10:
                health -= min((avg_time - 10) * 0.3, 3)

        # 成功率加分
        fs = _fetch_stats.get(pk, {})
        total_fetch = fs.get("success", 0) + fs.get("fail", 0)
        if total_fetch > 0:
            success_rate = fs["success"] / total_fetch
            health += (success_rate - 0.5) * 4

        # 响应质量加分
        quality_scores = [q["score"] for q in _response_quality_log if q["platform"] == pk]
        if quality_scores:
            avg_quality = sum(quality_scores[-5:]) / min(len(quality_scores), 5)
            health += (avg_quality - 5) * 0.5  # 质量5分基础

        # 并发负载惩罚
        req_count = _active_requests.get(pk, {}).get("count", 0)
        if req_count > 0:
            health -= req_count * 0.5

        health_scores[pk] = max(0, min(health, 10))

    # 3. 综合评分 (关键词60% + 健康40%)
    final_scores = {}
    for pk in PLATFORMS:
        kw = keyword_scores.get(pk, 0)
        hp = health_scores.get(pk, 5)
        if kw == 0:
            final_scores[pk] = hp * 0.3
        else:
            final_scores[pk] = kw * 0.6 + hp * 0.4

    if not final_scores:
        return ""

    best = max(final_scores, key=final_scores.get)
    # 如果最高分太低，返回空
    if final_scores[best] < 1:
        return ""
    return best


def _summarize_response(text: str, max_sentences: int = 3) -> str:
    """从长响应中提取关键句子作为摘要。"""
    if not text or len(text) < 200:
        return text
    # 按句子分割（中英文句号、问号、感叹号）
    sentences = re.split(r'(?<=[。！？.!?])\s*', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if len(sentences) <= max_sentences:
        return text
    # 优先选择包含关键词的句子
    keywords = ['因此', '所以', '总结', '关键', '重要', '结论', '首先', '其次', '最后',
                'therefore', 'conclusion', 'summary', 'key', 'important', 'first', 'finally']
    scored = []
    for s in sentences:
        score = sum(1 for kw in keywords if kw in s.lower())
        scored.append((score, s))
    # 按分数排序，取前N句，保持原文顺序
    top = sorted(scored, key=lambda x: -x[0])[:max_sentences]
    result = ' '.join(s for _, s in sorted(top, key=lambda x: sentences.index(x[1])))
    return result + f"\n... [摘要: {len(text)}字 → {len(result)}字]"


def _score_response(text: str, message: str = "") -> dict:
    """评分响应质量：长度+结构+相关性+错误检测，返回{score, details, issues}"""
    if not text:
        return {"score": 0, "details": "空响应", "issues": ["empty"]}

    score = 0
    details = []
    issues = []

    # 长度评分 (0-25)
    length = len(text)
    if length < 10:
        score += 5
        details.append(f"过短({length}字)")
        issues.append("too_short")
    elif length < 50:
        score += 15
        details.append(f"较短({length}字)")
    elif length < 500:
        score += 25
        details.append(f"适中({length}字)")
    else:
        score += 20
        details.append(f"较长({length}字)")

    # 结构评分 (0-25)
    has_structure = False
    if '\n' in text:
        score += 8
        has_structure = True
    if any(c in text for c in ['1.', '2.', '一、', '二、', '•', '- ']):
        score += 8
        has_structure = True
    if has_structure:
        score += 9

    # 完整性评分 (0-20)
    if text.endswith(('。', '！', '？', '.', '!', '?', '】', '）')):
        score += 20
        details.append("完整结尾")
    elif text.endswith(('...', '…', '→', '：')):
        score += 10
        details.append("截断结尾")
        issues.append("truncated")
    else:
        score += 5

    # 相关性评分 (0-15)
    if message:
        msg_chars = set(message.replace(' ', ''))
        resp_chars = set(text.replace(' ', ''))
        overlap = len(msg_chars & resp_chars)
        relevance = min(overlap / max(len(msg_chars), 1) * 100, 15)
        score += int(relevance)
        details.append(f"相关度{int(relevance/15*100)}%")

    # 错误模式检测 (0-15, 扣分项)
    error_patterns = ['错误', '无法', '抱歉', '对不起', '出错了', '失败', 'error', 'failed', 'sorry']
    error_count = sum(1 for p in error_patterns if p in text.lower())
    if error_count > 0:
        penalty = min(error_count * 5, 15)
        score -= penalty
        details.append(f"错误模式x{error_count}")
        issues.append("error_pattern")

    # 重复内容检测
    lines = text.split('\n')
    if len(lines) > 3:
        unique_lines = set(l.strip() for l in lines if l.strip())
        if len(unique_lines) < len(lines) * 0.5:
            score -= 10
            issues.append("repetitive")

    return {"score": max(0, min(score, 100)), "details": ', '.join(details), "issues": issues}


_response_quality_log = []  # [{"platform": str, "score": int, "ts": float}]


def _get_active_tools() -> set:
    """根据tool_mode返回当前激活的工具集"""
    mode = _config.get("tool_mode", "full")
    if mode == "full":
        return None  # None表示全部激活
    if mode == "smart":
        # smart模式：返回api-only，浏览器工具由Playwright处理
        return set(TOOL_SETS.get("api-only", []))
    return set(TOOL_SETS.get(mode, []))

def _update_coordination(platform: str, result: str, context: str = "", status: str = "done"):
    """更新协调状态。"""
    _coordination["platform_results"][platform] = {
        "result": result[:500],  # 截断过长结果
        "context": context,
        "status": status,
        "timestamp": time.strftime("%H:%M:%S"),
    }

def _truncate(text: str, max_len: int = 0) -> str:
    """截断过长响应，节省token。"""
    limit = max_len or _config["max_response_length"]
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [截断: {len(text)}字 → {limit}字]"


def _normalize_response(text: str, platform: str = "") -> str:
    """标准化响应格式：去除多余空白、统一换行、过滤系统提示。"""
    if not text:
        return text
    # 去除首尾空白
    text = text.strip()
    # 统一换行：多个空行→两个换行
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 去除行尾空格
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
    # 过滤常见系统提示残留
    noise = ['Ctrl K', '新对话', '历史对话', '下载电脑版', '内容举报']
    for n in noise:
        text = text.replace(n, '')
    return text.strip()


# AI冗余短语模式（中英文）
_AI_FILLER_PATTERNS = [
    r"当然可以[！!。.]?\s*",
    r"好的[！!。.]?\s*",
    r"没问题[！!。.]?\s*",
    r"我来帮你[！!。.]?\s*",
    r"让我来[！!。.]?\s*",
    r"以下是[：:]?\s*",
    r"根据你的要求[，,]?\s*",
    r"基于以上分析[，,]?\s*",
    r"总结一下[：:]?\s*",
    r"综上所述[，,]?\s*",
    r"总的来说[，,]?\s*",
    r"需要注意的是[，,]?\s*",
    r"希望这能帮到你[！!。.]?\s*",
    r"如果还有疑问[，,]?\s*随时[联系问].*\s*",
    r"As an AI[，,].*?\.\s*",
    r"I hope this helps[！!.]?\s*",
    r"Here (?:is|are) the?.*?:\s*",
    r"Sure[！!]? Let me.*?:\s*",
    r"Of course[！!]? .*?:\s*",
]
_AI_FILLER_RE = re.compile("|".join(_AI_FILLER_PATTERNS), re.IGNORECASE)


def _compress_response(text: str) -> str:
    """压缩响应：去除AI冗余短语和重复段落，减少token消耗。"""
    if not text:
        return text
    original_len = len(text)
    # 去除冗余开头短语
    text = _AI_FILLER_RE.sub("", text, count=1)
    # 去除重复段落（连续相似段落只保留第一个）
    lines = text.split("\n")
    compressed = []
    prev = ""
    for line in lines:
        stripped = line.strip()
        if stripped and stripped == prev:
            continue  # 跳过连续重复行
        compressed.append(line)
        prev = stripped
    text = "\n".join(compressed)
    # 去除多余空行（保留最多1个）
    text = re.sub(r"\n{3,}", "\n\n", text)
    saved = original_len - len(text)
    if saved > 20:
        text += f"\n... [压缩: {original_len}字 → {len(text)}字, 节省{saved}字]"
    return text.strip()


def _check_tool_cache(tool_name: str, **kwargs) -> str | None:
    """检查工具调用缓存，命中则返回缓存结果。"""
    args_hash = hashlib.md5(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()
    key = (tool_name, args_hash)
    cached = _tool_call_cache.get(key)
    if cached and (time.time() - cached["ts"]) < _TOOL_CACHE_TTL:
        return f"[缓存命中] {cached['result']}"
    return None


def _save_tool_cache(tool_name: str, result: str, **kwargs):
    """保存工具调用结果到缓存。"""
    args_hash = hashlib.md5(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()
    key = (tool_name, args_hash)
    _tool_call_cache[key] = {"result": result, "ts": time.time()}
    # 清理过期缓存
    now = time.time()
    expired = [k for k, v in _tool_call_cache.items() if (now - v["ts"]) > _TOOL_CACHE_TTL]
    for k in expired:
        del _tool_call_cache[k]


def _record_response_time(platform: str, elapsed: float):
    """记录平台响应时间。"""
    if platform not in _response_times:
        _response_times[platform] = []
    _response_times[platform].append(elapsed)
    if len(_response_times[platform]) > 10:
        _response_times[platform].pop(0)
    # 趋势记录
    if platform not in _response_trend:
        _response_trend[platform] = []
    _response_trend[platform].append((time.time(), elapsed))
    # 保留最近100条
    if len(_response_trend[platform]) > 100:
        _response_trend[platform] = _response_trend[platform][-100:]


def _get_dynamic_timeout(platform: str, base_timeout: int = 120) -> int:
    """根据历史响应时间动态调整超时：P90*1.5+缓冲，保证最小30s，上限base_timeout。"""
    times = _response_times.get(platform, [])
    if len(times) < 3:
        return base_timeout

    sorted_times = sorted(times)
    # P90百分位数
    p90_idx = int(len(sorted_times) * 0.9)
    p90 = sorted_times[min(p90_idx, len(sorted_times) - 1)]

    # 加权：最近3次权重更高
    recent = times[-3:] if len(times) >= 3 else times
    recent_avg = sum(recent) / len(recent)

    # 取P90和近期平均的较大值
    base = max(p90, recent_avg)
    dynamic = int(base * 1.5 + 15)  # 1.5倍+15秒缓冲
    return max(30, min(dynamic, base_timeout))  # 最小30s


def _get_adaptive_rate_limit(platform: str) -> dict:
    """根据平台状态动态调整限流参数。"""
    base_interval = _config["rate_limit_interval"]
    base_max = _config["rate_limit_max"]

    # 错误率高：降低速率
    stats = _error_stats.get(platform, {})
    total_err = sum(stats.values())
    if total_err > 10:
        return {"interval": base_interval * 3, "max": max(2, base_max // 3)}
    elif total_err > 5:
        return {"interval": base_interval * 2, "max": max(3, base_max // 2)}

    # 响应慢：降低速率
    times = _response_times.get(platform, [])
    if times:
        avg_time = sum(times) / len(times)
        if avg_time > 15:
            return {"interval": base_interval * 2, "max": max(3, base_max // 2)}

    # 并发高：降低速率
    req_count = _active_requests.get(platform, {}).get("count", 0)
    if req_count > 3:
        return {"interval": base_interval * 2, "max": max(2, base_max // 2)}

    return {"interval": base_interval, "max": base_max}


def _check_rate_limit(platform: str) -> str | None:
    """检查请求限流（自适应），返回错误信息或None（允许通过）。"""
    now = time.time()
    window = _config["rate_limit_window"]
    limits = _get_adaptive_rate_limit(platform)

    # 清理过期记录
    if platform not in _rate_limiter:
        _rate_limiter[platform] = []
    _rate_limiter[platform] = [t for t in _rate_limiter[platform] if (now - t) < window]

    # 检查间隔
    if _rate_limiter[platform]:
        last = _rate_limiter[platform][-1]
        if (now - last) < limits["interval"]:
            wait = limits["interval"] - (now - last)
            return f"[限流] {platform} 请求过快，请等待{wait:.1f}秒"
    # 检查窗口内数量
    if len(_rate_limiter[platform]) >= limits["max"]:
        return f"[限流] {platform} 窗口内请求数已达上限({limits['max']})"
    _rate_limiter[platform].append(now)
    return None


def _message_similarity(a: str, b: str) -> float:
    """计算两个消息的字符级相似度 (0-1)。"""
    if not a or not b:
        return 0.0
    # 简单Jaccard相似度（字符级）
    set_a = set(a.lower().replace(" ", ""))
    set_b = set(b.lower().replace(" ", ""))
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _check_message_dedup(platform: str, message: str) -> str | None:
    """检查重复消息（精确+近似），返回错误信息或None（允许发送）。"""
    now = time.time()
    _dedup_stats["total_checked"] += 1
    msg_hash = hashlib.md5(message.encode()).hexdigest()
    key = (platform, msg_hash)

    # 精确匹配
    last_time = _message_dedup.get(key)
    if last_time and (now - last_time) < _config["dedup_window"]:
        _dedup_stats["exact_hits"] += 1
        remain = _config["dedup_window"] - (now - last_time)
        return f"[去重] {platform} 相同消息已发送，请等待{remain:.0f}秒后再试"

    # 近似匹配（相似度>0.8）
    for (pk, hash_val), ts in _message_dedup.items():
        if pk != platform or (now - ts) >= _config["dedup_window"]:
            continue
        stored = _message_dedup_content.get((pk, hash_val))
        if stored and _message_similarity(message, stored) > 0.8:
            _dedup_stats["near_hits"] += 1
            remain = _config["dedup_window"] - (now - ts)
            return f"[去重] {platform} 疑似重复消息(相似度>80%)，请等待{remain:.0f}秒后再试"

    _message_dedup[key] = now
    # 同时存储消息内容用于近似匹配
    _message_dedup_content[key] = message

    # 清理过期记录
    expired = [k for k, v in _message_dedup.items() if (now - v) > _config["dedup_window"]]
    for k in expired:
        del _message_dedup[k]
        _message_dedup_content.pop(k, None)
    return None


def _get_context_summary(platform: str) -> str:
    """获取平台执行上下文摘要：当前任务+上次结果+下一步目标。支持上下文缓存。"""
    # 构建上下文键（基于任务和轮次）
    cache_key = f"{_coordination['current_task']}:{_coordination['iteration']}:{platform}"
    cached = _get_cached_context(cache_key)
    if cached:
        return cached

    lines = [f"当前任务: {_coordination['current_task'] or '无'}"]
    lines.append(f"迭代轮次: {_coordination['iteration']}")
    # 其他平台的上次结果
    for p, data in _coordination["platform_results"].items():
        if p != platform and data.get("result"):
            name = PLATFORMS.get(p, {}).get("name", p)
            lines.append(f"[{name}] 上次结果: {data['result'][:100]}")
    # 本平台的上次结果
    if platform in _coordination["platform_results"]:
        prev = _coordination["platform_results"][platform]
        if prev.get("result"):
            lines.append(f"[本平台] 上次结果: {prev['result'][:100]}")
    # 共享上下文
    for k, v in _coordination["shared_context"].items():
        lines.append(f"[共享] {k}: {str(v)[:80]}")

    result = "\n".join(lines)
    _save_context_cache(cache_key, result)
    return result
USER_DATA = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright", "ai-chat-browser")

PLATFORMS = {
    "doubao": {
        "name": "豆包",
        "url": "https://www.doubao.com/chat/",
        "mode": "超能模式",
        "purpose": "中文内容生成",
        "login_keywords": ["sign_in", "login", "passport"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://chat.deepseek.com/",
        "mode": "专家模式+深度思考+智能搜索",
        "purpose": "专业文档",
        "login_keywords": ["sign_in", "login"],
    },
    "volcengine": {
        "name": "火山引擎",
        "url": "https://ai.volcengine.com/experience/ark?mode=chat&modelId=ep-20260512152006-fxsc9",
        "mode": "Doubao-Seed-2.0-pro",
        "purpose": "技术调研分析",
        "login_keywords": ["login", "signin", "passport"],
    },
    "ouyi": {
        "name": "欧亿AI",
        "url": "https://ai.rcouyi.com/home",
        "mode": "高级VIP",
        "purpose": "图像生成",
        "login_keywords": ["login", "signin"],
    },
}

# 平台能力注册：关键词→平台映射
_PLATFORM_CAPABILITIES = {
    "doubao": ["中文", "润色", "改写", "文案", "创意", "翻译", "总结", "简化", "写作"],
    "volcengine": ["代码", "编程", "算法", "技术", "分析", "推理", "调试", "架构", "优化"],
    "ouyi": ["图片", "图像", "画", "思维导图", "流程图", "可视化"],
    "deepseek": ["报告", "文档", "专业", "论文", "实验", "数据", "统计", "研究"],
}


def _assess_complexity(message: str) -> dict:
    """评估任务复杂度，返回等级和推荐平台。基于cost-aware-llm-pipeline逻辑。"""
    char_count = len(message)
    msg_lower = message.lower()

    # L1 简单：<20字符 → 默认平台
    if char_count < 20:
        return {"level": 1, "platform": "doubao", "reason": "短文本", "tree": False}

    # L3 复杂：代码任务 → 火山引擎(技术)
    code_keywords = ["代码", "函数", "class", "function", "bug", "调试", "def ", "import ", "const "]
    has_code = any(k in msg_lower for k in code_keywords) or bool(__import__('re').search(r'[{}\[\]();]', message))
    if has_code:
        return {"level": 3, "platform": "volcengine", "reason": "代码任务", "tree": False}

    # 检测平台能力匹配
    platform_scores = {}
    for pk, caps in _PLATFORM_CAPABILITIES.items():
        score = sum(1 for cap in caps if cap in msg_lower)
        platform_scores[pk] = score

    best_platform = max(platform_scores, key=platform_scores.get) if platform_scores else "doubao"
    best_score = platform_scores.get(best_platform, 0)

    # L2 中等：>20字符的非代码任务 → 树状调用
    if char_count >= 20 and best_score > 0:
        return {
            "level": 2, "platform": best_platform, "reason": "中等任务",
            "tree": True, "tree_config": {
                "layer1": best_platform,
                "layer2": [pk for pk in platform_scores if pk != best_platform and platform_scores[pk] == 0][:2],
            }
        }

    # 默认：按能力匹配
    return {"level": 2, "platform": best_platform, "reason": "能力匹配", "tree": False}


def _route_by_capability(message: str) -> str:
    """根据消息内容智能路由到最佳平台。"""
    assessment = _assess_complexity(message)
    return assessment["platform"]


# ── Error handling ───────────────────────────────────────────────

def _check_retry_budget() -> bool:
    """检查全局重试预算。返回True表示允许重试。"""
    now = time.time()
    window = _config["retry_budget_window"]
    max_retries = _config["retry_budget_max"]
    # 清理过期记录
    _retry_budget[:] = [t for t in _retry_budget if (now - t) < window]
    return len(_retry_budget) < max_retries


def _record_retry():
    """记录一次重试。"""
    _retry_budget.append(time.time())


def retry_on_failure(func):
    """重试装饰器：在异步函数失败时自动重试"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        last_error = None
        max_retries = _config["max_retries"]
        delay = _config["retry_delay"]
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                _err(f"[retry] {func.__name__} attempt {attempt+1}/{max_retries} failed", error=str(e))
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay * (attempt + 1))
        raise last_error
    return wrapper


# ── Circuit Breaker ────────────────────────────────────────────


# ── Memory monitoring ──────────────────────────────────────────
def _check_memory() -> dict:
    """检查浏览器内存使用，返回状态和建议。"""
    import subprocess
    result = {"status": "ok", "memory_mb": 0, "action": "none"}
    try:
        ps = subprocess.run(
            ["powershell", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\").WorkingSetSize | Measure-Object -Sum | Select-Object -ExpandProperty Sum"],
            capture_output=True, text=True, timeout=5
        )
        if ps.stdout.strip():
            result["memory_mb"] = int(int(ps.stdout.strip()) / 1024 / 1024)
            if result["memory_mb"] > _config["memory_critical_mb"]:
                result["status"] = "critical"
                result["action"] = "close_tabs"
                _warn(f"[memory] CRITICAL: {result['memory_mb']}MB > {_config['memory_critical_mb']}MB, 建议关闭标签页")
            elif result["memory_mb"] > _config["memory_warn_mb"]:
                result["status"] = "warn"
                result["action"] = "cleanup"
                _warn(f"[memory] WARN: {result['memory_mb']}MB > {_config['memory_warn_mb']}MB")
    except Exception as e:
        _dbg(f"[memory] check failed: {e}")
    return result


async def _check_connection_health() -> dict:
    """定期检查浏览器连接健康状态，必要时主动重连。"""
    global _browser, _playwright_obj, _reconnect_count

    now = time.time()
    if now - _connection_health["last_check"] < _connection_health["check_interval"]:
        return _connection_health

    _connection_health["last_check"] = now
    ok = False
    pages_count = 0
    mem = _check_memory()

    if _browser:
        try:
            pages_count = len(_browser.pages)
            ok = True
            _connection_health["consecutive_failures"] = 0
        except Exception as e:
            _connection_health["consecutive_failures"] += 1
            _warn(f"[health] 连接检查失败: {str(e)[:50]}")

            # 连续失败3次，主动重连
            if _connection_health["consecutive_failures"] >= 3:
                _warn(f"[health] 连续失败{_connection_health['consecutive_failures']}次，主动重连")
                try:
                    if _playwright_obj:
                        await _playwright_obj.stop()
                except:
                    pass
                _browser = None
                _playwright_obj = None
                _connection_health["consecutive_failures"] = 0
                _connection_health["last_reconnect"] = now
                _reconnect_count += 1

    # 记录历史
    _connection_health["history"].append({
        "ts": now, "ok": ok, "pages": pages_count,
        "memory_mb": mem["memory_mb"]
    })
    if len(_connection_health["history"]) > 30:
        _connection_health["history"] = _connection_health["history"][-30:]

    return _connection_health


# ── Screenshot archiving ──────────────────────────────────────
async def _save_screenshot(page, label: str = "screenshot"):
    """保存页面截图到指定目录。"""
    import os
    ss_dir = _config.get("screenshot_dir", "")
    if not ss_dir or not page:
        return
    try:
        os.makedirs(ss_dir, exist_ok=True)
        ts = time.strftime('%Y%m%d_%H%M%S')
        filename = f"{label}_{ts}.png"
        path = os.path.join(ss_dir, filename)
        await page.screenshot(path=path, full_page=False)
        _info(f"[screenshot] saved: {path}")
    except Exception as e:
        _dbg(f"[screenshot] save failed: {e}")


# ── Platform health probe ─────────────────────────────────────
async def _probe_platform(platform_key: str) -> dict:
    """探测单个平台可达性和延迟。"""
    info = PLATFORMS.get(platform_key)
    if not info:
        return {"ok": False, "latency": 0, "error": "unknown platform"}
    t0 = time.time()
    try:
        page = await ensure_page(platform_key)
        if page is None:
            return {"ok": False, "latency": 0, "error": "browser unavailable"}
        title = await page.title()
        latency = time.time() - t0
        _health_status[platform_key] = {"ok": True, "last_check": time.time(), "latency": round(latency, 2)}
        return _health_status[platform_key]
    except Exception as e:
        latency = time.time() - t0
        _health_status[platform_key] = {"ok": False, "last_check": time.time(), "latency": round(latency, 2), "error": str(e)[:100]}
        return _health_status[platform_key]


async def probe_all_platforms() -> str:
    """探测所有平台健康状态：并行探测，返回详细结果。"""
    # 并行探测所有平台
    tasks = {key: _probe_platform(key) for key in PLATFORMS}
    results = []
    ok_count = 0
    total_latency = 0

    for key, task in tasks.items():
        status = await task
        icon = "✓" if status["ok"] else "✗"
        latency = f"{status['latency']:.1f}s"
        extra = f" ({status.get('error', '')[:30]})" if not status["ok"] else ""
        results.append(f"[{icon}] {PLATFORMS[key]['name']}: {latency}{extra}")
        if status["ok"]:
            ok_count += 1
            total_latency += status["latency"]

    avg_latency = total_latency / ok_count if ok_count > 0 else 0
    summary = f"\n\n可用: {ok_count}/{len(PLATFORMS)} | 平均延迟: {avg_latency:.1f}s"
    return "=== 平台健康探测 ===\n" + "\n".join(results) + summary


# ── Session persistence ────────────────────────────────────────
async def save_session():
    """保存浏览器cookies和会话状态到文件。"""
    path = _config.get("session_save_path", "")
    if not path or not _browser:
        return
    try:
        context = _browser.contexts[0] if _browser.contexts else None
        if not context:
            return
        cookies = await context.cookies()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"cookies": cookies, "ts": time.time()}, f)
        _info(f"[session] saved {len(cookies)} cookies to {path}")
    except Exception as e:
        _warn(f"[session] save failed: {e}")


async def restore_session():
    """从文件恢复浏览器cookies。"""
    path = _config.get("session_save_path", "")
    if not path or not _browser:
        return
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        if cookies:
            context = _browser.contexts[0] if _browser.contexts else None
            if context:
                await context.add_cookies(cookies)
                _info(f"[session] restored {len(cookies)} cookies from {path}")
    except Exception as e:
        _warn(f"[session] restore failed: {e}")


@mcp.tool()
async def save_session_snapshot(path: str = "") -> str:
    """保存完整会话状态快照（cookies+页面+错误+配置），用于调试回放。"""
    save_path = path or _config.get("session_save_path", "").replace(".json", "_snapshot.json")
    if not save_path:
        save_path = os.path.join(os.path.expanduser("~"), ".claude", "session_snapshot.json")

    snapshot = {"ts": time.time(), "version": "1.0"}

    # Cookies
    try:
        if _browser and _browser.contexts:
            cookies = await _browser.contexts[0].cookies()
            snapshot["cookies"] = cookies
    except Exception:
        snapshot["cookies"] = []

    # 页面状态
    snapshot["pages"] = {}
    if _browser:
        for pk, page in _pages.items():
            try:
                snapshot["pages"][pk] = {
                    "url": page.url,
                    "title": await page.title(),
                }
            except Exception:
                snapshot["pages"][pk] = {"url": "unknown", "title": "unknown"}

    # 错误统计
    snapshot["error_stats"] = dict(_error_stats)

    # 响应时间
    snapshot["response_times"] = {k: list(v) for k, v in _response_times.items()}

    # 缓存统计
    snapshot["cache_stats"] = dict(_cache_stats)
    snapshot["context_cache_stats"] = dict(_context_cache_stats)
    snapshot["coalesced_stats"] = dict(_coalesced_stats)

    # 健康状态
    snapshot["health_status"] = dict(_health_status)
    snapshot["connection_health"] = {
        "last_check": _connection_health.get("last_check", 0),
        "consecutive_failures": _connection_health.get("consecutive_failures", 0),
    }

    # 配置
    snapshot["config"] = dict(_config)

    # 协调状态
    snapshot["coordination"] = dict(_coordination)

    # 保存
    try:
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
        size = os.path.getsize(save_path)
        return f"快照已保存: {save_path}\n大小: {size}字节\n页面: {len(snapshot['pages'])}个\nCookies: {len(snapshot['cookies'])}条"
    except Exception as e:
        return f"保存失败: {e}"


@mcp.tool()
async def restore_session_snapshot(path: str = "") -> str:
    """从快照恢复完整会话状态。"""
    load_path = path or _config.get("session_save_path", "").replace(".json", "_snapshot.json")
    if not load_path:
        load_path = os.path.join(os.path.expanduser("~"), ".claude", "session_snapshot.json")

    if not os.path.exists(load_path):
        return f"快照不存在: {load_path}"

    try:
        with open(load_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
    except Exception as e:
        return f"读取失败: {e}"

    # 恢复cookies
    restored = 0
    if snapshot.get("cookies") and _browser and _browser.contexts:
        try:
            await _browser.contexts[0].add_cookies(snapshot["cookies"])
            restored = len(snapshot["cookies"])
        except Exception:
            pass

    # 恢复配置
    if snapshot.get("config"):
        for k, v in snapshot["config"].items():
            if k in _config:
                _config[k] = v

    # 恢复响应时间
    if snapshot.get("response_times"):
        for k, v in snapshot["response_times"].items():
            _response_times[k] = list(v)

    # 恢复统计
    if snapshot.get("cache_stats"):
        _cache_stats.update(snapshot["cache_stats"])
    if snapshot.get("context_cache_stats"):
        _context_cache_stats.update(snapshot["context_cache_stats"])
    if snapshot.get("coalesced_stats"):
        _coalesced_stats.update(snapshot["coalesced_stats"])

    # 恢复错误统计
    if snapshot.get("error_stats"):
        _error_stats.update(snapshot["error_stats"])

    # 恢复协调状态
    if snapshot.get("coordination"):
        _coordination.update(snapshot["coordination"])

    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snapshot.get("ts", 0)))
    pages = len(snapshot.get("pages", {}))
    restored_items = f"Cookies:{restored} 页面:{pages} 配置:✓"
    if snapshot.get("response_times"):
        restored_items += f" 响应时间:{len(snapshot['response_times'])}平台"
    return f"快照已恢复 (保存于{ts})\n{restored_items}"


# ── Browser management ──────────────────────────────────────────

async def get_browser():
    global _browser, _playwright_obj
    if _browser:
        try:
            # 检查浏览器对象是否有效
            pages = _browser.pages
            if pages is not None and hasattr(pages, '__len__'):
                return _browser
            else:
                raise Exception("Browser object invalid: pages attribute missing")
        except Exception as e:
            global _reconnect_count
            _reconnect_count += 1
            _warn(f"[get_browser] Browser connection lost (reconnect#{_reconnect_count}), attempting recovery...", error=str(e))
            _browser = None
            # 重置 browser-use 连接
            reset_browser_agent()
            # 强制清理旧的playwright实例
            if _playwright_obj:
                try:
                    await _playwright_obj.stop()
                except:
                    pass
                _playwright_obj = None
            # 清除CDP端口文件，强制使用新浏览器
            cdp_port_file = os.path.join(os.path.dirname(__file__), ".cdp_port")
            if os.path.exists(cdp_port_file):
                os.remove(cdp_port_file)
    from playwright.async_api import async_playwright
    _playwright_obj = await async_playwright().start()

    # 优先：通过CDP连接到已运行的Chrome（支持用户已有浏览器）
    cdp = _CDP_ENDPOINT
    if not cdp:
        # 检测CDP端口（默认9222），允许用户用--remote-debugging-port启动Chrome
        import urllib.request
        for port in [9222, 9223, 9224, 9225]:
            try:
                req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
                cdp = f"http://127.0.0.1:{port}"
                _info(f"[get_browser] 检测到CDP端口: {cdp}")
                break
            except Exception:
                pass

    # 优先：通过CDP连接到已运行的Chrome（支持browser-harness共享实例）
    if cdp:
        try:
            _info(f"[get_browser] 尝试通过CDP连接: {cdp}")
            _browser = await _playwright_obj.chromium.connect_over_cdp(cdp)
            if _browser:
                # Browser对象有contexts属性，BrowserContext对象有pages属性
                pages_count = 0
                if hasattr(_browser, 'pages'):
                    pages_count = len(_browser.pages)
                elif hasattr(_browser, 'contexts') and _browser.contexts:
                    pages_count = sum(len(ctx.pages) for ctx in _browser.contexts if hasattr(ctx, 'pages'))
                if pages_count > 0:
                    _info(f"[get_browser] CDP连接成功，共享 {pages_count} 个标签页")
                    # 保存CDP端口到文件
                    cdp_port_file = os.path.join(os.path.dirname(__file__), ".cdp_port")
                    with open(cdp_port_file, "w") as f:
                        f.write(cdp)
                    return _browser
                else:
                    _warn("[get_browser] CDP连接成功但无可用页面，回退到本地启动")
                    _browser = None
            else:
                _warn("[get_browser] CDP连接成功但Browser对象无效，回退到本地启动")
                _browser = None
        except Exception as e:
            _warn(f"[get_browser] CDP连接失败: {e}，回退到本地启动")
            _browser = None

    # 尝试通过Playwright的extension模式连接到已打开的Chrome
    _info("[get_browser] 尝试通过Playwright extension连接已打开的Chrome")
    try:
        # 检查是否有Chrome进程在运行
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Select-Object -First 1 -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=5
        )
        if "chrome.exe" in result.stdout:
            _info("[get_browser] 检测到Chrome进程正在运行，尝试通过extension连接")
            # 尝试通过extension连接
            try:
                _browser = await _playwright_obj.chromium.connect_over_cdp("http://127.0.0.1:9222")
                if _browser and _browser.pages is not None:
                    _info(f"[get_browser] Extension连接成功，共享 {len(_browser.pages)} 个标签页")
                    return _browser
            except:
                pass
    except:
        pass

    # 回退：启动本地浏览器并开放CDP端口9223
    _info(f"[get_browser] 启动本地浏览器（端口9223，供browser-harness连接）")

    # 启动本地浏览器（优化内存+指纹随机化）
    _VIEWPORTS = [
        {"width": 1280, "height": 800},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1920, "height": 1080},
    ]
    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    ]
    viewport = random.choice(_VIEWPORTS)
    user_agent = random.choice(_USER_AGENTS)
    _info(f"[get_browser] fingerprint: viewport={viewport['width']}x{viewport['height']}, ua={user_agent[:50]}...")

    # 代理配置
    proxy_config = None
    if _config.get("proxy_enabled") and _config.get("proxy_pool"):
        proxies = _config["proxy_pool"]
        idx = _config.get("proxy_index", 0) % len(proxies)
        proxy_url = proxies[idx]
        proxy_config = {"server": proxy_url}
        _info(f"[get_browser] proxy: {proxy_url}")

    _browser = await _playwright_obj.chromium.launch_persistent_context(
        USER_DATA,
        headless=_config.get("headless", False),
        viewport=viewport,
        user_agent=user_agent,
        proxy=proxy_config,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-translate",
            "--disable-sync",
            "--no-first-run",
            "--disable-component-update",
            "--disable-features=TranslateUI",
            "--js-flags=--max-old-space-size=256",
            f"--window-size={viewport['width']},{viewport['height']}",
            "--remote-debugging-port=9223",
        ],
    )
    _info(f"[get_browser] 启动浏览器，CDP端口: 9223")
    # 保存CDP端口到文件，供browser-harness使用
    cdp_port_file = os.path.join(os.path.dirname(__file__), ".cdp_port")
    with open(cdp_port_file, "w") as f:
        f.write("http://127.0.0.1:9223")
    await restore_session()
    return _browser


_page_activity = {}  # {page_id: last_active_timestamp}

async def cleanup_idle_pages(browser):
    """清理空闲时间过长的页面，保持页面数量在限制内"""
    if not browser:
        return
    now = time.time()
    idle_timeout = _config["page_idle_timeout"]

    # 关闭超过空闲时间的页面（保留至少1个页面）
    if len(browser.pages) > 1:
        for p in browser.pages[:]:
            pid = id(p)
            last_active = _page_activity.get(pid, now)
            if now - last_active > idle_timeout:
                try:
                    _dbg(f"[cleanup] closing idle page (>{idle_timeout}s): {p.url}")
                    await p.close()
                    _page_activity.pop(pid, None)
                except Exception:
                    pass

    # 保持页面数量在限制内
    if len(browser.pages) > _config["max_pages"]:
        pages_to_close = browser.pages[:len(browser.pages) - _config["max_pages"]]
        for p in pages_to_close:
            try:
                _dbg(f"[cleanup] closing excess page: {p.url}")
                await p.close()
                _page_activity.pop(id(p), None)
            except Exception:
                pass

    # 强制垃圾回收释放内存
    gc.collect()


def _touch_page(page):
    """更新页面活跃时间戳。"""
    _page_activity[id(page)] = time.time()


def _evict_page_pool():
    """清理页面池中过期和不可用的条目。"""
    now = time.time()
    expired = [pk for pk, data in _page_pool.items() if (now - data["last_used"]) > _PAGE_POOL_TTL]
    for pk in expired:
        del _page_pool[pk]


def _get_from_pool(platform_key: str):
    """从页面池获取可用页面。返回 (page, True) 或 (None, False)。"""
    if platform_key in _page_pool:
        data = _page_pool[platform_key]
        page = data["page"]
        try:
            if not page.is_closed():
                data["last_used"] = time.time()
                return page, True
        except Exception:
            pass
        del _page_pool[platform_key]
    return None, False


def _return_to_pool(platform_key: str, page):
    """将页面放回池中。"""
    _page_pool[platform_key] = {
        "page": page,
        "last_used": time.time(),
        "ready": True
    }


async def ensure_page(platform_key: str):
    # 0. 清理过期页面池
    _evict_page_pool()

    # 1. 从页面池获取
    pooled_page, found = _get_from_pool(platform_key)
    if found:
        _dbg(f"[ensure_page] 从页面池获取: {platform_key}")
        _touch_page(pooled_page)
        return pooled_page

    browser = await get_browser()
    if browser is None:
        _dbg(f"[ensure_page] 浏览器未启动，返回None")
        return None
    info = PLATFORMS[platform_key]
    target_url = info["url"]
    _dbg(f"[ensure_page] platform={platform_key}, target={target_url}")

    # 内存检查：超阈值时自动清理
    mem = _check_memory()
    if mem["action"] == "close_tabs" and len(browser.pages) > 1:
        _warn(f"[ensure_page] 内存{mem['memory_mb']}MB超限，关闭最旧标签页")
        oldest = min(browser.pages, key=lambda p: _page_activity.get(id(p), 0))
        if oldest.url != target_url:
            await oldest.close()

    # 清理空闲页面
    await cleanup_idle_pages(browser)

    # 先找精确匹配的页面
    for p in browser.pages:
        if target_url.split("?")[0] in p.url:
            _dbg(f"[ensure_page] exact match found: {p.url}")
            _touch_page(p)
            _return_to_pool(platform_key, p)
            return p

    # 再找同域名的页面
    domain = target_url.split("//")[1].split("/")[0]
    for p in browser.pages:
        if domain in p.url:
            _dbg(f"[ensure_page] domain match found: {p.url}, navigating to {target_url}")
            await p.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            await p.wait_for_timeout(3000)
            _dbg(f"[ensure_page] navigated to: {p.url}")
            _touch_page(p)
            _return_to_pool(platform_key, p)
            return p

    # 没找到，检查页面数量限制
    if len(browser.pages) >= _config["max_pages"]:
        _dbg(f"[ensure_page] 页面数量已达上限({_config['max_pages']})，关闭最旧页面")
        try:
            await browser.pages[0].close()
        except Exception:
            pass

    # 新建页面
    _dbg(f"[ensure_page] no match, creating new page")
    page = await browser.new_page()
    await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    _touch_page(page)
    _return_to_pool(platform_key, page)
    return page


def is_login_page(url: str, platform_key: str) -> bool:
    url_lower = url.lower()
    return any(kw in url_lower for kw in PLATFORMS[platform_key]["login_keywords"])


# ── JavaScript snippets ─────────────────────────────────────────
SEND_JS = r"""
(msg) => {
    const sels = ['textarea','textarea[placeholder]','#chat-input','[contenteditable="true"]','[role="textbox"]','.chat-input textarea','div[class*="input"] textarea'];
    let input = null;
    for (const s of sels) { const el = document.querySelector(s); if (el && el.offsetParent !== null) { input = el; break; } }
    if (!input) return {ok:false, error:'input_not_found'};
    if (input.tagName==='TEXTAREA'||input.tagName==='INPUT') {
        const proto = input.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto,'value').set.call(input,msg);
        input.dispatchEvent(new Event('input',{bubbles:true}));
        input.dispatchEvent(new Event('change',{bubbles:true}));
    } else { input.innerText=msg; input.dispatchEvent(new Event('input',{bubbles:true})); }
    // React 18+ nativeInputValueSetter approach (works with most React versions)
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
        || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    if(nativeSetter && (input.tagName==='TEXTAREA'||input.tagName==='INPUT')) {
        nativeSetter.call(input, msg);
        input.dispatchEvent(new Event('input', {bubbles:true}));
    }
    input.focus();
    for(const btn of document.querySelectorAll('button[type="submit"],button[class*="send"],button[class*="submit"],button[aria-label*="发送"],button[aria-label*="send"]')){
        if(btn&&btn.offsetParent!==null&&!btn.disabled){btn.click();return{ok:true,method:'button_click'};}
    }
    let c=input.parentElement,d=0;
    while(c&&d<10){const svgs=c.querySelectorAll('svg');if(svgs.length>0){const t=svgs[svgs.length-1].parentElement;if(t){t.click();return{ok:true,method:'svg_click'};}}c=c.parentElement;d++;}
    const o={key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true};
    input.dispatchEvent(new KeyboardEvent('keydown',o));input.dispatchEvent(new KeyboardEvent('keyup',o));
    return{ok:true,method:'enter_key'};
}
"""

STREAMING_JS = r"""
() => {
    for(const s of ['button[aria-label*="stop"]','[class*="stop-button"]','[class*="stop_btn"]']){
        try{const el=document.querySelector(s);if(el&&el.offsetParent!==null&&!el.disabled)return{streaming:true,indicator:s};}catch(e){}
    }
    const t=document.body.innerText||'';
    if(t.includes('思考中')&&!t.includes('已完成深度思考'))return{streaming:true,indicator:'volcengine-thinking'};
    return{streaming:false};
}
"""

RESPONSE_JS = r"""
() => {
    const EX=['内容由','AI 生成','请仔细甄别','下载电脑版','历史对话','超能模式','帮我写作','PPT 生成','图像生成','更多','新对话','Ctrl K','AI 创作','云盘','专家','Beta','主页','绘画','画廊','思维导图','白板','客户端','画布绘画','内容举报','高级VIP'];
    const ERR_PATTERNS=['重试.*次后仍失败','Cannot read properties','TypeError:','Page.evaluate','接口重试','请求失败','页面执行脚本触发类型异常'];
    function ex(t){if(!t||t.length<1||t.length>5000)return true;if(t.length<20&&EX.some(k=>t===k||t.includes(k)))return true;if(ERR_PATTERNS.some(p=>new RegExp(p).test(t)))return true;return false;}
    for(let i=document.querySelectorAll('div[class*="flow-markdown-body"]').length-1;i>=0;i--){const t=document.querySelectorAll('div[class*="flow-markdown-body"]')[i].innerText?.trim()||'';if(t.length>0&&t.length<15000&&!ex(t))return{text:t,selector:'doubao-markdown'};}
    for(let i=document.querySelectorAll('div[class*="container"][class*="theme-"]').length-1;i>=0;i--){const t=document.querySelectorAll('div[class*="container"][class*="theme-"]')[i].innerText?.trim()||'';if(t.length>1&&t.length<500&&!ex(t))return{text:t,selector:'doubao-theme-container'};}
    for(let i=document.querySelectorAll('.ds-assistant-message-main-content').length-1;i>=0;i--){const t=document.querySelectorAll('.ds-assistant-message-main-content')[i].innerText?.trim()||'';if(t.length>0&&!ex(t))return{text:t,selector:'deepseek-assistant'};}
    for(let i=document.querySelectorAll('[class*="markdown"]').length-1;i>=0;i--){const el=document.querySelectorAll('[class*="markdown"]')[i];if(el.className?.includes('flow-markdown-body'))continue;const t=el.innerText?.trim()||'';if(t.length>5&&t.length<15000&&!ex(t))return{text:t,selector:'deepseek-markdown-fallback'};}
    for(let i=document.querySelectorAll('div[class*="paragraph_48351"]').length-1;i>=0;i--){const t=document.querySelectorAll('div[class*="paragraph_48351"]')[i].innerText?.trim()||'';if(t.length>0&&t.length<15000&&!t.includes('用户现在')&&!t.includes('让我思考')&&!t.includes('首token')&&!t.includes('总耗时')&&!ex(t))return{text:t,selector:'volcengine-paragraph'};}
    for(let i=document.querySelectorAll('p').length-1;i>=0;i--){const t=document.querySelectorAll('p')[i].innerText?.trim()||'';if(t.length>5&&t.length<3000&&!ex(t)&&!/^\d{4}[-/]/.test(t)&&!/^[\d\s+\-=*/.]+$/.test(t)&&!['2','4','6','8','10'].includes(t))return{text:t,selector:'p-tag'};}
    return{text:'',selector:'none'};
}
"""


# ── Chat logic ──────────────────────────────────────────────────
DEBUG_JS = r"""
() => {
    const navKeywords = ['主页', '对话', 'DALL·E', '绘画', '画廊', '思维导图', '白板', '客户端', '画布绘画', '内容举报', '高级VIP',
                         '联网', '思考深度', 'MCP', 'Canvas', '图像答疑', '图像抽取', '图像回答', '图像创作', '视频理解', '检测定位'];

    // 收集所有文本内容
    const results = [];

    // 遍历所有元素
    const allEls = document.querySelectorAll('*');
    for (const el of allEls) {
        if (el.children.length === 0 && el.offsetParent !== null) {
            const t = el.innerText?.trim() || el.textContent?.trim() || '';
            if (t.length > 2 && t.length < 200 && !navKeywords.some(kw => t.includes(kw))) {
                results.push({
                    text: t,
                    tag: el.tagName,
                    class: el.className?.substring(0, 50) || '',
                    parentClass: el.parentElement?.className?.substring(0, 50) || ''
                });
            }
        }
    }

    return results.slice(-20);
}
"""

async def do_chat(platform_key: str, message: str, timeout: int = 120) -> str:
    # 错误统计衰减（让平台有机会恢复）
    _decay_error_stats()

    # 连接健康检查（定期执行，必要时主动重连）
    await _check_connection_health()

    # 跟踪活跃请求
    if platform_key not in _active_requests:
        _active_requests[platform_key] = {"count": 0, "start": time.time(), "total": 0}
    _active_requests[platform_key]["count"] += 1
    _active_requests[platform_key]["total"] += 1

    cache_key = (platform_key, hashlib.md5(message.encode()).hexdigest())

    # 检查缓存
    cached = _response_cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _CACHE_TTL:
        cached["hits"] = cached.get("hits", 0) + 1  # LRU: 增加命中计数
        _cache_stats["hits"] += 1
        _record_perf(f"chat:{platform_key}", 0, True)
        _record_cost(f"chat:{platform_key}", 0, len(cached['result']), cached=True)
        _record_audit(f"chat:{platform_key}", {"message": message}, cached['result'], 0, True)
        return f"[缓存] {cached['result']}"
    _cache_stats["misses"] += 1

    # 请求合并：如果相同请求正在处理，等待其结果
    _coalesced_stats["total"] += 1
    if cache_key in _inflight_requests:
        inflight = _inflight_requests[cache_key]
        inflight["count"] += 1
        _dbg(f"[do_chat] 请求合并: {platform_key} 相同请求已在处理，等待结果")
        try:
            result = await asyncio.wait_for(inflight["future"], timeout=timeout)
            _coalesced_stats["saved"] += 1
            _active_requests[platform_key]["count"] -= 1
            return result
        except asyncio.TimeoutError:
            _active_requests[platform_key]["count"] -= 1
            return f"[超时] {PLATFORMS[platform_key]['name']} 合并请求等待超时"
        except Exception as e:
            _active_requests[platform_key]["count"] -= 1
            return f"[错误] {PLATFORMS[platform_key]['name']} 合并请求失败: {str(e)[:50]}"

    # 创建新的Future用于合并
    future = asyncio.get_event_loop().create_future()
    _inflight_requests[cache_key] = {"future": future, "count": 1}

    if platform_key not in _fetch_stats:
        _fetch_stats[platform_key] = {"success": 0, "fail": 0, "total_time": 0.0}
    # 请求限流检查
    rate_msg = _check_rate_limit(platform_key)
    if rate_msg:
        _record_perf(f"chat:{platform_key}", 0, False)
        return rate_msg
    # 重复消息检查
    dedup_msg = _check_message_dedup(platform_key, message)
    if dedup_msg:
        _record_perf(f"chat:{platform_key}", 0, False)
        return dedup_msg
    last_error = None
    t0 = time.time()
    # 动态超时：根据历史响应时间调整
    effective_timeout = _get_dynamic_timeout(platform_key, timeout)
    for attempt in range(_config["max_retries"]):
        try:
            result = await _do_chat_single(platform_key, message, effective_timeout)
            elapsed = time.time() - t0
            _record_response_time(platform_key, elapsed)
            _fetch_stats[platform_key]["success"] += 1
            _fetch_stats[platform_key]["total_time"] += elapsed
            _record_perf(f"chat:{platform_key}", elapsed, True)
            _record_cost(f"chat:{platform_key}", elapsed, len(result), cached=False)
            # 写入缓存
            result = _normalize_response(result, platform_key)
            result = _compress_response(result)
            _response_cache[cache_key] = {"result": result, "ts": time.time(), "hits": 0}
            _evict_cache()  # 执行LRU淘汰
            _record_audit(f"chat:{platform_key}", {"message": message}, result, elapsed, True)
            # 响应质量评分
            quality = _score_response(result, message)
            _response_quality_log.append({"platform": platform_key, "score": quality["score"], "ts": time.time()})
            if len(_response_quality_log) > 50:
                _response_quality_log.pop(0)
            # 异步保存会话（不阻塞返回）
            asyncio.ensure_future(save_session())
            _active_requests[platform_key]["count"] -= 1
            # 记录使用模式用于智能预热
            _track_usage(platform_key, message)
            # 完成合并请求
            if cache_key in _inflight_requests:
                fut = _inflight_requests[cache_key]["future"]
                if not fut.done():
                    fut.set_result(result)
                del _inflight_requests[cache_key]
            return result
        except Exception as e:
            last_error = e
            _err(f"[do_chat] {platform_key} attempt {attempt+1}/{_config['max_retries']} failed", error=str(e))
            if attempt < _config["max_retries"] - 1:
                # 全局重试预算检查
                if not _check_retry_budget():
                    _warn(f"[do_chat] 全局重试预算已耗尽，停止重试")
                    break
                _record_retry()
                # 指数退避 + 随机抖动
                base_delay = _config["retry_delay"]
                exponential_delay = base_delay * (2 ** attempt)  # 2s, 4s, 8s...
                jitter = random.uniform(0.5, 1.5)  # 50%-150%随机抖动
                delay = exponential_delay * jitter
                _dbg(f"[do_chat] retry delay: {delay:.1f}s (base={base_delay}, attempt={attempt})")
                # 重置浏览器连接
                global _browser
                _browser = None
                await asyncio.sleep(delay)
    _fetch_stats[platform_key]["fail"] += 1
    # 最终失败时截图
    if _config.get("screenshot_on_error") and _browser:
        try:
            pages = _browser.pages
            if pages:
                await _save_screenshot(pages[-1], f"error_{platform_key}")
        except:
            pass
    _active_requests[platform_key]["count"] -= 1
    error_msg = f"[错误] {PLATFORMS[platform_key]['name']} 重试{_config['max_retries']}次后仍失败: {last_error}"
    # 完成合并请求（失败）
    if cache_key in _inflight_requests:
        fut = _inflight_requests[cache_key]["future"]
        if not fut.done():
            fut.set_result(error_msg)
        del _inflight_requests[cache_key]
    return error_msg


async def _do_chat_single(platform_key: str, message: str, timeout: int = 120) -> str:
    page = await ensure_page(platform_key)
    info = PLATFORMS[platform_key]

    if page is None:
        _dbg(f"[{platform_key}] 页面未启动，提示使用Playwright")
        return f"[AI-chat MCP] Playwright浏览器已运行，请使用Playwright MCP的browser_evaluate抓取消息，或使用browser_type+browser_click发送消息"

    _dbg(f"[{platform_key}] start chat, url={page.url}")

    if is_login_page(page.url, platform_key):
        _dbg(f"[{platform_key}] login page detected")
        # 登录失效时清除该平台缓存
        invalidated = _invalidate_platform_cache(platform_key)
        if invalidated:
            _dbg(f"[{platform_key}] 已清除{invalidated}条过期缓存")
        return f"[需要登录] {info['name']} 页面需要登录，请先运行 login_platform 工具"

    # ── browser-use 优先 ──────────────────────────────────────────
    if _BROWSER_USE_AVAILABLE and _config.get("browser_use_enabled", True):
        try:
            agent = get_browser_agent()
            _dbg(f"[{platform_key}] trying browser-use...")

            # 1. 切换模式
            mode_result = await agent.switch_mode(page, platform_key)
            _dbg(f"[{platform_key}] browser-use mode_switch={mode_result}")

            # 2. 检查输入框
            input_check = await agent.check_input_ready(page)
            _dbg(f"[{platform_key}] browser-use input_check={input_check}")
            if not input_check.get("found"):
                _dbg(f"[{platform_key}] browser-use: input not found, falling back to JS")
                raise Exception("input_not_found")

            # 3. 发送消息
            send_result = await agent.send_message(page, message, platform_key)
            _dbg(f"[{platform_key}] browser-use send={send_result}")
            if not send_result.get("ok"):
                _dbg(f"[{platform_key}] browser-use send failed: {send_result.get('error')}, falling back to JS")
                raise Exception("send_failed")

            # 4. 获取响应（优先使用 browser-harness）
            _dbg(f"[{platform_key}] getting response via browser-harness...")
            response = await agent.get_response(page, platform_key, timeout=timeout)
            if response and not response.startswith("[超时]") and not response.startswith("[错误]"):
                _dbg(f"[{platform_key}] browser-harness: response collected")
                return response

            # 如果 browser-harness 失败，使用传统轮询
            _dbg(f"[{platform_key}] browser-harness failed, falling back to JS polling")
            start = time.time()
            prev_text = ""
            stable_count = 0
            streaming_count = 0
            no_response_count = 0

            while time.time() - start < timeout:
                stream = await page.evaluate(STREAMING_JS)
                if stream.get("streaming"):
                    await page.wait_for_timeout(500)
                    streaming_count += 1
                    _dbg(f"[{platform_key}] streaming... count={streaming_count}")
                    resp = await page.evaluate(RESPONSE_JS)
                    text = resp.get("text", "")
                    if text and len(text) > 10 and text == prev_text:
                        stable_count += 1
                        if stable_count >= 2:
                            _dbg(f"[{platform_key}] JS polling: response collected")
                            return text
                    elif text:
                        prev_text = text
                        stable_count = 0
                    if streaming_count > 40:
                        break
                    continue

                streaming_count = 0
                resp = await page.evaluate(RESPONSE_JS)
                text = resp.get("text", "")

                if text and len(text) > 10:
                    no_response_count = 0
                    if text == prev_text:
                        stable_count += 1
                        if stable_count >= 2:
                            _dbg(f"[{platform_key}] browser-use: response collected via JS polling")
                            return text
                    else:
                        stable_count = 0
                        prev_text = text
                    await page.wait_for_timeout(1000)
                else:
                    no_response_count += 1
                    if no_response_count > 7:
                        return f"[快速失败] {info['name']} 发送后未检测到响应"
                    await page.wait_for_timeout(2000)

            # 如果轮询超时，尝试用 browser-use 获取
            _dbg(f"[{platform_key}] JS polling timeout, trying browser-use for response")
            response = await agent.get_response(page, platform_key, timeout=30)
            if response and not response.startswith("[超时]") and not response.startswith("[错误]"):
                return response

        except Exception as e:
            _dbg(f"[{platform_key}] browser-use failed: {e}, falling back to Playwright JS")

    # ── browser-harness fallback ──────────────────────────────────
    _dbg(f"[{platform_key}] using browser-harness fallback")

    # 使用 browser-harness 发送消息
    agent = get_browser_agent()
    send_result = await agent.send_message(page, message, platform_key)
    _dbg(f"[{platform_key}] browser-harness send={send_result}")

    if not send_result.get("ok"):
        return f"[错误] browser-harness 发送失败: {send_result.get('error', 'unknown')}"

    # 使用 browser-harness 获取响应
    _dbg(f"[{platform_key}] getting response via browser-harness...")
    response = await agent.get_response(page, platform_key, timeout=timeout)
    if response and not response.startswith("[超时]") and not response.startswith("[错误]"):
        _dbg(f"[{platform_key}] browser-harness: response collected")
        return response

    # 如果 browser-harness 失败，使用传统 Playwright JS
    _dbg(f"[{platform_key}] browser-harness failed, falling back to Playwright JS")

    input_check = await page.evaluate(r"""
        () => {
            const sels = ['textarea', '[contenteditable="true"]', '[role="textbox"]',
                          'textarea[placeholder]', 'input[type="text"]',
                          '.chat-input textarea', 'div[class*="input"] textarea'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent !== null) return {found: true, tag: el.tagName, class: el.className};
            }
            return {found: false};
        }
    """)
    _dbg(f"[{platform_key}] input_check={input_check}")
    if not input_check.get("found"):
        return f"[错误] {info['name']} 页面未找到输入框"

    result = await page.evaluate(SEND_JS, message)
    _dbg(f"[{platform_key}] send_result={result}")
    if not result.get("ok"):
        return f"[错误] 发送失败: {result.get('error', 'unknown')}"

    start = time.time()
    prev_text = ""
    stable_count = 0
    streaming_count = 0
    no_response_count = 0

    while time.time() - start < timeout:
        stream = await page.evaluate(STREAMING_JS)
        if stream.get("streaming"):
            await page.wait_for_timeout(500)
            streaming_count += 1
            _dbg(f"[{platform_key}] streaming... count={streaming_count}, indicator={stream.get('indicator')}")
            resp = await page.evaluate(RESPONSE_JS)
            text = resp.get("text", "")
            if text and len(text) > 10 and text == prev_text:
                stable_count += 1
                if stable_count >= 2:
                    return text
            elif text:
                prev_text = text
                stable_count = 0
            if streaming_count > 40:
                _dbg(f"[{platform_key}] streaming timeout (20s), forcing response check")
                break
            continue

        streaming_count = 0
        resp = await page.evaluate(RESPONSE_JS)
        text = resp.get("text", "")
        selector = resp.get("selector", "")
        _dbg(f"[{platform_key}] resp selector={selector}, len={len(text)}, preview={text[:80] if text else ''}")

        if text and len(text) > 10:
            no_response_count = 0
            if text == prev_text:
                stable_count += 1
                if stable_count >= 2:
                    return text
            else:
                stable_count = 0
                prev_text = text
            await page.wait_for_timeout(1000)
        else:
            no_response_count += 1
            if no_response_count > 7:
                _dbg(f"[{platform_key}] no response after {no_response_count} checks, failing fast")
                return f"[快速失败] {info['name']} 发送后未检测到响应，请检查页面状态"
            await page.wait_for_timeout(2000)

    resp = await page.evaluate(RESPONSE_JS)
    text = resp.get("text", "")
    return text if text else f"[超时] {timeout}秒内未获取到 {info['name']} 的响应"


# ── Task splitting ──────────────────────────────────────────────
def split_task(task: str) -> dict:
    """智能任务拆分：关键词匹配+权重评分+多平台并行。"""
    task_lower = task.lower()
    scores = {"doubao": 0, "deepseek": 0, "volcengine": 0}
    rules = {
        "doubao": {
            "high": ["润色", "改写", "翻译", "文案", "写作", "文章", "总结", "摘要", "提炼", "续写"],
            "medium": ["修改", "优化", "生成", "创作", "描述", "解释"],
        },
        "deepseek": {
            "high": ["搜索", "调研", "查找", "评测", "对比", "研究", "技术方案", "原理", "教程"],
            "medium": ["分析", "推理", "计算", "编程", "debug", "代码", "算法"],
        },
        "volcengine": {
            "high": ["实验报告", "论文", "技术报告", "方案书", "需求文档", "设计文档"],
            "medium": ["文档", "专业", "报告", "规范", "标准"],
        },
    }
    for platform, kw_map in rules.items():
        for kw in kw_map["high"]:
            if kw in task_lower:
                scores[platform] += 2
        for kw in kw_map["medium"]:
            if kw in task_lower:
                scores[platform] += 1

    assignments = {}
    max_score = max(scores.values()) if scores else 0
    if max_score > 0:
        # 所有达到最高分的平台都参与
        for platform, score in scores.items():
            if score == max_score:
                assignments[platform] = task
    else:
        # 无匹配：默认分配给deepseek
        assignments["deepseek"] = task
    return assignments


# ── Fallback strategy ───────────────────────────────────────────
PLATFORM_FALLBACK = {
    "doubao": ["deepseek", "volcengine"],
    "deepseek": ["doubao", "volcengine"],
    "volcengine": ["doubao", "deepseek"],
}


@mcp.tool()
async def open_all_platforms() -> str:
    """并行打开3个AI平台，返回登录状态。"""
    browser = await get_browser()
    if browser is None:
        return "[AI-chat MCP] Playwright浏览器已运行，请使用Playwright MCP的browser_navigate打开平台，browser_evaluate抓取消息。"

    async def _open_one(key):
        info = PLATFORMS[key]
        try:
            page = await ensure_page(key)
            if page is None:
                return f"[SKIP] {info['name']}: 浏览器由Playwright控制"
            title = await page.title()
            login = is_login_page(page.url, key)
            status = "需要登录" if login else "已登录"
            return f"[OK] {info['name']} ({info['mode']}) — {status}\n    {info['purpose']}"
        except Exception as e:
            return f"[FAIL] {info['name']}: {e}"

    results = await asyncio.gather(*[_open_one(k) for k in ["doubao", "deepseek", "volcengine"]])
    return "=== AI平台状态 ===\n\n" + "\n\n".join(results)


@mcp.tool()
async def ask_doubao(message: str, timeout: int = 120, summarize: bool = False) -> str:
    """豆包超能模式，适合中文润色和内容生成。summarize=true返回摘要。"""
    cached = _check_tool_cache("ask_doubao", message=message, timeout=timeout, summarize=summarize)
    if cached:
        return _truncate(cached)
    result = await do_chat("doubao", message, timeout)
    _save_tool_cache("ask_doubao", result, message=message, timeout=timeout, summarize=summarize)
    if summarize and result and not result.startswith("["):
        result = _summarize_response(result)
    return _truncate(result)


@mcp.tool()
async def smart_ask(message: str, timeout: int = 120) -> str:
    """智能路由：根据消息内容+复杂度自动选择最佳平台。支持树状调用。

    路由逻辑：
    - L1 (<20字符): 直接发送到默认平台
    - L2 (非代码任务): 按平台能力匹配，支持树状调用(主平台→辅助平台→整合)
    - L3 (代码任务): 发送到火山引擎(技术平台)
    """
    assessment = _assess_complexity(message)
    platform = assessment["platform"]
    level = assessment["level"]
    reason = assessment["reason"]

    # L2 树状调用：主平台+辅助平台并行
    if assessment.get("tree") and assessment.get("tree_config"):
        cfg = assessment["tree_config"]
        primary = cfg["layer1"]
        secondary = cfg.get("layer2", [])

        # 先发主平台
        primary_result = await do_chat(primary, message, timeout)
        primary_name = PLATFORMS[primary]["name"]

        if not secondary:
            return f"[L{level}|{reason}] [{primary_name}] {primary_result}"

        # 辅助平台并行
        secondary_results = []
        for pk in secondary:
            try:
                r = await do_chat(pk, message, timeout)
                secondary_results.append(f"[{PLATFORMS[pk]['name']}] {r[:500]}")
            except Exception as e:
                secondary_results.append(f"[{PLATFORMS[pk]['name']}] 错误: {e}")

        # 整合结果
        combined = f"[L{level}|{reason}] 主平台[{primary_name}]:\n{primary_result}"
        if secondary_results:
            combined += "\n\n辅助平台:\n" + "\n".join(secondary_results)
        return combined

    # L1/L3 直接发送
    result = await do_chat(platform, message, timeout)
    return f"[L{level}|{reason}] [{PLATFORMS[platform]['name']}] {result}"


@mcp.tool()
async def ask_deepseek(message: str, timeout: int = 120, summarize: bool = False) -> str:
    """DeepSeek专家模式，适合技术调研和复杂分析。summarize=true返回摘要。"""
    cached = _check_tool_cache("ask_deepseek", message=message, timeout=timeout, summarize=summarize)
    if cached:
        return _truncate(cached)
    result = await do_chat("deepseek", message, timeout)
    _save_tool_cache("ask_deepseek", result, message=message, timeout=timeout, summarize=summarize)
    if summarize and result and not result.startswith("["):
        result = _summarize_response(result)
    return _truncate(result)


@mcp.tool()
async def ask_volcengine(message: str, timeout: int = 120, summarize: bool = False) -> str:
    """火山引擎，适合代码/技术调研和复杂分析。summarize=true返回摘要。"""
    cached = _check_tool_cache("ask_volcengine", message=message, timeout=timeout, summarize=summarize)
    if cached:
        return _truncate(cached)
    result = await do_chat("volcengine", message, timeout)
    _save_tool_cache("ask_volcengine", result, message=message, timeout=timeout, summarize=summarize)
    if summarize and result and not result.startswith("["):
        result = _summarize_response(result)
    return _truncate(result)


@mcp.tool()
async def ask_ouyi(message: str, timeout: int = 120) -> str:
    """欧亿AI，适合图像生成、思维导图、可视化。"""
    cached = _check_tool_cache("ask_ouyi", message=message, timeout=timeout)
    if cached:
        return _truncate(cached)
    result = await do_chat("ouyi", message, timeout)
    _save_tool_cache("ask_ouyi", result, message=message, timeout=timeout)
    return _truncate(result)


@mcp.tool()
async def batch_ask(message: str, platforms: str = "doubao,deepseek", timeout: int = 120) -> str:
    """批量并行发送消息到多个平台，一次性返回所有结果。platforms用逗号分隔。"""
    targets = [p.strip() for p in platforms.split(",") if p.strip()]
    invalid = [p for p in targets if p not in PLATFORMS]
    if invalid:
        return f"未知平台: {invalid}，可选: {list(PLATFORMS.keys())}"

    async def _ask_one(p):
        try:
            r = await do_chat(p, message, timeout)
            name = PLATFORMS[p]["name"]
            return f"[{name}]\n{_truncate(r)}"
        except Exception as e:
            return f"[{PLATFORMS[p]['name']}] 错误: {e}"

    results = await asyncio.gather(*[_ask_one(p) for p in targets], return_exceptions=True)
    parts = []
    for r in results:
        parts.append(f"{r}\n" if not isinstance(r, Exception) else f"[错误] {r}\n")
    return "=== 批量结果 ===\n\n" + "\n".join(parts)


@mcp.tool()
async def login_platform(platform: str) -> str:
    """打开平台登录页面，等待用户手动完成登录。登录状态会持久化保存。"""
    if platform not in PLATFORMS:
        return f"未知平台: {platform}，可选: doubao/deepseek/volcengine"
    info = PLATFORMS[platform]
    page = await ensure_page(platform)
    if not is_login_page(page.url, platform):
        return f"{info['name']} 已登录"
    await page.goto(info["url"], wait_until="domcontentloaded", timeout=30000)
    for _ in range(60):
        await page.wait_for_timeout(2000)
        if not is_login_page(page.url, platform):
            title = await page.title()
            return f"{info['name']} 登录成功: {title}"
    return f"[超时] {info['name']} 登录超时"


@mcp.tool()
async def refresh_sessions(platforms: str = "") -> str:
    """刷新平台会话：重新加载页面防止登录过期。platforms为空则刷新所有。"""
    browser = await get_browser()
    if browser is None:
        return "浏览器未运行"
    targets = [p.strip() for p in platforms.split(",") if p.strip()] if platforms else list(PLATFORMS.keys())
    results = []
    for pk in targets:
        info = PLATFORMS.get(pk)
        if not info:
            results.append(f"{pk}: 未知平台")
            continue
        for page in browser.pages:
            if info["url"].split("?")[0] in page.url:
                try:
                    await page.reload(timeout=15000)
                    results.append(f"{info['name']}: 已刷新")
                except Exception as e:
                    results.append(f"{info['name']}: 刷新失败({str(e)[:50]})")
                break
        else:
            results.append(f"{info['name']}: 未打开")
    return "\n".join(results)


@mcp.tool()
async def check_login() -> str:
    """检查各平台登录状态。"""
    browser = await get_browser()
    if browser is None:
        return "[AI-chat MCP] Playwright浏览器已运行，无法直接检查。请使用Playwright MCP查看页面状态。"
    results = []
    for key, info in PLATFORMS.items():
        found = False
        for p in browser.pages:
            if info["url"].split("?")[0] in p.url:
                login = is_login_page(p.url, key)
                status = "需要登录" if login else "已登录"
                results.append(f"{info['name']}: {status}")
                found = True
                break
        if not found:
            results.append(f"{info['name']}: 未打开")
    return "\n".join(results)


@mcp.tool()
async def list_tabs() -> str:
    """列出当前浏览器中打开的所有标签页。"""
    browser = await get_browser()
    if browser is None:
        return "[AI-chat MCP] Playwright浏览器已运行，无法直接列出。请使用Playwright MCP的browser_tabs工具。"
    tabs = []
    for i, p in enumerate(browser.pages):
        title = await p.title()
        tabs.append(f"{i}: {p.url}\n   {title}")
    return "\n".join(tabs) or "无打开的标签页"


@mcp.tool()
def split_task_tool(task: str) -> str:
    """分析任务并分配给合适的AI平台。"""
    if not task:
        return "任务不能为空"
    assignments = split_task(task)
    lines = [f"任务: {task}\n", "分配方案:"]
    for platform, subtask in assignments.items():
        info = PLATFORMS[platform]
        lines.append(f"  → {info['name']} ({info['mode']}): {subtask}")
    lines.append("\nClaude: 核心代码工作")
    return "\n".join(lines)


@mcp.tool()
def set_task(task: str) -> str:
    """设置当前协调任务，初始化共享状态。"""
    _coordination["current_task"] = task
    _coordination["iteration"] += 1
    _coordination["platform_results"] = {}
    return f"任务已设置: {task}\n迭代: {_coordination['iteration']}"


@mcp.tool()
def get_context(platform: str) -> str:
    """获取平台上下文摘要，包含任务和历史结果。"""
    return _get_context_summary(platform)


@mcp.tool()
def report_result(platform: str, result: str, context: str = "") -> str:
    """平台报告执行结果，更新协调状态。"""
    _update_coordination(platform, result, context)
    return f"[{platform}] 结果已记录 ({len(result)}字)"


@mcp.tool()
def get_coordination_status() -> str:
    """获取双引擎协调状态全景。"""
    lines = [f"任务: {_coordination['current_task'] or '无'}"]
    lines.append(f"迭代: {_coordination['iteration']}")
    lines.append("平台状态:")
    for p, data in _coordination["platform_results"].items():
        name = PLATFORMS.get(p, {}).get("name", p)
        lines.append(f"  [{name}] {data['status']} @ {data.get('timestamp','?')} | {data.get('result','')[:80]}")
    if _coordination["shared_context"]:
        lines.append("共享上下文:")
        for k, v in _coordination["shared_context"].items():
            lines.append(f"  {k}: {str(v)[:80]}")
    return "\n".join(lines)


@mcp.tool()
async def execute_split(task: str, timeout: int = 180) -> str:
    """任务拆分并行执行，汇总各平台结果。"""
    if not task:
        return "任务不能为空"

    # 1. 设置协调状态
    _coordination["current_task"] = task
    _coordination["iteration"] += 1
    _coordination["platform_results"] = {}

    # 2. 任务拆分
    assignments = split_task(task)
    recommended = _recommend_platform(task)
    results = [f"任务: {task}\n迭代: {_coordination['iteration']}\n"]
    if recommended:
        results.append(f"推荐平台: {PLATFORMS[recommended]['name']}\n")
    results.append("=== 双引擎并行执行 ===\n")

    # 3. 为每个平台构建带上下文的消息
    async def run_one(platform_key, subtask):
        info = PLATFORMS[platform_key]
        # 构建上下文：当前任务+其他平台状态+共享数据
        context_parts = [f"当前任务: {task}"]
        for p, data in _coordination["platform_results"].items():
            if data.get("result"):
                name = PLATFORMS.get(p, {}).get("name", p)
                context_parts.append(f"[{name}] 已完成: {data['result'][:80]}")
        for k, v in _coordination["shared_context"].items():
            context_parts.append(f"[共享] {k}: {str(v)[:60]}")
        context = "\n".join(context_parts)

        # 带上下文的消息
        context_msg = f"[协调任务# {_coordination['iteration']}] {context}\n\n{subtask}"

        try:
            response = await do_chat(platform_key, context_msg, timeout)
            _update_coordination(platform_key, response, context)
            return f"[{info['name']}]\n{_truncate(response)}"
        except Exception as e:
            _update_coordination(platform_key, f"错误: {e}", context, status="error")
            return f"[{info['name']}] 错误: {e}"

    # 4. 并行执行
    tasks_list = [run_one(k, v) for k, v in assignments.items()]
    task_results = await asyncio.gather(*tasks_list, return_exceptions=True)

    for r in task_results:
        results.append(f"{r}\n" if not isinstance(r, Exception) else f"[错误] {r}\n")

    results.append("=== 协调状态 ===")
    results.append(get_coordination_status())
    results.append("\n=== Claude负责: 核心代码工作 ===")
    return "\n".join(results)


@mcp.tool()
def get_fetch_stats() -> str:
    """获取各平台抓取成功率统计。"""
    if not _fetch_stats:
        return "暂无统计数据"
    lines = ["平台 | 成功 | 失败 | 成功率 | 平均耗时"]
    lines.append("--- | --- | --- | --- | ---")
    for platform, stats in _fetch_stats.items():
        total = stats["success"] + stats["fail"]
        rate = f"{stats['success']/total*100:.1f}%" if total > 0 else "N/A"
        avg = f"{stats['total_time']/stats['success']:.1f}s" if stats["success"] > 0 else "N/A"
        name = PLATFORMS.get(platform, {}).get("name", platform)
        lines.append(f"{name} | {stats['success']} | {stats['fail']} | {rate} | {avg}")
    return "\n".join(lines)


@mcp.tool()
def get_browser_use_stats() -> str:
    """获取 browser-use 集成统计信息。"""
    if not _BROWSER_USE_AVAILABLE:
        return "browser-use 未启用或未安装"

    stats = get_browser_use_stats()
    if "error" in stats:
        return f"browser-use 错误: {stats['error']}"

    lines = ["=== browser-use 统计 ==="]
    lines.append(f"总调用次数: {stats.get('browser_use_calls', 0)}")
    lines.append(f"成功次数: {stats.get('browser_use_success', 0)}")
    lines.append(f"降级次数: {stats.get('browser_use_fallback', 0)}")
    lines.append(f"平均响应时间: {stats.get('avg_response_time', 0):.1f}s")
    lines.append(f"最近错误: {stats.get('last_error', '无')}")

    success_rate = 0
    if stats.get('browser_use_calls', 0) > 0:
        success_rate = stats.get('browser_use_success', 0) / stats.get('browser_use_calls', 0) * 100
    lines.append(f"成功率: {success_rate:.1f}%")

    lines.append(f"\n配置状态: {'启用' if _config.get('browser_use_enabled', True) else '禁用'}")
    lines.append("使用 set_config('browser_use_enabled', false) 可禁用 browser-use")

    return "\n".join(lines)


@mcp.tool()
def reset_browser_use() -> str:
    """重置 browser-use 连接（浏览器断开时使用）。"""
    if not _BROWSER_USE_AVAILABLE:
        return "browser-use 未启用"
    reset_browser_agent()
    return "browser-use 连接已重置"


@mcp.tool()
def get_error_stats() -> str:
    """获取各平台错误分类统计。"""
    if not _error_stats:
        return "暂无错误统计"
    lines = ["平台 | 登录 | 超时 | 错误 | 未知 | 总计"]
    lines.append("--- | --- | --- | --- | --- | ---")
    for platform, stats in _error_stats.items():
        total = sum(stats.values())
        name = PLATFORMS.get(platform, {}).get("name", platform)
        lines.append(f"{name} | {stats['login']} | {stats['timeout']} | {stats['error']} | {stats['unknown']} | {total}")
    return "\n".join(lines)


@mcp.tool()
def analyze_error_patterns() -> str:
    """错误模式分析：自动识别常见错误并推荐修复方案。"""
    if not _error_stats and not _error_log:
        return "暂无错误数据"

    lines = ["=== 错误模式分析 ===\n"]

    # 平台错误分布
    lines.append("## 平台错误分布")
    for platform, stats in _error_stats.items():
        total = sum(stats.values())
        if total == 0:
            continue
        name = PLATFORMS.get(platform, {}).get("name", platform)
        dominant = max(stats, key=stats.get)
        dominant_count = stats[dominant]
        dominant_pct = dominant_count / total * 100

        lines.append(f"\n**{name}** ({total}次错误)")
        lines.append(f"  主要错误: {dominant} ({dominant_count}次, {dominant_pct:.0f}%)")

        # 推荐修复
        if dominant == "login":
            lines.append(f"  推荐: 检查登录状态, 执行 login_platform('{platform}') 重新登录")
        elif dominant == "timeout":
            avg_timeout = _get_dynamic_timeout(platform)
            lines.append(f"  推荐: 当前动态超时{avg_timeout:.0f}s, 检查网络或增加 timeout 参数")
        elif dominant == "error":
            recent_errors = [e for e in _error_log if e["platform"] == platform and e["type"] == "error"]
            if recent_errors:
                last_msg = recent_errors[-1]["msg"][:100]
                if "selector" in last_msg.lower() or "选择器" in last_msg:
                    lines.append("  推荐: 选择器失效, 检查平台DOM结构变化")
                elif "click" in last_msg.lower() or "点击" in last_msg:
                    lines.append("  推荐: 点击失败, 可能是元素被遮挡或页面未加载完成")
                elif "fill" in last_msg.lower() or "输入" in last_msg:
                    lines.append("  推荐: 输入失败, 尝试 browser_click 先聚焦输入框")
                else:
                    lines.append(f"  推荐: 检查最近错误 — {last_msg[:60]}...")

    # 错误趋势
    if _error_log:
        lines.append("\n## 最近错误 (最新5条)")
        for e in _error_log[-5:]:
            ts_str = time.strftime("%H:%M:%S", time.localtime(e["ts"]))
            name = PLATFORMS.get(e["platform"], {}).get("name", e["platform"])
            lines.append(f"  [{ts_str}] {name} | {e['type']} | {e['msg'][:60]}")

    # 全局建议
    total_errors = sum(sum(v.values()) for v in _error_stats.values())
    if total_errors > 20:
        lines.append(f"\n## 全局建议")
        lines.append(f"  总错误数: {total_errors}")
        if any(s.get("login", 0) > 5 for s in _error_stats.values()):
            lines.append("  - 多个平台登录过期, 建议执行 open_all_platforms 刷新会话")
        if any(s.get("timeout", 0) > 10 for s in _error_stats.values()):
            lines.append("  - 超时频繁, 建议检查网络稳定性或增加全局timeout配置")

    return "\n".join(lines)


@mcp.tool()
def suggest_platform_switch(current_platform: str = "") -> str:
    """平台切换建议：综合负载/健康/质量推荐最优平台。"""
    lines = ["=== 平台切换建议 ===\n"]

    # 收集各平台评分
    platform_scores = {}
    for pk, info in PLATFORMS.items():
        score = 100
        reasons = []

        # 错误扣分
        stats = _error_stats.get(pk, {})
        total_err = sum(stats.values())
        if total_err > 10:
            score -= total_err * 2
            reasons.append(f"错误多({total_err}次)")
        if stats.get("login", 0) > 3:
            score -= 20
            reasons.append("登录过期")
        if stats.get("timeout", 0) > 5:
            score -= 15
            reasons.append("超时频繁")

        # 响应时间评分
        times = _response_times.get(pk, [])
        if times:
            avg = sum(times) / len(times)
            if avg > 15:
                score -= 15
                reasons.append(f"响应慢({avg:.0f}s)")
            elif avg < 5:
                score += 10
                reasons.append(f"响应快({avg:.0f}s)")

        # 抓取成功率
        fs = _fetch_stats.get(pk, {})
        total_fetch = fs.get("success", 0) + fs.get("fail", 0)
        if total_fetch > 0:
            rate = fs["success"] / total_fetch * 100
            if rate < 80:
                score -= 20
                reasons.append(f"成功率低({rate:.0f}%)")
            elif rate > 95:
                score += 5

        # 响应质量加分
        quality_list = [q["score"] for q in _response_quality_log if q["platform"] == pk]
        if quality_list:
            avg_quality = sum(quality_list[-5:]) / min(len(quality_list), 5)
            if avg_quality > 70:
                score += 10
                reasons.append(f"质量高({avg_quality:.0f}分)")
            elif avg_quality < 40:
                score -= 15
                reasons.append(f"质量低({avg_quality:.0f}分)")

        # 并发负载惩罚
        req_count = _active_requests.get(pk, {}).get("count", 0)
        if req_count > 2:
            score -= req_count * 10
            reasons.append(f"负载高({req_count}并发)")

        platform_scores[pk] = {"score": max(score, 0), "reasons": reasons}

    # 排序输出
    ranked = sorted(platform_scores.items(), key=lambda x: x[1]["score"], reverse=True)
    for pk, data in ranked:
        info = PLATFORMS[pk]
        marker = " ← 推荐" if pk == ranked[0][0] else ""
        marker += " (当前)" if pk == current_platform else ""
        status = "✓" if not data["reasons"] else "⚠"
        lines.append(f"{status} {info['name']}: {data['score']}分{marker}")
        if data["reasons"]:
            lines.append(f"  问题: {', '.join(data['reasons'])}")

    # 建议
    best = ranked[0][0]
    if current_platform and best != current_platform:
        best_name = PLATFORMS[best]["name"]
        curr_name = PLATFORMS.get(current_platform, {}).get("name", current_platform)
        lines.append(f"\n建议: 从 {curr_name} 切换到 {best_name}")
        lines.append(f"操作: ask_{best}('你的问题')")
    elif current_platform:
        lines.append(f"\n{PLATFORMS[current_platform]['name']} 已是最优选择")

    return "\n".join(lines)


@mcp.tool()
def get_response_quality(platform: str = "") -> str:
    """响应质量评分：根据完整度和相关性打分，优选平台。"""
    if not _response_quality_log:
        return "暂无质量评分数据"

    # 按平台聚合
    by_platform = {}
    for entry in _response_quality_log:
        pk = entry["platform"]
        if platform and pk != platform:
            continue
        if pk not in by_platform:
            by_platform[pk] = {"scores": [], "count": 0}
        by_platform[pk]["scores"].append(entry["score"])
        by_platform[pk]["count"] += 1

    if not by_platform:
        return f"平台 {platform} 无评分数据"

    lines = ["=== 响应质量评分 ===\n"]
    lines.append("平台 | 评分 | 次数 | 平均 | 最高 | 最低")
    lines.append("--- | --- | --- | --- | --- | ---")

    ranked = []
    for pk, data in by_platform.items():
        scores = data["scores"]
        avg = sum(scores) / len(scores)
        name = PLATFORMS.get(pk, {}).get("name", pk)
        lines.append(f"{name} | {scores[-1]} | {data['count']} | {avg:.0f} | {max(scores)} | {min(scores)}")
        ranked.append((pk, avg))

    # 推荐
    if ranked:
        best_pk = max(ranked, key=lambda x: x[1])[0]
        lines.append(f"\n质量最优: {PLATFORMS[best_pk]['name']} (平均{max(ranked, key=lambda x: x[1])[1]:.0f}分)")

    return "\n".join(lines)


@mcp.tool()
def get_perf_dashboard() -> str:
    """性能仪表板：各工具调用统计+响应时间+成功率。"""
    if not _perf_log:
        return "暂无性能数据"

    # 按工具聚合
    by_tool = {}
    for entry in _perf_log:
        t = entry["tool"]
        if t not in by_tool:
            by_tool[t] = {"count": 0, "ok": 0, "total_time": 0.0, "min": 999, "max": 0}
        by_tool[t]["count"] += 1
        if entry["ok"]:
            by_tool[t]["ok"] += 1
        by_tool[t]["total_time"] += entry["time"]
        by_tool[t]["min"] = min(by_tool[t]["min"], entry["time"])
        by_tool[t]["max"] = max(by_tool[t]["max"], entry["time"])

    lines = ["性能仪表板 (最近100次调用)", ""]
    lines.append("工具 | 次数 | 成功率 | 平均耗时 | 最小 | 最大")
    lines.append("--- | --- | --- | --- | --- | ---")
    for tool, s in sorted(by_tool.items(), key=lambda x: -x[1]["count"]):
        avg = f"{s['total_time']/s['count']:.1f}s"
        rate = f"{s['ok']/s['count']*100:.0f}%" if s['count'] > 0 else "N/A"
        lines.append(f"{tool} | {s['count']} | {rate} | {avg} | {s['min']:.1f}s | {s['max']:.1f}s")

    # 最近5条
    lines.append("")
    lines.append("最近调用:")
    for e in _perf_log[-5:]:
        status = "✓" if e["ok"] else "✗"
        lines.append(f"  [{e['ts']}] {e['tool']} {e['time']}s {status}")

    return "\n".join(lines)


@mcp.tool()
def get_cost_stats() -> str:
    """工具调用成本统计：耗时+token+缓存命中率。"""
    if not _cost_log:
        return "暂无成本数据"

    total_time = sum(e["time"] for e in _cost_log)
    total_tokens = sum(e["tokens"] for e in _cost_log)
    cached_count = sum(1 for e in _cost_log if e["cached"])
    total_calls = len(_cost_log)
    cache_rate = cached_count / total_calls * 100 if total_calls > 0 else 0

    lines = [f"成本统计 (最近{_COST_MAX}次调用)", ""]
    lines.append(f"总调用: {total_calls}")
    lines.append(f"总耗时: {total_time:.1f}s")
    lines.append(f"总字符: {total_tokens}")
    lines.append(f"缓存命中: {cached_count}/{total_calls} ({cache_rate:.0f}%)")
    lines.append(f"平均耗时: {total_time/total_calls:.1f}s" if total_calls > 0 else "")

    # 按工具聚合
    by_tool = {}
    for e in _cost_log:
        t = e["tool"]
        if t not in by_tool:
            by_tool[t] = {"count": 0, "time": 0.0, "tokens": 0, "cached": 0}
        by_tool[t]["count"] += 1
        by_tool[t]["time"] += e["time"]
        by_tool[t]["tokens"] += e["tokens"]
        if e["cached"]:
            by_tool[t]["cached"] += 1

    lines.append("")
    lines.append("工具 | 调用 | 耗时 | 字符 | 缓存率")
    lines.append("--- | --- | --- | --- | ---")
    for tool, s in sorted(by_tool.items(), key=lambda x: -x[1]["count"]):
        avg_t = f"{s['time']/s['count']:.1f}s"
        rate = f"{s['cached']/s['count']*100:.0f}%"
        lines.append(f"{tool} | {s['count']} | {avg_t} | {s['tokens']} | {rate}")

    return "\n".join(lines)


@mcp.tool()
def get_token_savings_report() -> str:
    """Token节省量化报告：统计各项优化带来的Token节省效果。"""
    lines = ["=== Token节省量化报告 ===\n"]

    # 1. 缓存节省
    cache_hits = _cache_stats["hits"]
    cache_misses = _cache_stats["misses"]
    total_cache = cache_hits + cache_misses
    # 平均每次缓存命中节省约200 token（避免重新查询+解析响应）
    cache_saved_tokens = cache_hits * 200
    cache_saved_time = cache_hits * 3.0  # 平均每次缓存命中节省3秒

    lines.append("### 1. 缓存节省")
    lines.append(f"  命中: {cache_hits}次, 未命中: {cache_misses}次")
    lines.append(f"  命中率: {cache_hits/total_cache*100:.1f}%" if total_cache > 0 else "  命中率: 0%")
    lines.append(f"  节省Token: ~{cache_saved_tokens}")
    lines.append(f"  节省时间: ~{cache_saved_time:.0f}s")

    # 2. 响应截断节省
    truncation_stats = _config.get("truncation_stats", {"enabled": True, "total_chars": 0, "saved_chars": 0})
    trunc_saved_tokens = truncation_stats.get("saved_chars", 0) // 4  # 约4字符=1token

    lines.append("\n### 2. 响应截断节省")
    lines.append(f"  状态: {'启用' if truncation_stats.get('enabled') else '禁用'}")
    lines.append(f"  节省字符: {truncation_stats.get('saved_chars', 0)}")
    lines.append(f"  节省Token: ~{trunc_saved_tokens}")

    # 3. 工具调用缓存节省
    tool_cache_hits = len([e for e in _cost_log if e.get("cached")])
    tool_saved_tokens = tool_cache_hits * 50  # 工具调用缓存每次节省约50 token

    lines.append("\n### 3. 工具调用缓存节省")
    lines.append(f"  缓存命中: {tool_cache_hits}次")
    lines.append(f"  节省Token: ~{tool_saved_tokens}")

    # 4. 批量操作节省（每次批量比单独调用节省约30% token）
    batch_calls = len([e for e in _cost_log if "batch" in e.get("tool", "")])
    batch_saved_tokens = batch_calls * 100  # 每次批量节省约100 token

    lines.append("\n### 4. 批量操作节省")
    lines.append(f"  批量调用: {batch_calls}次")
    lines.append(f"  节省Token: ~{batch_saved_tokens}")

    # 5. 页面池节省（避免重复创建页面）
    pool_hits = sum(1 for pk in _page_pool if _page_pool[pk].get("ready"))
    pool_saved_tokens = pool_hits * 150  # 每次页面复用节省约150 token

    lines.append("\n### 5. 页面池节省")
    lines.append(f"  池中页面: {pool_hits}个")
    lines.append(f"  节省Token: ~{pool_saved_tokens}")

    # 汇总
    total_saved = cache_saved_tokens + trunc_saved_tokens + tool_saved_tokens + batch_saved_tokens + pool_saved_tokens
    total_saved_time = cache_saved_time + tool_cache_hits * 0.5  # 工具缓存每次节省0.5秒

    lines.append("\n### 汇总")
    lines.append(f"  总节省Token: ~{total_saved}")
    lines.append(f"  总节省时间: ~{total_saved_time:.0f}s")
    lines.append(f"  优化项目: 5项")

    # 估算原始开销（无优化时）
    # 假设每次查询平均200 token，每次工具调用50 token
    raw_tokens = total_cache * 200 + len(_cost_log) * 50
    lines.append(f"\n### 对比")
    lines.append(f"  原始开销(估算): ~{raw_tokens} token")
    lines.append(f"  节省比例: ~{total_saved/raw_tokens*100:.1f}%" if raw_tokens > 0 else "  节省比例: 0%")

    return "\n".join(lines)


@mcp.tool()
def get_audit_log(count: int = 10) -> str:
    """工具调用审计日志：最近N次调用的完整链路。"""
    if not _audit_log:
        return "暂无审计日志"
    entries = _audit_log[-count:]
    lines = [f"审计日志 (最近{len(entries)}/{len(_audit_log)}条)", ""]
    for e in entries:
        status = "✓" if e["ok"] else "✗"
        lines.append(f"[{e['ts']}] {e['tool']} {e['time']}s {status}")
        lines.append(f"  参数: {e['args']}")
        preview = e['result_preview'][:120] + "..." if len(e['result_preview']) > 120 else e['result_preview']
        lines.append(f"  结果: {preview}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
async def replay_tool_calls(count: int = 5, dry_run: bool = True) -> str:
    """工具调用重放：记录并重放历史调用序列，用于调试。"""
    if not _audit_log:
        return "暂无可重放的调用记录"

    entries = _audit_log[-count:]
    lines = [f"=== 工具调用重放 (最近{len(entries)}条) ===\n"]

    replayed = 0
    failed = 0
    for i, entry in enumerate(entries):
        tool = entry["tool"]
        args = entry["args"]
        lines.append(f"[{i+1}] {tool}")

        if dry_run:
            lines.append(f"  参数: {args}")
            lines.append(f"  原始结果: {entry['result_preview'][:80]}...")
            lines.append(f"  状态: DRY_RUN（未执行）")
        else:
            # 实际重放
            try:
                # 构造函数调用
                if tool == "ask_doubao":
                    result = await do_chat("doubao", args.get("message", "重放测试"), args.get("timeout", 60))
                elif tool == "ask_deepseek":
                    result = await do_chat("deepseek", args.get("message", "重放测试"), args.get("timeout", 60))
                elif tool == "ask_volcengine":
                    result = await do_chat("volcengine", args.get("message", "重放测试"), args.get("timeout", 60))
                else:
                    lines.append(f"  跳过: {tool} 不支持重放")
                    continue

                preview = result[:80] + "..." if len(result) > 80 else result
                lines.append(f"  新结果: {preview}")
                replayed += 1
            except Exception as e:
                lines.append(f"  重放失败: {str(e)[:80]}")
                failed += 1

        lines.append("")

    mode = "DRY_RUN" if dry_run else f"执行{replayed}条, 失败{failed}条"
    lines.append(f"状态: {mode}")
    return "\n".join(lines)


@mcp.tool()
def get_response_trend(platform: str = "") -> str:
    """平台响应时间趋势：按小时统计平均响应时间+ASCII图表。"""
    platforms = [platform] if platform and platform in _response_trend else list(_response_trend.keys())
    if not platforms:
        return "暂无趋势数据"
    lines = ["=== 响应时间趋势 ===", ""]
    for p in platforms:
        data = _response_trend.get(p, [])
        if not data:
            continue
        name = PLATFORMS.get(p, {}).get("name", p)
        # 按小时聚合
        hourly = {}
        for ts, lat in data:
            hour = time.strftime('%H:00', time.localtime(ts))
            if hour not in hourly:
                hourly[hour] = []
            hourly[hour].append(lat)
        lines.append(f"[{name}] 最近{len(data)}次:")
        avg_all = sum(lat for _, lat in data) / len(data)
        for hour, lats in sorted(hourly.items()):
            avg = sum(lats) / len(lats)
            bar_len = int(avg / 2)
            bar = "█" * bar_len
            lines.append(f"  {hour}: {avg:.1f}s ({len(lats)}次) {bar}")
        lines.append(f"  总平均: {avg_all:.1f}s")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
async def probe_all_platforms_tool() -> str:
    """探测所有AI平台可达性和延迟。"""
    return await probe_all_platforms()


@mcp.tool()
def check_performance_baseline() -> str:
    """性能基线告警：检测各平台性能是否偏离基线，提供预警。"""
    lines = ["=== 性能基线检测 ===\n"]
    alerts = []

    for pk, info in PLATFORMS.items():
        # 获取历史数据
        times = _response_times.get(pk, [])
        stats = _fetch_stats.get(pk, {})
        errors = _error_stats.get(pk, {})

        if not times:
            lines.append(f"[{info['name']}] 无历史数据")
            continue

        # 计算基线指标
        avg_time = sum(times) / len(times)
        max_time = max(times)
        min_time = min(times)
        total_fetch = stats.get("success", 0) + stats.get("fail", 0)
        success_rate = stats.get("success", 0) / total_fetch * 100 if total_fetch > 0 else 0
        total_errors = sum(errors.values())

        # 告警条件
        platform_alerts = []
        if avg_time > 15:
            platform_alerts.append(f"响应慢({avg_time:.1f}s > 15s)")
        if success_rate < 80 and total_fetch > 5:
            platform_alerts.append(f"成功率低({success_rate:.0f}% < 80%)")
        if total_errors > 10:
            platform_alerts.append(f"错误多({total_errors}次)")
        if max_time > avg_time * 3 and len(times) > 3:
            platform_alerts.append(f"性能波动大(最大{max_time:.1f}s vs 平均{avg_time:.1f}s)")

        # 状态标记
        if platform_alerts:
            icon = "⚠"
            alerts.extend(platform_alerts)
        else:
            icon = "✓"

        lines.append(f"[{icon}] {info['name']}")
        lines.append(f"  平均: {avg_time:.1f}s | 最大: {max_time:.1f}s | 最小: {min_time:.1f}s")
        lines.append(f"  成功率: {success_rate:.0f}% | 错误: {total_errors}次")
        if platform_alerts:
            lines.append(f"  告警: {', '.join(platform_alerts)}")
        lines.append("")

    # 总结
    if alerts:
        lines.append(f"⚠ 发现 {len(alerts)} 个性能问题")
    else:
        lines.append("✓ 所有平台性能正常")

    return "\n".join(lines)


@mcp.tool()
def predict_errors() -> str:
    """智能错误预测：分析错误模式，预测潜在问题并建议预防措施。"""
    if not _error_log and not _error_stats:
        return "暂无错误数据，无法预测"

    lines = ["=== 智能错误预测 ===\n"]
    predictions = []

    # 分析每个平台的错误模式
    for pk, info in PLATFORMS.items():
        platform_errors = [e for e in _error_log if e["platform"] == pk]
        if not platform_errors:
            continue

        name = info["name"]
        stats = _error_stats.get(pk, {})
        total_errors = sum(stats.values())

        # 1. 错误频率分析
        if len(platform_errors) >= 3:
            # 计算错误间隔
            timestamps = [e["ts"] for e in platform_errors]
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            avg_interval = sum(intervals) / len(intervals) if intervals else 0

            if avg_interval < 300:  # 5分钟内多次错误
                predictions.append(f"[{name}] 错误频繁: 平均{avg_interval:.0f}s一次，可能需要检查平台状态")

        # 2. 错误类型预测
        dominant_type = max(stats, key=stats.get) if stats else None
        if dominant_type:
            if dominant_type == "login" and stats.get("login", 0) > 3:
                predictions.append(f"[{name}] 登录即将过期: 已有{stats['login']}次登录错误，建议提前重新登录")
            elif dominant_type == "timeout" and stats.get("timeout", 0) > 5:
                predictions.append(f"[{name}] 超时风险高: 已有{stats['timeout']}次超时，建议增加超时时间")
            elif dominant_type == "error" and stats.get("error", 0) > 10:
                predictions.append(f"[{name}] 稳定性问题: 已有{stats['error']}次错误，建议检查页面结构")

        # 3. 时间模式分析
        if len(platform_errors) >= 5:
            hours = [time.localtime(e["ts"]).tm_hour for e in platform_errors]
            # 检查是否有特定时间段的错误集中
            hour_counts = {}
            for h in hours:
                hour_counts[h] = hour_counts.get(h, 0) + 1
            peak_hour = max(hour_counts, key=hour_counts.get)
            if hour_counts[peak_hour] > len(platform_errors) * 0.4:
                predictions.append(f"[{name}] 时间模式: {peak_hour}点错误集中({hour_counts[peak_hour]}次)，可能与平台维护相关")

    # 输出预测
    if predictions:
        lines.append("## 预测结果")
        for p in predictions:
            lines.append(f"  ⚠ {p}")
    else:
        lines.append("✓ 未发现明显错误模式")

    # 预防建议
    lines.append("\n## 预防建议")
    total_errors = sum(sum(v.values()) for v in _error_stats.values())
    if total_errors > 20:
        lines.append("  - 考虑增加请求间隔，减少平台压力")
    if any(s.get("login", 0) > 5 for s in _error_stats.values()):
        lines.append("  - 定期执行 login_platform 保持登录状态")
    if any(s.get("timeout", 0) > 10 for s in _error_stats.values()):
        lines.append("  - 增加 timeout 配置值，适应平台响应速度")

    return "\n".join(lines)


@mcp.tool()
async def rotate_proxy() -> str:
    """浏览器代理轮换：切换到代理池中的下一个代理，重启浏览器生效。"""
    global _browser
    pool = _config.get("proxy_pool", [])
    if not pool:
        return "代理池为空。使用 set_config('proxy_pool', '[\"http://host:port\"]') 配置"

    # 切换到下一个代理
    idx = (_config.get("proxy_index", 0) + 1) % len(pool)
    _config["proxy_index"] = idx
    _config["proxy_enabled"] = True

    # 关闭当前浏览器以应用新代理
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None

    proxy_url = pool[idx]
    _info(f"[rotate_proxy] switched to proxy {idx}: {proxy_url}")

    # 重新启动
    browser = await get_browser()
    if browser is None:
        return f"代理已切换到: {proxy_url}\n（浏览器由Playwright控制，需重启生效）"

    return f"代理已轮换 [{idx+1}/{len(pool)}]\n当前: {proxy_url}"


@mcp.tool()
def get_proxy_status() -> str:
    """查看代理池状态。"""
    pool = _config.get("proxy_pool", [])
    enabled = _config.get("proxy_enabled", False)
    idx = _config.get("proxy_index", 0)

    if not pool:
        return "代理池为空\n使用 set_config('proxy_pool', '[\"http://host:port\"]') 配置"

    lines = [f"代理池: {len(pool)}个", f"启用: {'是' if enabled else '否'}", f"当前索引: {idx}", ""]
    for i, p in enumerate(pool):
        marker = " ← 当前" if i == idx else ""
        lines.append(f"  [{i}] {p}{marker}")
    return "\n".join(lines)


@mcp.tool()
def health_check() -> str:
    """系统健康检查：配置状态、工具数、缓存、错误统计。"""
    lines = ["=== AI-chat MCP 健康检查 ===", ""]

    # 配置
    lines.append(f"Schema版本: {_config.get('schema_version', 'N/A')}")
    lines.append(f"工具模式: {_config.get('tool_mode', 'full')}")
    lines.append(f"Headless: {_config.get('headless', False)}")
    lines.append(f"重试次数: {_config.get('max_retries', 3)}")
    lines.append("")

    # 缓存
    lines.append(f"缓存条目: {len(_response_cache)}")
    lines.append(f"工具缓存: {len(_tool_call_cache)}")
    lines.append("")

    # 内存
    mem = _check_memory()
    lines.append(f"内存使用: {mem['memory_mb']}MB [{mem['status']}]")
    lines.append("")

    # 抓取统计
    total_ok = sum(s["success"] for s in _fetch_stats.values())
    total_fail = sum(s["fail"] for s in _fetch_stats.values())
    lines.append(f"抓取成功: {total_ok} / 失败: {total_fail}")
    lines.append("")

    # 错误统计
    total_err = sum(sum(v.values()) for v in _error_stats.values())
    lines.append(f"错误总数: {total_err}")

    # 性能
    lines.append(f"性能记录: {len(_perf_log)}条")
    lines.append(f"重连次数: {_reconnect_count}")

    # 浏览器状态
    browser_ok = False
    if _browser:
        try:
            _ = _browser.pages
            browser_ok = True
        except:
            pass
    lines.append(f"浏览器连接: {'正常' if browser_ok else '断开'}")

    return "\n".join(lines)


@mcp.tool()
def quick_diagnostic() -> str:
    """快速诊断：一键检查所有关键子系统状态，返回问题清单。"""
    issues = []
    warnings = []

    # 1. 浏览器连接
    browser_ok = False
    if _browser:
        try:
            _ = _browser.pages
            browser_ok = True
        except:
            pass
    if not browser_ok:
        issues.append("浏览器连接断开")

    # 2. 内存
    mem = _check_memory()
    if mem["status"] == "critical":
        issues.append(f"内存严重不足: {mem['memory_mb']}MB")
    elif mem["status"] == "warn":
        warnings.append(f"内存偏高: {mem['memory_mb']}MB")

    # 3. 抓取成功率
    for pk, fs in _fetch_stats.items():
        total = fs["success"] + fs["fail"]
        if total > 5:
            rate = fs["success"] / total * 100
            if rate < 50:
                issues.append(f"{PLATFORMS[pk]['name']} 成功率过低({rate:.0f}%)")
            elif rate < 80:
                warnings.append(f"{PLATFORMS[pk]['name']} 成功率偏低({rate:.0f}%)")

    # 5. 缓存命中率
    cache_total = _cache_stats["hits"] + _cache_stats["misses"]
    if cache_total > 10:
        cache_rate = _cache_stats["hits"] / cache_total * 100
        if cache_rate < 20:
            warnings.append(f"缓存命中率低({cache_rate:.0f}%)")

    # 6. 响应质量
    if _response_quality_log:
        recent_scores = [q["score"] for q in _response_quality_log[-10:]]
        avg_quality = sum(recent_scores) / len(recent_scores)
        if avg_quality < 40:
            warnings.append(f"近期响应质量低({avg_quality:.0f}分)")

    # 输出
    lines = ["═══ 快速诊断 ═══\n"]
    if issues:
        lines.append(f"❌ 问题 ({len(issues)}):")
        for issue in issues:
            lines.append(f"  - {issue}")
    if warnings:
        lines.append(f"⚠ 警告 ({len(warnings)}):")
        for w in warnings:
            lines.append(f"  - {w}")
    if not issues and not warnings:
        lines.append("✓ 所有系统正常")

    # 状态摘要
    lines.append(f"\n状态:")
    lines.append(f"  浏览器: {'✓' if browser_ok else '✗'}")
    lines.append(f"  内存: {mem['memory_mb']}MB")
    lines.append(f"  缓存: {len(_response_cache)}/{_CACHE_MAX}")

    return "\n".join(lines)


@mcp.tool()
def preview_snapshot() -> str:
    """预览当前系统状态快照内容，不实际保存。"""
    lines = ["=== 系统状态快照预览 ===\n"]

    # 基本信息
    lines.append(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"版本: 2.0")

    # 浏览器状态
    browser_ok = False
    pages_count = 0
    if _browser:
        try:
            pages_count = len(_browser.pages)
            browser_ok = True
        except:
            pass
    lines.append(f"\n浏览器: {'✓' if browser_ok else '✗'} ({pages_count}页面)")

    # 响应时间
    rt_platforms = len(_response_times)
    total_samples = sum(len(v) for v in _response_times.values())
    lines.append(f"响应时间: {rt_platforms}平台 ({total_samples}样本)")

    # 缓存统计
    lines.append(f"缓存统计: 命中{_cache_stats['hits']} 未命中{_cache_stats['misses']} 淘汰{_cache_stats['evictions']}")

    # 上下文缓存
    lines.append(f"上下文缓存: {len(_context_cache)}条 (命中{_context_cache_stats['hits']}次)")

    # 请求合并
    lines.append(f"请求合并: 总{_coalesced_stats['total']} 节省{_coalesced_stats['saved']}次")

    # 错误统计
    total_errors = sum(sum(v.values()) for v in _error_stats.values())
    lines.append(f"错误统计: {total_errors}次")

    # 协调状态
    lines.append(f"协调状态: 任务'{_coordination.get('current_task', '')[:20]}' 迭代{_coordination.get('iteration', 0)}")

    # 配置
    lines.append(f"\n配置项: {len(_config)}个")
    lines.append(f"  工具模式: {_config.get('tool_mode', 'full')}")
    lines.append(f"  最大重试: {_config.get('max_retries', 3)}")
    lines.append(f"  缓存TTL: {_CACHE_TTL}s")

    lines.append(f"\n估算大小: ~{len(str(_response_times)) + len(str(_error_stats)) + len(str(_config))}字节")

    return "\n".join(lines)


@mcp.tool()
def get_rate_limit_status() -> str:
    """自适应限流状态：显示各平台的动态限流配置。"""
    lines = ["=== 自适应限流状态 ===\n"]
    lines.append("平台 | 当前请求 | 窗口限制 | 最小间隔 | 状态")
    lines.append("--- | --- | --- | --- | ---")

    now = time.time()
    for pk, info in PLATFORMS.items():
        name = info["name"]
        limits = _get_adaptive_rate_limit(pk)

        # 当前窗口内请求数
        recent = _rate_limiter.get(pk, [])
        recent_count = len([t for t in recent if (now - t) < _config["rate_limit_window"]])

        # 状态判断
        if limits["interval"] > _config["rate_limit_interval"] * 2:
            status = "降速"
        elif recent_count >= limits["max"] * 0.8:
            status = "接近上限"
        else:
            status = "正常"

        lines.append(f"{name} | {recent_count} | {limits['max']} | {limits['interval']}s | {status}")

    lines.append(f"\n基础配置: 间隔{_config['rate_limit_interval']}s, 窗口{_config['rate_limit_window']}s, 最大{_config['rate_limit_max']}")
    lines.append(f"自适应: 高错误-3x, 慢响应-2x, 高并发-2x")
    return "\n".join(lines)


@mcp.tool()
def get_retry_budget_status() -> str:
    """重试预算状态：显示全局重试使用情况。"""
    lines = ["=== 重试预算状态 ===\n"]

    now = time.time()
    window = _config["retry_budget_window"]
    max_retries = _config["retry_budget_max"]

    # 清理过期记录
    active_retries = [t for t in _retry_budget if (now - t) < window]
    used = len(active_retries)
    remaining = max(0, max_retries - used)
    usage_rate = (used / max_retries * 100) if max_retries > 0 else 0

    lines.append(f"预算上限: {max_retries}次/{window}s窗口")
    lines.append(f"已使用: {used}次")
    lines.append(f"剩余: {remaining}次")
    lines.append(f"使用率: {usage_rate:.0f}%")

    # 状态
    if usage_rate >= 90:
        status = "⚠ 即将耗尽"
    elif usage_rate >= 70:
        status = "○ 偏高"
    elif usage_rate > 0:
        status = "✓ 正常"
    else:
        status = "✓ 无重试"
    lines.append(f"状态: {status}")

    # 最近重试时间
    if active_retries:
        lines.append(f"\n最近重试:")
        for t in active_retries[-5:]:
            ts = time.strftime("%H:%M:%S", time.localtime(t))
            lines.append(f"  [{ts}]")
        if len(active_retries) > 5:
            lines.append(f"  ... 共{len(active_retries)}次")

    lines.append(f"\n机制: 全局{window}s内最多{max_retries}次重试，防止重试风暴")
    return "\n".join(lines)


_dedup_stats = {"exact_hits": 0, "near_hits": 0, "total_checked": 0}


@mcp.tool()
def get_dedup_stats() -> str:
    """消息去重统计：显示精确匹配和近似匹配的拦截情况。"""
    lines = ["=== 消息去重统计 ===\n"]
    total = _dedup_stats["total_checked"]
    exact = _dedup_stats["exact_hits"]
    near = _dedup_stats["near_hits"]
    blocked = exact + near
    rate = (blocked / total * 100) if total > 0 else 0
    lines.append(f"检查总数: {total}")
    lines.append(f"精确拦截: {exact}")
    lines.append(f"近似拦截: {near}")
    lines.append(f"拦截率: {rate:.1f}%")
    lines.append(f"去重窗口: {_config['dedup_window']}s")
    lines.append(f"缓存条目: {len(_message_dedup)}/{len(_message_dedup_content)}")
    return "\n".join(lines)


@mcp.tool()
def get_platform_scores(task: str = "") -> str:
    """平台评分详情：显示各平台的推荐评分分解。"""
    lines = ["=== 平台评分详情 ===\n"]

    if not task:
        task = "测试任务"
    task_lower = task.lower()

    lines.append(f"任务: {task[:50]}")
    lines.append("")
    lines.append("平台 | 关键词 | 健康 | 质量 | 负载 | 综合")
    lines.append("--- | --- | --- | --- | --- | ---")

    # 计算各维度分数
    keyword_scores = {}
    for platform, keywords in _PLATFORM_STRENGTHS.items():
        score = sum(1 for kw in keywords if kw in task_lower)
        keyword_scores[platform] = min(score * 2, 10)

    health_scores = {}
    quality_scores_dict = {}
    load_scores = {}

    for pk in PLATFORMS:
        # 健康分
        health = 10
        stats = _error_stats.get(pk, {})
        total_err = sum(stats.values())
        if total_err > 5:
            health -= min(total_err * 0.5, 5)
        times = _response_times.get(pk, [])
        if times:
            avg_time = sum(times) / len(times)
            if avg_time > 10:
                health -= min((avg_time - 10) * 0.3, 3)
        fs = _fetch_stats.get(pk, {})
        total_fetch = fs.get("success", 0) + fs.get("fail", 0)
        if total_fetch > 0:
            success_rate = fs["success"] / total_fetch
            health += (success_rate - 0.5) * 4
        health_scores[pk] = max(0, min(health, 10))

        # 质量分
        quality_list = [q["score"] for q in _response_quality_log if q["platform"] == pk]
        if quality_list:
            quality_scores_dict[pk] = sum(quality_list[-5:]) / min(len(quality_list), 5)
        else:
            quality_scores_dict[pk] = 5.0

        # 负载分
        req_count = _active_requests.get(pk, {}).get("count", 0)
        load_scores[pk] = max(0, 10 - req_count * 2)

    # 综合评分
    final_scores = {}
    for pk in PLATFORMS:
        kw = keyword_scores.get(pk, 0)
        hp = health_scores.get(pk, 5)
        if kw == 0:
            final_scores[pk] = hp * 0.3
        else:
            final_scores[pk] = kw * 0.6 + hp * 0.4

    for pk in PLATFORMS:
        name = PLATFORMS[pk]["name"]
        kw = keyword_scores.get(pk, 0)
        hp = health_scores.get(pk, 5)
        ql = quality_scores_dict.get(pk, 5)
        ld = load_scores.get(pk, 10)
        fs = final_scores.get(pk, 0)

        # 标记最优
        marker = " ★" if pk == max(final_scores, key=final_scores.get) and fs > 1 else ""

        lines.append(f"{name} | {kw:.1f} | {hp:.1f} | {ql:.1f} | {ld:.1f} | {fs:.1f}{marker}")

    # 推荐结果
    best = max(final_scores, key=final_scores.get)
    if final_scores[best] > 1:
        lines.append(f"\n推荐: {PLATFORMS[best]['name']} (评分{final_scores[best]:.1f})")
    else:
        lines.append(f"\n无推荐 (最高分<1)")

    return "\n".join(lines)


@mcp.tool()
def get_coalescing_stats() -> str:
    """请求合并统计：显示并发请求合并效果。"""
    lines = ["=== 请求合并统计 ===\n"]

    total = _coalesced_stats["total"]
    saved = _coalesced_stats["saved"]
    rate = (saved / total * 100) if total > 0 else 0

    lines.append(f"总请求: {total}")
    lines.append(f"合并节省: {saved}次")
    lines.append(f"合并率: {rate:.1f}%")

    # 当前正在合并的请求
    inflight = len(_inflight_requests)
    if inflight > 0:
        lines.append(f"\n当前合并中: {inflight}个")
        for key, data in _inflight_requests.items():
            pk, msg_hash = key
            name = PLATFORMS.get(pk, {}).get("name", pk)
            lines.append(f"  {name}: {data['count']}个等待者")

    lines.append(f"\n机制: 相同平台+消息的并发请求共享同一结果")
    return "\n".join(lines)


@mcp.tool()
def get_timeout_stats() -> str:
    """自适应超时统计：显示各平台的响应时间和动态超时配置。"""
    lines = ["=== 自适应超时统计 ===\n"]
    lines.append("平台 | 样本 | P50 | P90 | 动态超时 | 默认超时")
    lines.append("--- | --- | --- | --- | --- | ---")

    for pk, info in PLATFORMS.items():
        name = info["name"]
        times = _response_times.get(pk, [])
        if len(times) >= 3:
            sorted_t = sorted(times)
            p50 = sorted_t[len(sorted_t) // 2]
            p90_idx = int(len(sorted_t) * 0.9)
            p90 = sorted_t[min(p90_idx, len(sorted_t) - 1)]
            dynamic = _get_dynamic_timeout(pk)
            lines.append(f"{name} | {len(times)} | {p50:.1f}s | {p90:.1f}s | {dynamic}s | 120s")
        else:
            lines.append(f"{name} | {len(times)} | - | - | 120s | 120s")

    lines.append(f"\n算法: P90*1.5+15s缓冲, 最小30s, 最大120s")
    return "\n".join(lines)


@mcp.tool()
def get_recovery_status() -> str:
    """健康恢复状态：显示各平台错误衰减和恢复进度。"""
    lines = ["=== 健康恢复状态 ===\n"]
    lines.append("平台 | 登录错 | 超时 | 一般错 | 未知 | 衰减 | 恢复进度")
    lines.append("--- | --- | --- | --- | --- | --- | ---")

    for pk, info in PLATFORMS.items():
        name = info["name"]
        stats = _error_stats.get(pk, {"login": 0, "timeout": 0, "error": 0, "unknown": 0})
        total_errors = sum(stats.values())

        # 恢复进度：基于总错误数
        if total_errors == 0:
            recovery = "✓ 健康"
        else:
            recovery = f"衰减中({total_errors})"

        lines.append(f"{name} | {stats['login']} | {stats['timeout']} | {stats['error']} | {stats['unknown']} | - | {recovery}")

    lines.append(f"\n衰减规则: 每30秒每类错误-1, 最小0")
    return "\n".join(lines)


@mcp.tool()
def get_health_trend() -> str:
    """健康评分趋势：显示最近健康评分变化和趋势分析。"""
    if not _health_score_history:
        return "暂无健康评分记录。调用 health_check 触发评分。"
    lines = ["=== 健康评分趋势 ===\n"]
    scores = [h["score"] for h in _health_score_history]
    avg = sum(scores) / len(scores)
    latest = scores[-1]
    highest = max(scores)
    lowest = min(scores)
    lines.append(f"最新: {latest}/100 | 平均: {avg:.0f} | 最高: {highest} | 最低: {lowest}")
    # 趋势判断
    if len(scores) >= 3:
        recent_avg = sum(scores[-3:]) / 3
        if recent_avg > avg:
            lines.append("趋势: ↗ 上升")
        elif recent_avg < avg:
            lines.append("趋势: ↘ 下降")
        else:
            lines.append("趋势: → 稳定")
    # 最近5次评分
    lines.append("\n最近评分:")
    for h in _health_score_history[-5:]:
        ts = h["ts"][11:19]
        bar = "█" * (h["score"] // 10) + "░" * (10 - h["score"] // 10)
        lines.append(f"  [{ts}] {bar} {h['score']}/100")
    return "\n".join(lines)


@mcp.tool()
def clear_cache() -> str:
    """清除响应缓存，强制重新查询。"""
    count = len(_response_cache)
    _response_cache.clear()
    return f"已清除 {count} 条缓存"


@mcp.tool()
async def warmup_cache(platforms: str = "all", messages: str = "", mode: str = "smart") -> str:
    """智能缓存预热：基于历史使用模式分析，预加载最可能需要的查询。mode: smart=基于模式, static=静态消息, both=两者结合。"""
    target_platforms = list(PLATFORMS.keys()) if platforms == "all" else [p.strip() for p in platforms.split(",") if p.strip() in PLATFORMS]
    if not target_platforms:
        return f"无效平台: {platforms}"

    msg_list = []
    lines = ["=== 智能缓存预热 ===\n"]

    # 模式1: 静态默认消息
    default_msgs = ["你好", "1+1=?", "测试"]
    if messages:
        msg_list.extend([m.strip() for m in messages.split(",") if m.strip()])

    # 模式2: 基于历史使用模式
    if mode in ("smart", "both"):
        smart_msgs = _get_smart_warmup_messages(target_platforms)
        msg_list.extend(smart_msgs)
        if smart_msgs:
            lines.append(f"[模式] 从历史使用中提取 {len(smart_msgs)} 条模式消息")

    # 模式3: 静态默认
    if mode in ("static", "both") or (not messages and not _usage_tracker["message_patterns"]):
        msg_list.extend(default_msgs)

    # 去重
    seen = set()
    unique_msgs = []
    for m in msg_list:
        if m not in seen:
            seen.add(m)
            unique_msgs.append(m)
    msg_list = unique_msgs

    warmed = 0
    skipped = 0
    for pk in target_platforms:
        name = PLATFORMS[pk]["name"]
        for msg in msg_list:
            cache_key = (pk, hashlib.md5(msg.encode()).hexdigest())
            if cache_key in _response_cache:
                skipped += 1
                continue
            try:
                result = await do_chat(pk, msg, 60)
                if not result.startswith("[") or "错误" not in result:
                    warmed += 1
                    lines.append(f"[{name}] '{msg}' → 预热成功")
                else:
                    lines.append(f"[{name}] '{msg}' → 跳过（{result[:30]}）")
            except Exception as e:
                lines.append(f"[{name}] '{msg}' → 失败: {str(e)[:30]}")

    lines.append(f"\n预热: {warmed}条, 跳过: {skipped}条（已缓存）")
    lines.append(f"缓存总数: {len(_response_cache)}条")
    return "\n".join(lines)


def _get_smart_warmup_messages(platforms: list) -> list:
    """从历史使用模式中提取高频查询前缀用于智能预热。"""
    if not _usage_tracker["message_patterns"]:
        return []

    # 统计每个前缀在目标平台上的出现次数
    prefix_counts = {}
    for entry in _usage_tracker["message_patterns"]:
        if entry["platform"] in platforms:
            p = entry["prefix"]
            prefix_counts[p] = prefix_counts.get(p, 0) + 1

    # 取出现2次以上的前缀，最多5条
    hot_prefixes = sorted(prefix_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    return [p for p, c in hot_prefixes if c >= 2]


@mcp.tool()
def create_task_chain(name: str, steps: str) -> str:
    """创建任务链：多步骤跨平台工作流。steps格式：'platform1:msg1|platform2:msg2'。支持{result}引用上一步结果。"""
    global _chain_counter
    _chain_counter += 1
    chain_id = f"chain_{_chain_counter}"
    parsed_steps = []
    for step_str in steps.split("|"):
        step_str = step_str.strip()
        if ":" in step_str:
            platform, msg = step_str.split(":", 1)
            parsed_steps.append({"platform": platform.strip(), "message": msg.strip(), "status": "pending"})
    if not parsed_steps:
        return "错误：无有效步骤。格式：'platform1:msg1|platform2:msg2'"
    _task_chains[chain_id] = {
        "name": name, "steps": parsed_steps, "results": [], "status": "created",
        "created": datetime.datetime.now().isoformat(),
    }
    return f"任务链已创建: {chain_id} ({name})\n步骤数: {len(parsed_steps)}\n" + "\n".join(
        f"  {i+1}. [{s['platform']}] {s['message'][:50]}" for i, s in enumerate(parsed_steps)
    )


@mcp.tool()
async def execute_task_chain(chain_id: str) -> str:
    """执行任务链：按顺序执行各步骤，上一步结果自动传入下一步（{result}占位符）。"""
    chain = _task_chains.get(chain_id)
    if not chain:
        return f"错误：任务链 {chain_id} 不存在"
    chain["status"] = "running"
    results = []
    for i, step in enumerate(chain["steps"]):
        msg = step["message"]
        # 替换{result}占位符
        if "{result}" in msg and results:
            msg = msg.replace("{result}", results[-1][:2000])
        step["status"] = "running"
        try:
            result = await do_chat(step["platform"], msg)
            step["status"] = "done"
            results.append(result)
            chain["results"].append({"step": i, "platform": step["platform"], "result": result[:500]})
        except Exception as e:
            step["status"] = "failed"
            results.append(f"[错误] {str(e)[:200]}")
            chain["results"].append({"step": i, "platform": step["platform"], "error": str(e)[:200]})
            chain["status"] = "partial"
            break
    if chain["status"] == "running":
        chain["status"] = "done"
    summary = f"任务链 {chain_id} 执行完成\n状态: {chain['status']}\n步骤: {len([s for s in chain['steps'] if s['status']=='done'])}/{len(chain['steps'])}"
    return summary


@mcp.tool()
def get_task_chain_status(chain_id: str = "") -> str:
    """查看任务链状态。chain_id为空则显示所有任务链。"""
    if chain_id:
        chain = _task_chains.get(chain_id)
        if not chain:
            return f"任务链 {chain_id} 不存在"
        lines = [f"任务链: {chain_id} ({chain['name']})"]
        lines.append(f"状态: {chain['status']}")
        lines.append(f"创建: {chain['created']}")
        lines.append("步骤:")
        for i, s in enumerate(chain["steps"]):
            status_icon = {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌"}.get(s["status"], "?")
            lines.append(f"  {i+1}. {status_icon} [{s['platform']}] {s['message'][:40]}")
        return "\n".join(lines)
    if not _task_chains:
        return "暂无任务链"
    lines = ["所有任务链:"]
    for cid, c in _task_chains.items():
        lines.append(f"  {cid}: {c['name']} [{c['status']}] ({len(c['steps'])}步)")
    return "\n".join(lines)


@mcp.tool()
def delete_task_chain(chain_id: str) -> str:
    """删除任务链。"""
    if chain_id in _task_chains:
        del _task_chains[chain_id]
        return f"已删除: {chain_id}"
    return f"任务链 {chain_id} 不存在"


@mcp.tool()
def list_workflow_templates() -> str:
    """列出所有可用的工作流模板。"""
    lines = ["=== 工作流模板 ===\n"]
    for tid, t in _WORKFLOW_TEMPLATES.items():
        lines.append(f"  {tid}: {t['name']}")
        lines.append(f"    {t['description']}")
        lines.append(f"    步骤: {len(t['steps'])}个")
    return "\n".join(lines)


@mcp.tool()
async def run_workflow(template_id: str, **kwargs) -> str:
    """运行工作流模板。template_id为模板名称，kwargs为模板参数（如topic、text、code）。"""
    template = _WORKFLOW_TEMPLATES.get(template_id)
    if not template:
        available = ", ".join(_WORKFLOW_TEMPLATES.keys())
        return f"模板 '{template_id}' 不存在。可用: {available}"
    global _chain_counter
    _chain_counter += 1
    chain_id = f"wf_{_chain_counter}"
    results = []
    for step in template["steps"]:
        msg = step["message"]
        for k, v in kwargs.items():
            msg = msg.replace(f"{{{k}}}", str(v))
        if "{result}" in msg and results:
            msg = msg.replace("{result}", results[-1][:2000])
        try:
            result = await do_chat(step["platform"], msg)
            results.append(result)
        except Exception as e:
            return f"[工作流中断] {step['platform']}失败: {str(e)[:200]}\n已完成{len(results)}/{len(template['steps'])}步"
    summary = f"工作流 '{template['name']}' 执行完成\n"
    for i, (step, res) in enumerate(zip(template["steps"], results)):
        summary += f"\n--- 步骤{i+1} [{step['platform']}] ---\n{res[:300]}"
    return summary


@mcp.tool()
def add_workflow_template(template_id: str, name: str, description: str, steps: str) -> str:
    """添加自定义工作流模板。steps格式：'platform1:msg1|platform2:msg2'。"""
    parsed = []
    for s in steps.split("|"):
        s = s.strip()
        if ":" in s:
            platform, msg = s.split(":", 1)
            parsed.append({"platform": platform.strip(), "message": msg.strip()})
    if not parsed:
        return "错误：无有效步骤"
    _WORKFLOW_TEMPLATES[template_id] = {
        "name": name, "description": description, "steps": parsed,
    }
    return f"模板已添加: {template_id} ({name})"


@mcp.tool()
def delete_workflow_template(template_id: str) -> str:
    """删除工作流模板。"""
    if template_id in _WORKFLOW_TEMPLATES:
        del _WORKFLOW_TEMPLATES[template_id]
        return f"已删除: {template_id}"
    return f"模板 '{template_id}' 不存在"


@mcp.tool()
def enqueue_task(task: str, platforms: str = "doubao", priority: int = -1) -> str:
    """加入任务队列。priority: -1=自动(默认), 0=最高, 1=普通, 2=低。platforms逗号分隔。"""
    targets = [p.strip() for p in platforms.split(",") if p.strip()]

    # 智能优先级：根据平台负载自动调整
    if priority == -1:
        priority = 1  # 默认普通
        for pk in targets:
            stats = _error_stats.get(pk, {})
            total_err = sum(stats.values())
            if total_err > 10:
                priority = 0  # 高优先级：平台错误多，尽快处理
                break
            times = _response_times.get(pk, [])
            if times and sum(times) / len(times) > 15:
                priority = 0  # 高优先级：平台响应慢
                break

    entry = {
        "task": task,
        "platforms": targets,
        "priority": priority,
        "ts": time.strftime('%H:%M:%S'),
        "status": "pending",
    }
    _task_queue.append(entry)
    _task_queue.sort(key=lambda x: x["priority"])
    if len(_task_queue) > _QUEUE_MAX:
        _task_queue.pop()
    return f"已入队: {task[:30]}... (优先级{priority}, {len(_task_queue)}条待处理)"


@mcp.tool()
def process_queue() -> str:
    """处理任务队列：智能调度，考虑平台健康和负载后取出最优任务。"""
    if not _task_queue:
        return "队列为空"

    # 自动重平衡
    for task in _task_queue:
        if task["status"] != "pending":
            continue
        for pk in task["platforms"]:
            # 高负载平台降级
            req_count = _active_requests.get(pk, {}).get("count", 0)
            if req_count > 2:
                task["priority"] = max(task["priority"], 0)

    _task_queue.sort(key=lambda x: x["priority"])

    # 取出最高优先级的pending任务
    for i, task in enumerate(_task_queue):
        if task["status"] == "pending":
            task["status"] = "processing"
            _task_queue.pop(i)
            return f"任务: {task['task']}\n平台: {', '.join(task['platforms'])}\n优先级: {task['priority']}"

    return "无待处理任务"


@mcp.tool()
def get_queue_status() -> str:
    """查看任务队列状态。"""
    if not _task_queue:
        return "队列为空"
    lines = [f"队列: {len(_task_queue)}条", ""]
    lines.append("优先级 | 任务 | 平台 | 状态 | 时间")
    lines.append("--- | --- | --- | --- | ---")
    for t in _task_queue:
        lines.append(f"{t['priority']} | {t['task'][:25]}... | {','.join(t['platforms'])} | {t['status']} | {t['ts']}")
    return "\n".join(lines)


@mcp.tool()
def rebalance_queue() -> str:
    """智能队列重平衡：根据当前平台负载动态调整待处理任务优先级。"""
    if not _task_queue:
        return "队列为空，无需重平衡"

    rebalanced = 0
    for task in _task_queue:
        if task["status"] != "pending":
            continue
        old_priority = task["priority"]
        new_priority = 1  # 默认普通

        for pk in task["platforms"]:
            stats = _error_stats.get(pk, {})
            total_err = sum(stats.values())
            if total_err > 10:
                new_priority = 0
                break
            times = _response_times.get(pk, [])
            if times and sum(times) / len(times) > 15:
                new_priority = 0
                break
            # 低错误+快速响应 → 可降低优先级
            if total_err < 3 and times and sum(times) / len(times) < 5:
                new_priority = 2

        if new_priority != old_priority:
            task["priority"] = new_priority
            rebalanced += 1

    _task_queue.sort(key=lambda x: x["priority"])
    return f"重平衡完成: {rebalanced}/{len(_task_queue)}条任务优先级已调整"


@mcp.tool()
def get_scheduling_info() -> str:
    """智能调度信息：显示队列任务的调度决策依据。"""
    if not _task_queue:
        return "队列为空"

    lines = ["=== 智能调度信息 ===\n"]
    pending = [t for t in _task_queue if t["status"] == "pending"]
    processing = [t for t in _task_queue if t["status"] == "processing"]

    lines.append(f"待处理: {len(pending)}条, 处理中: {len(processing)}条\n")

    if pending:
        lines.append("任务 | 优先级 | 平台状态 | 调度建议")
        lines.append("--- | --- | --- | ---")
        for t in pending[:5]:
            platforms_status = []
            suggestions = []
            for pk in t["platforms"]:
                name = PLATFORMS.get(pk, {}).get("name", pk)
                if _active_requests.get(pk, {}).get("count", 0) > 2:
                    platforms_status.append(f"{name}:忙")
                    suggestions.append("等待")
                else:
                    platforms_status.append(f"{name}:就绪")
                    suggestions.append("可执行")

            status_str = ", ".join(platforms_status)
            suggestion = suggestions[0] if len(set(suggestions)) == 1 else "混合"
            lines.append(f"{t['task'][:20]}... | {t['priority']} | {status_str} | {suggestion}")

    return "\n".join(lines)


@mcp.tool()
def save_checkpoint(task_id: str) -> str:
    """保存当前任务检查点，支持断点续传。"""
    _save_checkpoint(task_id)
    return f"检查点已保存: {task_id}"


@mcp.tool()
def restore_checkpoint(task_id: str) -> str:
    """恢复任务检查点，继续执行。"""
    if _restore_checkpoint(task_id):
        return f"已恢复: {_coordination['current_task'][:50]}"
    return f"检查点不存在: {task_id}"


@mcp.tool()
def get_config() -> str:
    """获取当前所有配置参数。"""
    lines = ["配置参数:", ""]
    lines.append("参数 | 值 | 说明")
    lines.append("--- | --- | ---")
    lines.append(f"schema_version | {_config['schema_version']} | Schema版本")
    lines.append(f"tool_mode | {_config['tool_mode']} | 工具集模式(full/browser-only/api-only/smart)")
    lines.append(f"headless | {_config['headless']} | 无头浏览器模式(CI/CD)")
    lines.append(f"max_retries | {_config['max_retries']} | 最大重试次数")
    lines.append(f"retry_delay | {_config['retry_delay']} | 重试间隔(秒)")
    lines.append(f"max_pages | {_config['max_pages']} | 最大页面数")
    lines.append(f"page_idle_timeout | {_config['page_idle_timeout']} | 页面空闲超时(秒)")
    lines.append(f"chat_timeout | {_config['chat_timeout']} | 对话超时(秒)")
    lines.append(f"streaming_timeout | {_config['streaming_timeout']} | 流式响应超时(秒)")
    lines.append(f"no_response_timeout | {_config['no_response_timeout']} | 无响应快速失败(秒)")
    lines.append(f"log_level | {_config['log_level']} | 日志级别")
    return "\n".join(lines)


@mcp.tool()
def set_config(key: str, value: str) -> str:
    """热更新配置参数，无需重启MCP服务器。"""
    # 类型映射
    int_keys = {"max_retries", "retry_delay", "max_pages", "page_idle_timeout",
                "chat_timeout", "streaming_timeout", "no_response_timeout"}
    bool_keys = {"headless"}
    str_keys = {"log_level"}
    valid_modes = {"full", "browser-only", "api-only", "smart"}

    if key not in _config:
        valid = ", ".join(sorted(_config.keys()))
        return f"未知参数: {key}。可用参数: {valid}"

    # 类型转换
    if key in int_keys:
        try:
            _config[key] = int(value)
        except ValueError:
            return f"参数 {key} 需要整数值，当前: {value}"
    elif key in bool_keys:
        _config[key] = value.lower() in ("true", "1", "yes", "on")
    elif key == "tool_mode":
        if value not in valid_modes:
            return f"无效模式: {value}。可选: {', '.join(valid_modes)}"
        _config[key] = value
    elif key in str_keys:
        _config[key] = value.upper()
    else:
        return f"不支持修改参数: {key}"

    _info(f"[config] {key} updated to {_config[key]}")
    return f"已更新: {key} = {_config[key]}"


@mcp.tool()
def get_cache_stats() -> str:
    """缓存性能监控：显示缓存命中率、淘汰次数、条目数等统计。"""
    total_requests = _cache_stats["hits"] + _cache_stats["misses"]
    hit_rate = _cache_stats["hits"] / total_requests * 100 if total_requests > 0 else 0

    lines = ["=== 缓存性能监控 ===\n"]
    lines.append(f"响应缓存:")
    lines.append(f"  条目数: {len(_response_cache)} / {_CACHE_MAX}")
    lines.append(f"  命中: {_cache_stats['hits']}次")
    lines.append(f"  未命中: {_cache_stats['misses']}次")
    lines.append(f"  命中率: {hit_rate:.1f}%")
    lines.append(f"  淘汰: {_cache_stats['evictions']}次")
    lines.append(f"  TTL: {_CACHE_TTL}秒")

    lines.append(f"\n工具调用缓存:")
    lines.append(f"  条目数: {len(_tool_call_cache)}")
    lines.append(f"  TTL: {_TOOL_CACHE_TTL}秒")

    lines.append(f"\n消息去重:")
    lines.append(f"  条目数: {len(_message_dedup)}")
    lines.append(f"  窗口: {_config['dedup_window']}秒")

    # 建议
    lines.append("\n## 优化建议")
    if hit_rate < 30 and total_requests > 10:
        lines.append("  - 命中率低，考虑增加CACHE_TTL或优化缓存键策略")
    if len(_response_cache) > _CACHE_MAX * 0.8:
        lines.append("  - 缓存接近上限，考虑增加CACHE_MAX或缩短TTL")
    if _cache_stats["evictions"] > _cache_stats["hits"]:
        lines.append("  - 淘汰过多，考虑增加CACHE_MAX")

    return "\n".join(lines)


@mcp.tool()
def get_load_status() -> str:
    """平台负载监控：显示各平台并发请求数和总处理量。"""
    lines = ["=== 平台负载监控 ===\n"]
    lines.append("平台 | 并发 | 总请求 | 运行时间")
    lines.append("--- | --- | --- | ---")

    for pk, info in PLATFORMS.items():
        data = _active_requests.get(pk, {"count": 0, "start": time.time(), "total": 0})
        concurrent = data["count"]
        total = data["total"]
        runtime = time.time() - data["start"]
        name = info["name"]

        # 状态标记
        if concurrent > 3:
            status = "⚠ 高负载"
        elif concurrent > 0:
            status = "→ 处理中"
        else:
            status = "✓ 空闲"

        lines.append(f"{name} | {concurrent} | {total} | {runtime:.0f}s {status}")

    # 总计
    total_concurrent = sum(d["count"] for d in _active_requests.values())
    total_requests = sum(d["total"] for d in _active_requests.values())
    lines.append(f"\n总计: {total_concurrent}个并发, {total_requests}个请求")

    return "\n".join(lines)


@mcp.tool()
def get_usage_stats() -> str:
    """使用模式分析：显示平台查询频率、热门消息模式、小时使用热力图。"""
    lines = ["=== 使用模式分析 ===\n"]

    # 1. 平台查询统计
    lines.append("### 平台查询频率")
    pq = _usage_tracker["platform_queries"]
    if pq:
        sorted_platforms = sorted(pq.items(), key=lambda x: x[1]["count"], reverse=True)
        for pk, data in sorted_platforms:
            name = PLATFORMS.get(pk, {}).get("name", pk)
            lines.append(f"  {name}: {data['count']}次, 最近: {data['last_used'][:16]}")
    else:
        lines.append("  暂无数据")

    # 2. 热门消息模式
    lines.append("\n### 热门消息模式 (前缀)")
    patterns = _usage_tracker["message_patterns"]
    if patterns:
        prefix_counts = {}
        for p in patterns:
            prefix_counts[p["prefix"]] = prefix_counts.get(p["prefix"], 0) + 1
        hot = sorted(prefix_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for prefix, count in hot:
            lines.append(f"  '{prefix}' → {count}次")
    else:
        lines.append("  暂无数据")

    # 3. 小时使用热力图
    lines.append("\n### 小时使用分布")
    hourly = _usage_tracker["hourly_pattern"]
    if hourly:
        for hour in sorted(hourly.keys()):
            platforms_str = ", ".join(f"{PLATFORMS.get(p, {}).get('name', p)}:{c}" for p, c in hourly[hour].items())
            lines.append(f"  {hour}:00 → {platforms_str}")
    else:
        lines.append("  暂无数据")

    lines.append(f"\n跟踪条目: {len(patterns)}/{_USAGE_MAX}")
    return "\n".join(lines)


@mcp.tool()
def get_page_pool_status() -> str:
    """页面池状态：显示各平台预创建页面的可用性和最后使用时间。"""
    lines = ["=== 页面池状态 ===\n"]
    lines.append("平台 | 页面就绪 | 最后使用 | 状态")
    lines.append("--- | --- | --- | ---")

    now = time.time()
    for pk in PLATFORMS:
        name = PLATFORMS[pk]["name"]
        if pk in _page_pool:
            data = _page_pool[pk]
            age = now - data["last_used"]
            if age < 60:
                status = "✓ 活跃"
            elif age < _PAGE_POOL_TTL:
                status = f"○ 空闲({age:.0f}s)"
            else:
                status = "⚠ 过期"
            lines.append(f"{name} | ✓ | {data['last_used']:.0f}s前 | {status}")
        else:
            lines.append(f"{name} | ✗ | - | 未创建")

    total = len(_page_pool)
    lines.append(f"\n页面池: {total}/{len(PLATFORMS)}个平台已预创建")
    lines.append(f"过期阈值: {_PAGE_POOL_TTL}s")
    return "\n".join(lines)


@mcp.tool()
@mcp.tool()
def invalidate_cache(platform: str = "", pattern: str = "", clear_all: bool = False) -> str:
    """缓存失效管理：按平台/模式/全量清除缓存。platform=指定平台, pattern=消息前缀匹配, clear_all=完全清除。"""
    lines = ["=== 缓存失效 ===\n"]

    if clear_all:
        counts = _clear_all_cache()
        lines.append("完全清除:")
        for name, count in counts.items():
            lines.append(f"  {name}: {count}条已清除")
        return "\n".join(lines)

    if platform:
        if platform not in PLATFORMS:
            return f"无效平台: {platform}"
        count = _invalidate_platform_cache(platform)
        lines.append(f"[{PLATFORMS[platform]['name']}] 清除{count}条缓存")
        return "\n".join(lines)

    if pattern:
        count = _invalidate_by_pattern(pattern)
        lines.append(f"模式 '{pattern}': 清除{count}条缓存")
        return "\n".join(lines)

    # 显示当前缓存状态供参考
    lines.append("用法:")
    lines.append("  invalidate_cache(platform='doubao') — 清除指定平台")
    lines.append("  invalidate_cache(pattern='你好') — 按模式清除")
    lines.append("  invalidate_cache(clear_all=true) — 完全清除")
    lines.append(f"\n当前缓存: {len(_response_cache)}条响应, {len(_tool_call_cache)}条工具")
    return "\n".join(lines)


@mcp.tool()
def get_context_cache_stats() -> str:
    """上下文缓存统计：显示缓存条目数、命中率、节省Token数。"""
    total = _context_cache_stats["hits"] + _context_cache_stats["misses"]
    hit_rate = (_context_cache_stats["hits"] / total * 100) if total > 0 else 0

    lines = ["=== 上下文缓存统计 ===\n"]
    lines.append(f"条目数: {len(_context_cache)}/{_CONTEXT_CACHE_MAX}")
    lines.append(f"命中: {_context_cache_stats['hits']}次")
    lines.append(f"未命中: {_context_cache_stats['misses']}次")
    lines.append(f"命中率: {hit_rate:.1f}%")
    lines.append(f"节省Token: ~{_context_cache_stats['tokens_saved']}")
    lines.append(f"\n过期阈值: {_CONTEXT_CACHE_TTL}s")

    # 显示缓存条目详情
    if _context_cache:
        lines.append(f"\n缓存条目:")
        for key, data in sorted(_context_cache.items(), key=lambda x: -x[1]["hits"])[:5]:
            age = time.time() - data["ts"]
            lines.append(f"  [{key[:8]}] 命中{data['hits']}次, ~{data['tokens']}tokens, {age:.0f}s前")

    return "\n".join(lines)


@mcp.tool()
def clear_context_cache() -> str:
    """清除上下文缓存。"""
    count = len(_context_cache)
    _context_cache.clear()
    return f"已清除{count}条上下文缓存"


@mcp.tool()
def get_tool_status() -> str:
    """获取工具集状态：当前模式、激活工具数、各模式工具列表。"""
    mode = _config.get("tool_mode", "full")
    active = _get_active_tools()
    all_tools = list(TOOL_SETS.keys())

    lines = ["工具集状态:", ""]
    lines.append(f"当前模式: {mode}")
    lines.append(f"激活工具数: {len(active) if active else '全部(18)'}")
    lines.append("")

    for m in all_tools:
        tools = TOOL_SETS[m]
        if tools is None:
            lines.append(f"[{m}] 全部工具")
        else:
            lines.append(f"[{m}] {len(tools)}个: {', '.join(tools[:3])}...")

    return "\n".join(lines)


@mcp.tool()
async def run_benchmark(platforms: str = "all", message: str = "1+1=?", timeout: int = 60) -> str:
    """性能测试：发送消息并记录响应时间。"""
    # 解析平台列表
    if platforms == "all":
        target_platforms = list(PLATFORMS.keys())
    else:
        target_platforms = [p.strip() for p in platforms.split(",") if p.strip() in PLATFORMS]

    if not target_platforms:
        return f"无效平台: {platforms}。可选: {', '.join(PLATFORMS.keys())}"

    results = []
    results.append(f"=== 性能基准测试 ===")
    results.append(f"测试消息: {message}")
    results.append(f"超时: {timeout}s\n")

    for platform_key in target_platforms:
        info = PLATFORMS[platform_key]
        results.append(f"--- {info['name']} ({platform_key}) ---")

        # 检查登录状态
        page = await ensure_page(platform_key)
        if page is None:
            results.append("  [跳过] 页面未启动")
            continue

        if is_login_page(page.url, platform_key):
            results.append("  [跳过] 需要登录")
            continue

        # 执行测试
        t0 = time.time()
        try:
            response = await do_chat(platform_key, message, timeout)
            elapsed = time.time() - t0

            # 判断是否成功
            is_error = response.startswith("[") and ("错误" in response or "超时" in response or "失败" in response)
            status = "FAIL" if is_error else "OK"

            results.append(f"  状态: {status}")
            results.append(f"  耗时: {elapsed:.2f}s")
            if not is_error:
                results.append(f"  响应长度: {len(response)}字")
                results.append(f"  响应预览: {response[:100]}...")
            else:
                results.append(f"  错误: {response[:200]}")

        except Exception as e:
            elapsed = time.time() - t0
            results.append(f"  状态: ERROR")
            results.append(f"  耗时: {elapsed:.2f}s")
            results.append(f"  异常: {str(e)[:200]}")

        results.append("")

    # 汇总统计
    results.append("=== 汇总统计 ===")
    results.append(get_fetch_stats())

    return "\n".join(results)


if __name__ == "__main__":
    _dbg("Starting mcp.run(transport='stdio')")
    mcp.run(transport="stdio")
