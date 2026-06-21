"""classify.py - Auto-classification and category management mixins."""

import json
import re
import logging

from i18n import t
from ..kb_utils import _tokenize, _compute_jaccard

logger = logging.getLogger(__name__)


class ClassifyMixin:
    """Mixin: auto-classification and category management commands."""

    def auto_classify(self, content: str, title: str) -> str:
        """Auto-classify content by similarity to existing categories"""
        index = self._load_index()
        if not index.get("documents"):
            return "其他"

        text_tokens = set(_tokenize(title + " " + content[:3000]))

        category_tokens = {}
        for doc in index["documents"]:
            doc_cat = doc.get("tags", ["其他"])[0] if doc.get("tags") else "其他"
            doc_text = " ".join([
                doc.get("title", ""),
                " ".join(doc.get("concepts", [])),
                " ".join(doc.get("entities", [])),
                " ".join(doc.get("tags", [])),
                doc.get("summary", ""),
            ])
            tokens = set(_tokenize(doc_text))
            category_tokens.setdefault(doc_cat, set()).update(tokens)

        if not category_tokens:
            return "其他"

        scores = {}
        for cat, cat_toks in category_tokens.items():
            scores[cat] = _compute_jaccard(text_tokens, cat_toks)

        best_cat = max(scores, key=scores.get)
        best_score = scores[best_cat]

        if best_score > 0.7:
            print(f"[CLASSIFY] matched: {best_cat} (score={best_score:.2f})")
            return best_cat
        elif best_score >= 0.4:
            print(f"[WARN] candidate: {best_cat} (score={best_score:.2f}) -- confirm?")
            return f"候选:{best_cat}"
        else:
            hint = _tokenize(title)
            candidate = hint[0] if hint else "未分类"
            print(f"[CLASSIFY] new category candidate: {candidate} (best={best_cat}, score={best_score:.2f})")
            return f"新分类:{candidate}"

    def discover_categories(self) -> dict:
        """Scan all documents and discover potential new categories"""
        cat_docs = {}
        for md_file in self.import_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding='utf-8')
            except Exception as e:
                logger.debug("Read failed for %s: %s", md_file, e)
                continue

            category = "其他"
            in_frontmatter = False
            for line in content.split('\n')[:20]:
                if line.strip() == '---':
                    in_frontmatter = not in_frontmatter
                    continue
                if in_frontmatter and line.lower().startswith('category:'):
                    category = line.split(':', 1)[1].strip()
                    break

            if category == "其他":
                tag_match = re.search(r'tags:\s*\[([^\]]+)\]', content[:500])
                if tag_match:
                    tags = [t_.strip().strip('"').strip("'") for t_ in tag_match.group(1).split(',')]
                    if tags:
                        category = tags[0]

            cat_docs.setdefault(category, []).append(md_file.name)

        existing = []
        candidates = []
        recommended = []

        for cat, docs in sorted(cat_docs.items(), key=lambda x: -len(x[1])):
            entry = {"category": cat, "count": len(docs), "samples": docs[:3]}
            if cat == "其他":
                existing.append(entry)
            elif len(docs) >= 3:
                recommended.append(entry)
                existing.append(entry)
            else:
                candidates.append(entry)

        result = {
            "existing": existing,
            "candidates": candidates,
            "recommended": recommended,
            "total_files": sum(len(d) for d in cat_docs.values()),
        }

        print(f"\n[DISCOVER] category scan ({result['total_files']} files):")
        print("=" * 60)
        if recommended:
            print("\n  [REC] recommended (>=3 docs, create正式分类):")
            for r in recommended:
                print(f"    - {r['category']}: {r['count']} docs")
        if candidates:
            print("\n  [CAND] candidates (<3 docs):")
            for c in candidates:
                print(f"    - {c['category']}: {c['count']} docs")
        if existing:
            print("\n  [EXISTS] existing categories:")
            for e in existing:
                print(f"    - {e['category']}: {e['count']} docs")

        return result

    def merge_categories(self, source: str, target: str):
        """Merge two categories: move all source documents to target"""
        updated_files = 0

        for md_file in self.import_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding='utf-8')
            except Exception as e:
                logger.debug("Read failed for %s: %s", md_file, e)
                continue

            if f"category: {source}" not in content and f'category: "{source}"' not in content:
                continue

            safe_target = re.escape(target)
            new_content = re.sub(
                r'(category:\s*)["\']?' + re.escape(source) + r'["\']?',
                lambda m: m.group(1) + safe_target,
                content,
                count=1,
                flags=re.IGNORECASE
            )

            if new_content != content:
                md_file.write_text(new_content, encoding='utf-8')
                updated_files += 1
                print(f"[MERGE] {md_file.name}: {source} -> {target}")

        # Update documents.json
        index = self._load_index()
        for doc in index.get("documents", []):
            tags = doc.get("tags", [])
            if source in tags:
                tags[tags.index(source)] = target
                doc["tags"] = tags

        index_file = self.index_dir / "documents.json"
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        if source in index.get("concepts", {}):
            existing_docs = index["concepts"].pop(source, [])
            index["concepts"].setdefault(target, []).extend(existing_docs)

        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        print(f"\n[OK] merge complete: {source} -> {target} ({updated_files} files updated)")
        return self._ok({"updated_files": updated_files, "source": source, "target": target})
