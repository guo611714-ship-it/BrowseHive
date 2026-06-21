"""query.py - Query and unified search mixins."""

from pathlib import Path
from typing import Optional

from i18n import t
from ..kb_utils import _extract_title
import logging

logger = logging.getLogger(__name__)


class QueryMixin:
    """Mixin: query and unified search commands."""

    def query(self, question: str, limit: int = 5, rerank: bool = True):
        """Query knowledge base (hybrid matching + AI rerank + two-level cache)"""
        # Check cache
        cache_key_suffix = f"limit={limit}"
        cached = self.cache.get(question, cache_key_suffix)
        if cached is not None:
            print("[CACHE] L1/L2 hit, returning cached result")
            return cached

        index = self._load_index()
        if not index["documents"]:
            print(f"[ERR] {t('error.index_missing')}")
            return self._err(400, t('error.index_missing'))

        question_lower = question.lower()
        question_words = question_lower.split()
        relevant_docs = []

        for doc in index["documents"]:
            score = 0
            # Title matching (highest weight)
            title_lower = doc.get('title', '').lower()
            for word in question_words:
                if word in title_lower:
                    score += 3
            # Concept matching
            concepts_lower = " ".join(doc.get('concepts', [])).lower()
            for word in question_words:
                if word in concepts_lower:
                    score += 2
            # Entity matching
            entities_lower = " ".join(doc.get('entities', [])).lower()
            for word in question_words:
                if word in entities_lower:
                    score += 2
            # Tag matching
            tags_lower = " ".join(doc.get('tags', [])).lower()
            for word in question_words:
                if word in tags_lower:
                    score += 1
            # Summary matching
            summary_lower = doc.get('summary', '').lower()
            for word in question_words:
                if word in summary_lower:
                    score += 1

            if score > 0:
                relevant_docs.append({"score": score, "doc": doc})

        # Sort by score, take top candidates
        relevant_docs.sort(key=lambda x: x["score"], reverse=True)
        candidates = relevant_docs[:limit * 2]

        if not candidates:
            print(f"[NONE] {t('query.none')}")
            return self._ok([], msg=t('query.none'))

        # AI rerank (free API, direct call)
        if rerank and self.config.get("api_key") and len(candidates) > 1:
            try:
                candidates = self._rerank(question, candidates, limit)
            except Exception as e:
                print(f"[WARN]  {t('rerank.failed')}: {e}")
                candidates = candidates[:limit]
        else:
            candidates = candidates[:limit]

        print(f"\n[SEARCH] {t('query.found', count=len(candidates))}:")
        print("=" * 80)

        contexts = []
        for item in candidates:
            doc = item["doc"]
            doc_path = self.vault_path / doc['path']
            if doc_path.exists():
                content = doc_path.read_text(encoding='utf-8')[:2000]
                contexts.append(f"文档: {doc['title']}\n内容: {content}\n")
                print(f"* {doc['title']} (相关度: {item['score']})")

        # Use LLM API to generate answer
        if self.config.get("api_key"):
            print(f"\n[AI] {t('query.ai_generating')}")
            answer = self._generate_answer(question, contexts)
            print("\n" + "=" * 80)
            print(f"{t('query.answer')}:")
            print(answer)
        else:
            print(f"\n[TIP] {t('tip.set_api')}")

        # Write to cache
        self.cache.put(question, cache_key_suffix, candidates)
        return self._ok(candidates)

    def unified_search(self, question: str, limit: int = 5, memory_dir: Optional[str] = None):
        """Unified search: search both Memory and KB Manager, merge results"""
        print(f"[SEARCH] {question}")
        print("=" * 80)

        results = []

        # 1. Search KB Manager
        index = self._load_index()
        question_words = question.lower().split()

        if index["documents"]:
            for doc in index["documents"]:
                score = 0
                all_text = " ".join([
                    doc.get('title', ''),
                    " ".join(doc.get('concepts', [])),
                    " ".join(doc.get('entities', [])),
                    " ".join(doc.get('tags', [])),
                    doc.get('summary', '')
                ]).lower()
                for word in question_words:
                    if word in all_text:
                        score += 1
                if score > 0:
                    results.append({"source": "KB", "title": doc["title"], "score": score, "path": doc["path"]})

        # 2. Search Memory knowledge base
        if memory_dir:
            memory_knowledge = Path(memory_dir) / "knowledge"
        else:
            memory_knowledge = Path.home() / ".claude" / "projects" / "d--Users-lenovo-Desktop-claude-workspace" / "memory" / "knowledge"
        if memory_knowledge.exists():
            for md_file in memory_knowledge.rglob("*.md"):
                if md_file.name == "INDEX.md":
                    continue
                try:
                    content = md_file.read_text(encoding='utf-8')[:2000]
                    content_lower = content.lower()
                    score = 0
                    for word in question_words:
                        if word in content_lower:
                            score += 1
                    if score > 0:
                        title = _extract_title(content, md_file.stem)
                        results.append({"source": "Memory", "title": title, "score": score, "path": str(md_file)})
                except Exception as e:
                    logger.debug("caught exception, continuing: %s", e)
                    continue

        # Sort
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:limit]

        if not results:
            print(f"[NONE] {t('unified.none')}")
            return results

        print(f"\n[KB] {t('unified.found', count=len(results))}:")
        for r in results:
            icon = "[KB]" if r["source"] == "KB" else "[MEM]"
            print(f"  {icon} [{r['source']}] {r['title']} (相关度: {r['score']})")

        # AI answer
        if self.config.get("api_key"):
            contexts = []
            for r in results:
                try:
                    if r["source"] == "KB":
                        content = (self.vault_path / r["path"]).read_text(encoding='utf-8')[:1500]
                    else:
                        content = Path(r["path"]).read_text(encoding='utf-8')[:1500]
                    contexts.append(f"[{r['source']}] {r['title']}\n{content}")
                except Exception as e:
                    logger.debug("caught exception, continuing: %s", e)
                    continue

            if contexts:
                print(f"\n[AI] {t('query.ai_generating')}")
                answer = self._generate_answer(question, contexts)
                print("\n" + "=" * 80)
                print(f"{t('query.answer')}:")
                print(answer)

        return results
