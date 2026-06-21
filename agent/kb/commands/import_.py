"""import_.py - Document import and text analysis mixins."""

import time
from pathlib import Path
from typing import Optional

from i18n import t
from ..kb_utils import _get_file_hash, _content_hash, _extract_title


class ImportMixin:
    """Mixin: document import and text analysis commands."""

    def import_document(self, filepath: str, category: Optional[str] = None):
        """Import a document into the knowledge base"""
        source = Path(filepath).resolve()

        if not source.exists():
            print(f"[ERR] {t('error.file_not_found', path=source)}")
            return

        # Check for duplicates
        file_hash = _get_file_hash(source)
        existing = list(self.import_dir.glob(f"*{file_hash}*.md"))
        if existing:
            print(f"[WARN]  {t('import.exists')}: {source.name} -> {existing[0].name}")
            return

        print(f"[IMPORT] {t('import.start')}: {source.name}")

        try:
            # Extract text
            print(f"   {t('extracting_text')}")
            content = self._extract_text(source)

            # Load existing index for link matching
            existing_index = self._load_index()

            # AI analysis (auto-classify + bidirectional links)
            print(f"   {t('analyzing_ai')}")
            metadata = self._analyze_with_claude(content, source.name, existing_index)

            # Generate Markdown
            print(f"   {t('generating_markdown')}")
            markdown = self._generate_markdown(metadata, content, source)

            # Save file
            safe_title = metadata.get('title', source.stem)
            safe_title = "".join(c for c in safe_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"{_get_file_hash(source)[:8]}-{safe_title[:50]}.md"
            output_path = self.import_dir / filename

            output_path.write_text(markdown, encoding='utf-8')
            print(f"[OK] {t('import.done')}: {output_path.name}")

            # Copy to processed directory
            processed_path = self.processed_dir / source.name
            import shutil
            shutil.copy2(source, processed_path)

            # Update index
            self._update_index(output_path, metadata)

            # Invalidate cache after import
            self.cache.invalidate()

        except Exception as e:
            print(f"[ERR] {t('import.failed')}: {e}")
            import traceback
            traceback.print_exc()

    def batch_import(self, folder: str, category: str = "其他", to_memory: bool = False):
        """Batch import all supported files from a folder (with real-time progress)"""
        folder_path = Path(folder).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            print(f"[ERR] {t('error.folder_not_found', path=folder_path)}")
            return

        supported = {'.md', '.txt', '.pdf', '.docx', '.doc'}
        files = [f for f in folder_path.rglob("*") if f.suffix.lower() in supported and f.is_file()]

        if not files:
            print(f"[NONE] 文件夹中没有支持的文件（支持: {', '.join(supported)}）")
            return

        total = len(files)
        print(f"[IMPORT] {t('batch.importing')}: {folder_path}")
        print(f"   {t('batch.total', count=total)}")
        print("=" * 80)

        imported = 0
        skipped = 0
        failed = 0

        # Memory knowledge base path
        memory_knowledge = None
        if to_memory:
            memory_knowledge = Path.home() / ".claude" / "projects" / "d--Users-lenovo-Desktop-claude-workspace" / "memory" / "knowledge"

        for i, f in enumerate(files, 1):
            # -- Progress bar (Task 3) --
            pct = i / total * 100
            filled = int(pct // 2)
            bar = "=" * filled + ">" + " " * (50 - filled)
            name_display = f.name[:30]
            print(f"\r[{bar}] {pct:5.1f}% ({i}/{total}) {name_display:<30s}", end="", flush=True)
            print()  # newline after progress line

            # Read content
            try:
                if f.suffix.lower() in ('.md', '.txt'):
                    content = f.read_text(encoding='utf-8')
                else:
                    content = self._extract_text(f)
            except Exception as e:
                print(f"   [ERR] 读取失败: {e}")
                failed += 1
                continue

            # Content dedup
            content_hash = _content_hash(content)
            existing = list(self.import_dir.glob(f"*{content_hash}*.md"))
            if existing:
                print(f"   [SKIP]  {t('batch.skipped')}")
                skipped += 1
                continue

            # Extract title
            title = _extract_title(content, f.stem)

            # Infer category from directory name or content
            rel = f.relative_to(folder_path)
            inferred_category = rel.parts[0] if len(rel.parts) > 1 else category

            # AI analysis + generate Obsidian page
            try:
                self.analyze_text(content, title, inferred_category)
                imported += 1
            except Exception as e:
                print(f"   [WARN]  分析失败: {e}")
                failed += 1
                continue

            # Optional: also write to Memory
            if memory_knowledge:
                cat_dir = memory_knowledge / inferred_category
                cat_dir.mkdir(parents=True, exist_ok=True)
                slug = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(' ', '-')[:50]
                mem_file = cat_dir / f"{slug}.md"
                if not mem_file.exists():
                    mem_file.write_text(f"# {title}\n\n{content[:3000]}", encoding='utf-8')
                    print(f"   [MEM] 已写入 Memory: {mem_file.name}")

            time.sleep(1)  # Rate limiting

        # Final summary with full progress bar
        print()
        bar_done = "=" * 51
        print(f"[{bar_done}] 100.0% DONE")
        print(f"[OK] {t('batch.done')}: +{imported}, skip {skipped}, -{failed}")

    def analyze_text(self, text: str, title: str = "untitled", category: str = "其他"):
        """Analyze text content and generate Obsidian page (auto-classify + links + breakdown)"""
        print(f"[MEM] {t('mem.analyzing')}: {title}")

        # Content dedup check
        content_hash = _content_hash(text)
        existing = list(self.import_dir.glob(f"*{content_hash[:8]}*.md"))
        if existing:
            print(f"[WARN]  {t('mem.exists')}: {existing[0].name}")
            return str(existing[0])

        # Load existing index for link matching
        existing_index = self._load_index()

        try:
            metadata = self._analyze_with_claude(text, title, existing_index)
        except Exception as e:
            print(f"[WARN]  {t('mem.ai_failed')}: {e}")
            metadata = {
                "title": title,
                "summary": text[:200],
                "concepts": [],
                "entities": [],
                "tags": [],
                "suggested_links": [],
                "category": category,
                "key_points": [],
                "structured_breakdown": {},
                "missing_concepts": []
            }

        # Generate markdown (reuse _generate_markdown)
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
        filename = f"{content_hash[:8]}-{safe_title}.md"
        output_path = self.import_dir / filename

        markdown = self._generate_markdown(metadata, text, output_path,
                                           source_label="/learn auto-generated",
                                           file_hash=content_hash[:8])

        output_path.write_text(markdown, encoding='utf-8')
        self._update_index(output_path, metadata)

        # Invalidate cache after analysis
        self.cache.invalidate()
        print(f"   概念: {', '.join(metadata.get('concepts', [])[:5])}")
        print(f"   实体: {', '.join(metadata.get('entities', [])[:5])}")
        print(f"   链接: {', '.join(metadata.get('suggested_links', [])[:3])}")
        return str(output_path)
