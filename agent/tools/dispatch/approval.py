"""审批流程 + 共享上下文 + 知识库查询"""

import json
import re
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging
import threading
from ...config import AI_KB_INDEX

logger = logging.getLogger(__name__)


# ── 审批系统（asyncio.Future 替代轮询）──────────────────────────────

_pending_approvals: Dict[str, Dict[str, Any]] = {}  # id -> {info, future}


# ── 子代理间共享上下文（SharedContext）───────────────────────────────

_shared_context: Dict[str, Any] = {}  # key -> value，子代理可读写


# ── 知识库路径 + 缓存（线程安全）─────────────────────────────────────

_KB_INDEX_PATH = AI_KB_INDEX
_kb_index_cache: Optional[list] = None
_kb_index_mtime: float = 0.0
_kb_cache_lock = threading.Lock()


def _kb_query_sync(question: str, limit: int = 3) -> list:
    """同步查询知识库索引（关键词匹配，带缓存+线程安全）"""
    global _kb_index_cache, _kb_index_mtime
    try:
        with _kb_cache_lock:
            if _KB_INDEX_PATH.exists():
                mtime = _KB_INDEX_PATH.stat().st_mtime
                if mtime != _kb_index_mtime or _kb_index_cache is None:
                    data = json.loads(_KB_INDEX_PATH.read_text(encoding="utf-8"))
                    _kb_index_cache = data.get("documents", []) if isinstance(data, dict) else []
                    _kb_index_mtime = mtime
                docs = _kb_index_cache
            else:
                docs = []
    except Exception as e:
        logger.warning(f"KB索引加载失败: {e}")
        return []

    if not docs:
        return []

    question_lower = question.lower()
    # 中英文AI术语映射
    _ZH_EN_MAP = {
        "多模态": "multimodal", "推理": "reasoning", "安全": "safety guard",
        "代码": "code", "模型": "model", "训练": "training",
        "微调": "fine-tune lora", "检索": "retrieval rag",
        "agent": "agentic tool", "工具": "tool calling",
        "视觉": "vision image", "轻量": "lightweight small",
        "路由": "routing", "分类": "classification",
    }
    # 展开中文查询为中英文混合
    expanded = [question_lower]
    for zh, en in _ZH_EN_MAP.items():
        if zh in question_lower:
            expanded.append(en)
    question_words = []
    for part in expanded:
        question_words.extend(part.split())
    scored = []

    for doc in docs:
        try:
            # 构建可搜索文本（标题+概念+标签+摘要）
            all_text = " ".join([
                doc.get("title") or "",
                " ".join(doc.get("concepts") or []),
                " ".join(doc.get("tags") or []),
                doc.get("summary") or "",
            ]).lower()

            # 关键词匹配（使用共享评分函数）
            from ...kb.kb_utils import score_document
            score = score_document(question_words, doc)

            # 子串匹配（兜底：查询文本出现在任何字段中）
            for part in re.findall(r'[a-zA-Z0-9]+|[一-鿿]+', question_lower):
                if len(part) >= 2 and part in all_text:
                    score += 1
            if score > 0:
                scored.append((score, doc))
        except Exception as e:
            logger.debug("caught exception, continuing: %s", e)
            continue  # 跳过单个损坏文档，不毒化整个扫描

    scored.sort(key=lambda x: -x[0])
    return [
        {"title": d.get("title") or "", "path": d.get("path") or "",
         "concepts": d.get("concepts") or [], "tags": d.get("tags") or [],
         "summary": (d.get("summary") or "")[:300]}
        for _, d in scored[:limit]
    ]


# ── 模块级审批函数 ─────────────────────────────────────────────────

def _approve_task(approval_id: str, approved: bool = True, reason: str = ""):
    """提交审批结果（内部函数，供UI/CLI调用，不暴露给LLM）"""
    from .parallel import get_dispatcher
    dispatcher = get_dispatcher()
    dispatcher.approve(approval_id, approved, reason)


def get_pending_approvals() -> list:
    """获取待审批列表"""
    from .parallel import get_dispatcher
    dispatcher = get_dispatcher()
    return dispatcher.get_pending_approvals()


# ── 共享上下文操作 ──────────────────────────────────────────────────

def shared_context_set(key: str, value: str, ttl: int = 1800) -> dict:
    """写入共享上下文（子代理间通信，带TTL过期）"""
    _shared_context[key] = {"value": value, "expires": time.time() + ttl}
    return {"key": key, "status": "set"}


def shared_context_get(key: str) -> dict:
    """读取共享上下文（自动过期清理）"""
    entry = _shared_context.get(key)
    if entry is None:
        return {"key": key, "status": "not_found"}
    if time.time() > entry.get("expires", 0):
        _shared_context.pop(key, None)
        return {"key": key, "status": "expired"}
    return {"key": key, "value": entry["value"], "status": "ok"}


def shared_context_list() -> dict:
    """列出所有共享上下文（自动清理过期项）"""
    now = time.time()
    expired = [k for k, v in _shared_context.items() if now > v.get("expires", 0)]
    for k in expired:
        _shared_context.pop(k, None)
    return {"keys": list(_shared_context.keys()), "count": len(_shared_context)}


# ── 知识库搜索 ──────────────────────────────────────────────────────

def kb_search(query: str, limit: int = 5) -> dict:
    """搜索AI知识库 — 查找相关文档、概念、标签

    Args:
        query: 搜索关键词或问题
        limit: 返回结果数量

    Returns:
        {"results": [{title, path, concepts, tags, summary}], "count": N}
    """
    results = _kb_query_sync(query, limit=limit)
    return {
        "results": results,
        "count": len(results),
        "query": query
    }
