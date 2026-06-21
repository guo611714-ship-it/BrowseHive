"""Lightweight internationalization module for Knowledge Base Manager."""

import json
import os
from pathlib import Path
from typing import Dict

_I18N_DIR = Path(__file__).parent / "locales"
_DEFAULT_LANG = "zh"

_ZH_MESSAGES = {
    "init.success": "知识库已初始化",
    "init.vault_path": "Vault路径",
    "init.api_key_set": "API密钥已设置",
    "init.api_key_unset": "未设置",
    "import.start": "正在导入",
    "import.done": "导入完成",
    "import.exists": "文件已导入过",
    "import.failed": "导入失败",
    "query.found": "找到 {count} 个相关文档",
    "query.none": "未找到相关文档",
    "query.answer": "回答",
    "query.ai_generating": "正在生成回答...",
    "list.title": "知识库文档",
    "list.empty": "知识库为空或未建立索引",
    "graph.done": "知识图谱已生成",
    "backup.done": "知识库已备份",
    "backup.nothing": "知识库无变更",
    "sync.start": "同步开始",
    "sync.done": "同步完成",
    "cache.hit": "缓存命中",
    "cache.miss": "缓存未命中",
    "error.file_not_found": "文件不存在: {path}",
    "error.unsupported_format": "不支持的文件类型: {format}",
    "error.api_key_missing": "未设置api_key",
    "error.index_missing": "知识库未建立索引，请先导入文档",
    "error.folder_not_found": "文件夹不存在: {path}",
    "error.memory_dir_not_found": "Memory 目录不存在: {path}",
    "version.list": "版本历史",
    "version.diff": "版本差异",
    "version.rollback": "已回滚到版本 {rev}",
    "version.no_git": "Vault未初始化git仓库",
    "version.no_commits": "没有提交历史",
    "version.no_changes": "版本间无差异",
    "version.rebuild_index": "正在重建索引...",
    "config.set": "已设置",
    "batch.total": "找到 {count} 个文件",
    "batch.done": "批量导入完成",
    "batch.skipped": "已存在，跳过",
    "batch.importing": "批量导入",
    "mem.analyzing": "正在深度分析",
    "mem.exists": "内容已存在",
    "mem.ai_failed": "AI分析失败，使用基础元数据",
    "mem.done": "深度分析完成",
    "unified.found": "找到 {count} 条结果",
    "unified.none": "未找到相关内容",
    "kb_sync.syncing": "同步 Memory -> KB Manager...",
    "kb_sync.done": "同步完成",
    "kb_sync.skipped": "跳过",
    "kb_index.synced": "索引已同步到",
    "kb_index.rebuilding": "重建 Memory 知识索引...",
    "kb_index.rebuilt": "索引已重建",
    "kb_index.index_missing": "KB 索引不存在",
    "bye": "已取消",
    "error.generic": "错误",
    "tip.set_api": "设置API密钥后可获得AI生成的回答",
    "extracting_text": "extracting text...",
    "analyzing_ai": "analyzing with AI (auto-classify + link matching)...",
    "generating_markdown": "generating markdown...",
    "index.updated": "索引已更新: {count} 个文档",
    "rerank.failed": "重排序失败，使用关键词排序",
}

_EN_MESSAGES = {
    "init.success": "Knowledge base initialized",
    "init.vault_path": "Vault path",
    "init.api_key_set": "API key set",
    "init.api_key_unset": "Not set",
    "import.start": "Importing",
    "import.done": "Import complete",
    "import.exists": "File already imported",
    "import.failed": "Import failed",
    "query.found": "Found {count} relevant documents",
    "query.none": "No relevant documents found",
    "query.answer": "Answer",
    "query.ai_generating": "Generating answer...",
    "list.title": "Knowledge base documents",
    "list.empty": "Knowledge base is empty or not indexed",
    "graph.done": "Knowledge graph generated",
    "backup.done": "Knowledge base backed up",
    "backup.nothing": "No changes to backup",
    "sync.start": "Sync started",
    "sync.done": "Sync complete",
    "cache.hit": "Cache hit",
    "cache.miss": "Cache miss",
    "error.file_not_found": "File not found: {path}",
    "error.unsupported_format": "Unsupported file type: {format}",
    "error.api_key_missing": "api_key not set",
    "error.index_missing": "Knowledge base not indexed, please import documents first",
    "error.folder_not_found": "Folder not found: {path}",
    "error.memory_dir_not_found": "Memory directory not found: {path}",
    "version.list": "Version history",
    "version.diff": "Version diff",
    "version.rollback": "Rolled back to version {rev}",
    "version.no_git": "Vault has no git repository",
    "version.no_commits": "No commit history",
    "version.no_changes": "No changes between versions",
    "version.rebuild_index": "Rebuilding index...",
    "config.set": "Config set",
    "batch.total": "Found {count} files",
    "batch.done": "Batch import complete",
    "batch.skipped": "Already exists, skipped",
    "batch.importing": "Batch import",
    "mem.analyzing": "Analyzing in depth",
    "mem.exists": "Content already exists",
    "mem.ai_failed": "AI analysis failed, using basic metadata",
    "mem.done": "Deep analysis complete",
    "unified.found": "Found {count} results",
    "unified.none": "No relevant content found",
    "kb_sync.syncing": "Syncing Memory -> KB Manager...",
    "kb_sync.done": "Sync complete",
    "kb_sync.skipped": "Skipped",
    "kb_index.synced": "Index synced to",
    "kb_index.rebuilding": "Rebuilding Memory knowledge index...",
    "kb_index.rebuilt": "Index rebuilt",
    "kb_index.index_missing": "KB index not found",
    "bye": "Cancelled",
    "error.generic": "Error",
    "tip.set_api": "Set API key to get AI-generated answers",
    "extracting_text": "extracting text...",
    "analyzing_ai": "analyzing with AI (auto-classify + link matching)...",
    "generating_markdown": "generating markdown...",
    "index.updated": "Index updated: {count} documents",
    "rerank.failed": "Rerank failed, using keyword ranking",
}


class I18n:
    """Lightweight i18n with env detection and custom locale files."""

    def __init__(self, lang: str = None):
        self.lang = lang or self._detect_lang()
        self.messages = self._load_messages()

    def _detect_lang(self) -> str:
        env_lang = os.getenv("KB_LANG")
        if env_lang:
            return env_lang
        system_lang = os.getenv("LANG", os.getenv("LANGUAGE", ""))
        if system_lang.startswith("zh"):
            return "zh"
        return _DEFAULT_LANG

    def _load_messages(self) -> Dict[str, str]:
        if self.lang == "zh":
            messages = _ZH_MESSAGES.copy()
        else:
            messages = _EN_MESSAGES.copy()

        custom_file = _I18N_DIR / f"{self.lang}.json"
        if custom_file.exists():
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    messages.update(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass

        return messages

    def t(self, key: str, **kwargs) -> str:
        text = self.messages.get(key, key)
        if kwargs:
            text = text.format(**kwargs)
        return text


_i18n = None


def get_i18n(lang: str = None) -> I18n:
    global _i18n
    if _i18n is None or (lang and lang != _i18n.lang):
        _i18n = I18n(lang)
    return _i18n


def t(key: str, **kwargs) -> str:
    return get_i18n().t(key, **kwargs)
