"""kb_core.py - Core KnowledgeBaseManager class

Combines all sub-modules via mixin inheritance:
  - KBStorageMixin  (kb_storage): config, index, file extraction, markdown generation
  - KBLlmMixin      (kb_llm):     LLM API calls (analysis, reranking, answer generation)
  - KBCommandsMixin  (kb_commands): all high-level command implementations
"""

from pathlib import Path
from typing import Optional

from .kb_utils import (
    _ok, _err, _warn,
    _get_file_hash as _get_file_hash_fn,
    _content_hash as _content_hash_fn,
    _extract_title as _extract_title_fn,
    _get_model as _get_model_fn,
    _tokenize as _tokenize_fn,
    _compute_jaccard as _compute_jaccard_fn,
    _make_response as _make_response_fn,
)
from .kb_storage import KBStorageMixin
from .kb_llm import KBLlmMixin
from .commands import KBCommandsMixin
from .kb_cache import KBQueryCache


class KnowledgeBaseManager(KBStorageMixin, KBLlmMixin, KBCommandsMixin):
    """Knowledge Base Manager core class -- composed from sub-modules."""

    def __init__(self, vault_path: str, config_path: Optional[str] = None):
        self.vault_path = Path(vault_path).resolve()
        self.config_path = Path(config_path) if config_path else self.vault_path / "config.json"
        self.config = self._load_config()

        # Directory structure
        self.import_dir = self.vault_path / "01-Import"
        self.notes_dir = self.vault_path / "02-Notes"
        self.index_dir = self.vault_path / "03-Index"
        self.processed_dir = self.vault_path.parent / "processed"
        self.log_dir = self.vault_path.parent / "logs"

        # Ensure directories exist
        for d in [self.import_dir, self.notes_dir, self.index_dir, self.processed_dir, self.log_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Two-level cache
        self.cache = KBQueryCache(self.vault_path / ".cache")

    # Re-export response helpers as instance methods for backward compatibility
    def _make_response(self, code, msg, data=None):
        return _make_response_fn(code, msg, data)

    def _ok(self, data=None, msg="success"):
        return _ok(data, msg)

    def _err(self, code, msg):
        return _err(code, msg)

    def _warn(self, msg):
        return _warn(msg)

    # Re-export utils as instance methods for backward compatibility
    # (tests call these as kb._get_file_hash(...), etc.)
    def _get_file_hash(self, filepath):
        return _get_file_hash_fn(filepath)

    def _content_hash(self, content):
        return _content_hash_fn(content)

    def _extract_title(self, content, fallback=""):
        return _extract_title_fn(content, fallback)

    def _tokenize(self, text):
        return _tokenize_fn(text)

    def _compute_jaccard(self, set_a, set_b):
        return _compute_jaccard_fn(set_a, set_b)
