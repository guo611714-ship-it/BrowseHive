"""Knowledge Base package - structured knowledge management with Obsidian integration."""

from .kb_core import KnowledgeBaseManager
from .kb_utils import _extract_title, _get_file_hash, _content_hash, score_document
from .kb_storage import KBStorageMixin
from .kb_llm import KBLlmMixin
from .kb_cache import KBQueryCache
from .kb_setup import SetupWizard
from .commands import KBCommandsMixin

__all__ = [
    "KnowledgeBaseManager",
    "KBCommandsMixin",
    "KBStorageMixin",
    "KBLlmMixin",
    "KBQueryCache",
    "SetupWizard",
    "_extract_title",
    "_get_file_hash",
    "_content_hash",
    "score_document",
]
