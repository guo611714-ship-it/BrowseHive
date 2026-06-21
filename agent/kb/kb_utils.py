"""kb_utils.py - Pure utility functions for Knowledge Base Manager

Provides hashing, tokenization, similarity computation, and response helpers.
No dependencies on other kb_* modules.
"""

import hashlib
import re
from typing import Any, List, Optional

# Re-export unified response helpers from agent.utils
from ..utils import _ok, _err, _warn, _make_response  # noqa: F401


def _get_file_hash(filepath) -> str:
    """Calculate file hash for deduplication"""
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _content_hash(content: str) -> str:
    """Calculate text content hash for deduplication"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:8]


def _extract_title(content: str, fallback: str = "") -> str:
    """Extract # title from content, return fallback if not found"""
    for line in content.split('\n'):
        if line.startswith('# '):
            return line[2:].strip()
    return fallback


def _get_model(config: dict) -> str:
    """Get model name from config (with default)"""
    return config.get("model", "stepfun-ai/step-3.7-flash")


def _tokenize(text: str) -> List[str]:
    """Simple tokenization: split by whitespace+punctuation, lowercase, remove stop words"""
    stop_words = {
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
        '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
        '自己', '这', '他', '她', '它', '们', '那', '这个', '那个', '什么', '怎么',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'can', 'shall', 'to', 'of', 'in', 'for',
        'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
        'before', 'after', 'and', 'but', 'or', 'nor', 'not', 'so', 'yet',
        'both', 'either', 'neither', 'each', 'every', 'all', 'any', 'few',
        'more', 'most', 'other', 'some', 'such', 'no', 'only', 'own', 'same',
        'than', 'too', 'very', 'just', 'because', 'if', 'when', 'while',
    }
    tokens = re.findall(r'[\w一-鿿]+', text.lower())
    return [t for t in tokens if t not in stop_words and len(t) > 1]


def _compute_jaccard(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets"""
    if not set_a and not set_b:
        return 0.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def score_document(query_words: list, doc: dict) -> int:
    """Score a document against query words by keyword matching.

    Shared scoring logic used by approval._kb_query_sync and
    KnowledgeService._search_kb_fallback. Weights: title=3, concepts=2,
    entities=2, tags=1, summary=1.
    """
    score = 0
    title_lower = (doc.get("title") or "").lower()
    concepts_lower = " ".join(doc.get("concepts") or []).lower()
    entities_lower = " ".join(doc.get("entities") or []).lower()
    tags_lower = " ".join(doc.get("tags") or []).lower()
    summary_lower = (doc.get("summary") or "").lower()

    for w in query_words:
        if w in title_lower:
            score += 3
        if w in concepts_lower:
            score += 2
        if w in entities_lower:
            score += 2
        if w in tags_lower:
            score += 1
        if w in summary_lower:
            score += 1
    return score


