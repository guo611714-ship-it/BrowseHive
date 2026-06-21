"""知识库爬虫工具 -- 从 URL 提取内容并导入 Obsidian 知识库"""

import json
import logging
import time
import hashlib
from pathlib import Path
from typing import Dict
from datetime import datetime
from ..config import AI_KB_IMPORT
from ..utils import _ok, _err  # Unified response helpers

logger = logging.getLogger(__name__)

# 知识库导入目录
_KB_IMPORT_DIR = AI_KB_IMPORT


def _generate_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def _format_doc(title: str, content: str, url: str, tags: list, entities: list) -> str:
    """生成 Obsidian Markdown 文档"""
    now = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag_str = json.dumps(tags, ensure_ascii=False) if tags else '["网页内容"]'
    entity_str = json.dumps(entities, ensure_ascii=False) if entities else "[]"

    return f"""---
title: {title}
created: {now}
source: {url}
category: web
tags: {tag_str}
entities: {entity_str}
---

# {title}

## 摘要

{content[:500]}

## 原始内容

{content}

---

**来源**: {url}
**处理时间**: {ts}
"""


async def kb_crawl(url: str, category: str = "web") -> dict:
    """从 URL 提取内容并导入知识库

    Args:
        url: 目标网页 URL
        category: 内容分类，默认 "web"

    Returns:
        dict: {"code": 200, "data": {...}} 或 {"code": ..., "msg": ...}
    """
    t0 = time.time()

    # 1. 从浏览器提取页面内容
    from .browser_tools import get_page_text
    text_result = await get_page_text(max_length=15000)
    if text_result.get("code") != 200:
        return _err(500, f"页面提取失败: {text_result.get('msg')}")

    raw_content = text_result.get("data", {}).get("content", "")
    if not raw_content.strip():
        return _err(422, "页面内容为空")

    # 2. 分析内容（简单提取式分析）
    title = raw_content[:60].split("\n")[0].strip()
    if len(title) > 50:
        title = title[:50] + "..."

    # 从内容中提取关键词作为标签
    tags = [category]
    keywords = ["AI", "Python", "JavaScript", "LLM", "RAG", "Agent", "API"]
    content_lower = raw_content.lower()
    tags.extend(kw for kw in keywords if kw.lower() in content_lower)
    tags = tags[:6]  # 最多6个标签

    # 提取实体
    entities = []
    entity_patterns = ["OpenAI", "Google", "Microsoft", "Anthropic", "Meta", "NVIDIA"]
    entities.extend(e for e in entity_patterns if e in raw_content)
    entities = entities[:5]

    # 3. 生成并保存文档
    url_hash = _generate_hash(url)
    doc_title = f"{url_hash}-{title}"
    filename = f"{doc_title}.md"
    save_path = _KB_IMPORT_DIR / filename

    _KB_IMPORT_DIR.mkdir(parents=True, exist_ok=True)

    doc_content = _format_doc(title, raw_content, url, tags, entities)
    save_path.write_text(doc_content, encoding="utf-8")

    cost = int((time.time() - t0) * 1000)
    logger.info("kb_crawl done: %s (%d ms)", filename, cost)

    return _ok({
        "title": title,
        "file": str(save_path),
        "filename": filename,
        "hash": url_hash,
        "tags": tags,
        "entities": entities,
        "content_length": len(raw_content),
        "cost_time": cost,
    }, msg=f"已导入: {title}")
