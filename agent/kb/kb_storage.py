"""kb_storage.py - Storage abstraction layer for Knowledge Base Manager

Provides config management, index operations, text extraction, and file system
operations via KBStorageMixin.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from i18n import t
from .kb_utils import _get_file_hash, _content_hash, _extract_title


class KBStorageMixin:
    """Mixin: config, index, file extraction, and filesystem operations."""

    # -- Config --

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration file"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "api_key": os.getenv("NVIDIA_API_KEY", ""),
            "base_url": "https://integrate.api.nvidia.com/v1",
            "model": "stepfun-ai/step-3.7-flash",
            "max_tokens": 4096,
            "vault_name": self.vault_path.name
        }

    def _save_config(self):
        """Save configuration file"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def init(self, vault_name: Optional[str] = None):
        """Initialize a new knowledge base"""
        if vault_name:
            self.vault_path = self.vault_path.parent / vault_name
            self.config_path = self.vault_path / "config.json"
            self.__init__(str(self.vault_path))

        print(f"[OK] {t('init.success')}: {self.vault_path}")
        print(f"[DIR] {t('init.vault_path')}: {self.vault_path}")
        api_status = t('init.api_key_set') if self.config.get('api_key') else t('init.api_key_unset')
        print(f"[KEY] API密钥: {api_status}")
        print(f"[URL] API地址: {self.config.get('base_url', 'N/A')}")
        return self._ok({"vault": str(self.vault_path)})

    def config_set(self, key: str, value: str):
        """Set a configuration item"""
        if key == "api-key":
            self.config["api_key"] = value
        elif key == "base-url":
            self.config["base_url"] = value
        else:
            self.config[key] = value
        self._save_config()
        print(f"[OK] {t('config.set')}: {key} = {value}")
        return self._ok({"key": key, "value": value})

    # -- Index --

    def _load_index(self) -> Dict[str, Any]:
        """Load existing index (for link matching)"""
        index_file = self.index_dir / "documents.json"
        if index_file.exists():
            with open(index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"documents": [], "concepts": {}, "entities": {}}

    def _update_index(self, doc_path: Path, metadata: Dict[str, Any]):
        """Update index file"""
        index_file = self.index_dir / "documents.json"

        if index_file.exists():
            with open(index_file, 'r', encoding='utf-8') as f:
                index = json.load(f)
        else:
            index = {"documents": [], "concepts": {}, "entities": {}}

        # Add document record
        doc_record = {
            "path": str(doc_path.relative_to(self.vault_path)),
            "title": metadata.get('title', doc_path.stem),
            "entities": metadata.get('entities', []),
            "concepts": metadata.get('concepts', []),
            "tags": metadata.get('tags', []),
            "created": datetime.now().isoformat()
        }
        index["documents"].append(doc_record)

        # Update concept and entity indexes
        for concept in metadata.get('concepts', []):
            index["concepts"].setdefault(concept, []).append(doc_record["path"])

        for entity in metadata.get('entities', []):
            index["entities"].setdefault(entity, []).append(doc_record["path"])

        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        print(f"[INDEX] {t('index.updated', count=len(index['documents']))}")

    # -- Text extraction --

    def _extract_text(self, filepath: Path) -> str:
        """Extract text content from a file"""
        suffix = filepath.suffix.lower()

        if suffix == '.pdf':
            return self._extract_pdf(filepath)
        elif suffix in ['.docx', '.doc']:
            return self._extract_docx(filepath)
        elif suffix in ['.md', '.markdown']:
            return filepath.read_text(encoding='utf-8')
        elif suffix in ['.txt']:
            return filepath.read_text(encoding='utf-8')
        else:
            raise ValueError(t('error.unsupported_format', format=suffix))

    def _extract_pdf(self, filepath: Path) -> str:
        """Extract PDF text"""
        try:
            import pypdf
            text_parts = []
            with open(filepath, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    text_parts.append(page.extract_text())
            return "\n\n".join(text_parts)
        except ImportError:
            print("请安装: pip install pypdf2")
            raise

    def _extract_docx(self, filepath: Path) -> str:
        """Extract DOCX text"""
        try:
            import docx
            doc = docx.Document(filepath)
            return "\n".join([para.text for para in doc.paragraphs])
        except ImportError:
            print("请安装: pip install python-docx")
            raise

    # -- Markdown generation --

    def _generate_markdown(self, metadata: Dict[str, Any], content: str, source_path: Path,
                           source_label: str = "", file_hash: str = "") -> str:
        """Generate Obsidian-compatible Markdown file (structured breakdown + bidirectional links)"""
        if not file_hash:
            file_hash = _get_file_hash(source_path)
        if not source_label:
            source_label = f"`{source_path.name}`"
        created = datetime.now().strftime("%Y-%m-%d")

        # Structured breakdown section
        breakdown = metadata.get('structured_breakdown', {})
        breakdown_section = ""
        if breakdown:
            code_examples = breakdown.get('code_examples', [])
            code_lines = []
            for c in code_examples:
                code_lines.append("```\n" + c + "\n```")
            code_block = chr(10).join(code_lines) or '暂无'

            scenarios = chr(10).join([f'- {s}' for s in breakdown.get('applicable_scenarios', [])]) or '暂无'
            mistakes = chr(10).join([f'- {m}' for m in breakdown.get('common_mistakes', [])]) or '暂无'

            breakdown_section = f"""
## 结构化拆解

### 核心观点
{breakdown.get('core_idea', '暂无')}

### 详细解释
{breakdown.get('detailed_explanation', '暂无')}

### 代码示例
{code_block}

### 适用场景
{scenarios}

### 常见误区
{mistakes}
"""

        # Missing concepts section
        missing_section = ""
        missing = metadata.get('missing_concepts', [])
        if missing:
            missing_section = f"""
## 相关概念（自动补全）

{chr(10).join([f'- [[{m}]] — 需要补充' for m in missing])}
"""

        # Key points section
        key_points = metadata.get('key_points', [])
        key_points_section = ""
        if key_points:
            key_points_section = f"""
## 核心要点

{chr(10).join([f'- {p}' for p in key_points])}
"""

        markdown = f"""---
title: {metadata.get('title', source_path.stem)}
created: {created}
source: file:///{source_path.resolve().as_posix()}
hash: {file_hash}
tags: {json.dumps(metadata.get('tags', []), ensure_ascii=False)}
entities: {json.dumps(metadata.get('entities', []), ensure_ascii=False)}
category: {metadata.get('category', '其他')}
summary: {metadata.get('summary', '')[:100]}
---

# {metadata.get('title', source_path.stem)}

## 摘要

{metadata.get('summary', '暂无摘要')}
{key_points_section}
## 关键概念

{chr(10).join([f'- [[{c}]]' for c in metadata.get('concepts', [])])}
{breakdown_section}
## 原始内容

{content[:5000]}{'...' if len(content) > 5000 else ''}

## 参考链接

{chr(10).join([f'- [[{l}]]' for l in metadata.get('suggested_links', [])])}
{missing_section}
---

**来源**: {source_label}
**处理时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**文件哈希**: `{file_hash}`
"""
        return markdown
