"""agent/utils.py - Shared utility functions

Provides unified response helpers, retry-after parsing, and error response construction.
Eliminates duplication across browser/utils, kb_crawl, kb_utils, kb_core, knowledge_service, llm_client.
"""

from typing import Any, Dict, Optional


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Response helpers (unified from 5 independent implementations)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _make_response(code: int, msg: str, data: Any = None) -> Dict:
    """Unified response format used across all tools and services."""
    return {"code": code, "msg": msg, "data": data}


def _ok(data: Any = None, msg: str = "success") -> Dict:
    """Success response: {"code": 200, "msg": "success", "data": ...}"""
    return _make_response(200, msg, data if data is not None else {})


def _err(code: int, msg: str) -> Dict:
    """Error response: {"code": N, "msg": "...", "data": {}}"""
    return _make_response(code, msg, {})


def _warn(msg: str) -> Dict:
    """Warning response (success code with warning message)."""
    return _make_response(200, msg)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLM client helpers (extracted from llm_client.py duplication)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_retry_after(headers, default: float = 30.0) -> float:
    """Parse Retry-After header with safe fallback.

    Extracted from 3 identical copies in llm_client.py.
    """
    retry_after = default
    if "retry-after" in headers:
        try:
            retry_after = float(headers["retry-after"])
        except (ValueError, TypeError):
            pass
    return retry_after


def _error_response(content: str, status_code: int = -1) -> Dict:
    """Construct a standardized LLM error response.

    Extracted from 10 identical dict constructions in llm_client.py.
    """
    return {
        "content": content,
        "usage": {},
        "tool_calls": [],
        "status_code": status_code,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Hashing (unified from 4 independent implementations)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def short_hash(text: str, length: int = 8) -> str:
    """Quick hash for deduplication/keys. Consistent length across codebase."""
    import hashlib
    return hashlib.md5(text.encode()).hexdigest()[:length]
def load_json_file(path, default=None):
    """安全加载JSON文件，失败返回default"""
    import json
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return default if default is not None else {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}

