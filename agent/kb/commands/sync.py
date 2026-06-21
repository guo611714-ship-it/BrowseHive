"""sync.py - Synchronization mixins."""

import time
from pathlib import Path

from i18n import t
from ..kb_utils import _content_hash, _extract_title
import logging

logger = logging.getLogger(__name__)


class SyncMixin:
    """Mixin: synchronization commands."""

    def sync_memory_to_kb(self, memory_dir: str):
        """Memory -> KB sync: scan Memory knowledge base, sync new content to Obsidian"""
        memory_path = Path(memory_dir)
        if not memory_path.exists():
            print(f"[ERR] {t('error.memory_dir_not_found', path=memory_path)}")
            return

        print(f"[SYNC] {t('kb_sync.syncing')}")
        synced = 0
        skipped = 0

        for md_file in memory_path.rglob("*.md"):
            rel = md_file.relative_to(memory_path)
            if rel.parts[0] != "knowledge":
                continue
            if md_file.name in ("INDEX.md", "kb-sync-index.md"):
                continue

            content = md_file.read_text(encoding='utf-8')
            content_hash = _content_hash(content)
            existing = list(self.import_dir.glob(f"*{content_hash}*.md"))
            if existing:
                skipped += 1
                continue

            title = _extract_title(content, md_file.stem)

            rel = md_file.relative_to(memory_path)
            category = rel.parts[0] if len(rel.parts) > 1 else "其他"

            try:
                self.analyze_text(content, title, category)
                synced += 1
                time.sleep(1)
            except Exception as e:
                print(f"[WARN]  跳过 {md_file.name}: {e}")

        print(f"\n[OK] {t('sync.done')}: +{synced}, {t('kb_sync.skipped')} {skipped}")

    def sync_kb_to_memory_index(self, memory_dir: str):
        """KB -> Memory sync: sync KB index to Memory INDEX.md"""
        memory_path = Path(memory_dir)
        index = self._load_index()
        if not index["documents"]:
            print(f"[ERR] {t('kb_index.index_missing')}")
            return

        categories = {}
        for doc in index["documents"]:
            cat = doc.get("tags", ["其他"])[0] if doc.get("tags") else "其他"
            categories.setdefault(cat, []).append(doc)

        lines = ["# KB Manager 知识索引\n"]
        lines.append(f"> 自动同步自 AI知识库，共 {len(index['documents'])} 篇文档\n")
        for cat, docs in sorted(categories.items()):
            lines.append(f"\n## {cat}\n")
            for doc in docs:
                lines.append(f"- {doc['title']}")

        kb_index = memory_path / "kb-sync-index.md"
        kb_index.write_text("\n".join(lines), encoding='utf-8')
        print(f"[OK] {t('kb_index.synced')}: {kb_index}")

    def rebuild_memory_index(self, memory_dir: str):
        """Auto-rebuild Memory knowledge base INDEX.md"""
        memory_path = Path(memory_dir)
        knowledge_path = memory_path / "knowledge"
        if not knowledge_path.exists():
            print(f"[ERR] {t('error.file_not_found', path=knowledge_path)}")
            return

        print(f"[SYNC] {t('kb_index.rebuilding')}")

        categories = {}
        for md_file in sorted(knowledge_path.rglob("*.md")):
            if md_file.name == "INDEX.md":
                continue
            rel = md_file.relative_to(knowledge_path)
            category = rel.parts[0] if len(rel.parts) > 1 else "其他"

            title = md_file.stem
            description = ""
            try:
                content = md_file.read_text(encoding='utf-8')
                for line in content.split('\n'):
                    if line.startswith('# ') and title == md_file.stem:
                        title = line[2:].strip()
                    if line.startswith('description:'):
                        description = line.split(':', 1)[1].strip()
            except Exception as e:
                logger.debug("caught exception: %s", e)

            slug = str(rel.with_suffix('')).replace('\\', '/')
            categories.setdefault(category, []).append({
                "slug": slug,
                "title": title,
                "description": description
            })

        lines = ["# 知识库索引\n"]
        category_names = {
            "ai": "AI",
            "programming": "编程",
            "domain": "领域知识",
            "tools": "工具",
            "references": "参考资料"
        }
        for cat, items in sorted(categories.items()):
            cat_name = category_names.get(cat, cat)
            lines.append(f"\n## {cat_name}\n")
            for item in items:
                desc = f" -- {item['description']}" if item['description'] else ""
                lines.append(f"- [[{item['slug']}]] -- {item['title']}{desc}")

        index_path = knowledge_path / "INDEX.md"
        index_path.write_text("\n".join(lines), encoding='utf-8')
        print(f"[OK] {t('kb_index.rebuilt')}: {index_path}")
        print(f"   分类: {len(categories)}, 知识条目: {sum(len(v) for v in categories.values())}")
