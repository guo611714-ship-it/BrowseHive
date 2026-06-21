"""Unified Knowledge Service -- single interface for Agent Team sub-agents.

Provides three layers:
    1. Memory  -- MEMORY.md index + per-topic .md files
    2. Knowledge Base -- documents.json indexed KB (optional)
    3. Task context -- auto-composed from both

Zero external dependencies. Graceful degradation when KB is unavailable.
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MEMORY_INDEX_FILENAME = "MEMORY.md"
_KB_INDEX_FILENAME = "documents.json"
_KB_SEARCH_LIMIT = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_kebab(name: str) -> str:
    """Convert a human-readable name to kebab-case for filenames.

    Chinese characters are preserved; whitespace and punctuation are
    replaced with hyphens.  Runs of hyphens are collapsed.
    Appends a short hash to avoid collisions.
    """
    s = name.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^\w-]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    base = s.strip("-") or "untitled"
    h = hashlib.md5(name.encode()).hexdigest()[:6]
    return f"{base}-{h}"


def _parse_memory_index(index_path: Path) -> List[Dict[str, str]]:
    """Parse MEMORY.md into a list of entries.

    Expected line format:
        - [Title](file.md) -- description
    """
    entries: List[Dict[str, str]] = []
    if not index_path.exists():
        return entries

    try:
        content = index_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return entries

    for line in content.splitlines():
        m = re.match(
            r"^- \[([^\]]+)\]\(([^)]+)\)\s*[—-]+\s*(.+)$",
            line.strip(),
        )
        if m:
            entries.append({
                "name": m.group(1),
                "file": m.group(2),
                "description": m.group(3).strip(),
            })
    return entries


def _build_memory_entry(name: str, description: str, content: str) -> str:
    """Render a memory file with YAML-ish front-matter + body."""
    now = datetime.now().strftime("%Y-%m-%d")
    return (
        f"---\n"
        f"title: {name}\n"
        f"date: {now}\n"
        f"description: {description}\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"{content.strip()}\n"
    )


def _strip_front_matter(text: str) -> str:
    """Remove leading YAML front-matter block (--- ... ---)."""
    return re.sub(r"^---\n.*?\n---\n*", "", text, flags=re.DOTALL).strip()


# ---------------------------------------------------------------------------
# KnowledgeService
# ---------------------------------------------------------------------------

class KnowledgeService:
    """Unified knowledge layer for Agent Team sub-agents.

    Automatically locates memory and (optionally) KB directories by
    probing well-known paths.  If the KB is not found the service still
    works for all memory operations.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()

        # -- Memory paths --
        # Primary : ~/.claude/projects/<project-slug>/memory/
        # Fallback: <project_root>/memory/
        # Claude Code uses <drive>--<path-with-dashes> as project slug.
        # e.g. D:\Users\lenovo\Desktop\claude workspace -> d--Users-lenovo-Desktop-claude-workspace
        p = self.project_root.resolve()
        drive = p.drive.lower().rstrip(":")  # 'd'
        rest = str(p)[len(p.drive):].lstrip("\\")  # '\Users\...' -> 'Users\...'
        slug = drive + "--" + rest.replace("\\", "-").replace("/", "-").replace(" ", "-")
        self.memory_dir = Path.home() / ".claude" / "projects" / slug / "memory"
        if not self.memory_dir.exists():
            self.memory_dir = self.project_root / "memory"
        self.memory_index = self.memory_dir / _MEMORY_INDEX_FILENAME

        # -- KB paths (optional) --
        self.kb_index_dir: Optional[Path] = None
        self._kb_commands_instance: Any = None
        self._detect_kb()

    # ------------------------------------------------------------------
    # KB detection (internal)
    # ------------------------------------------------------------------

    def _detect_kb(self) -> None:
        """Probe common locations for a KB index and build a minimal
        KBCommandsMixin-compatible instance for querying."""
        candidates = [
            self.project_root / "knowledge" / "index",
            self.memory_dir / "knowledge",
            self.project_root / "kb",
        ]
        for candidate in candidates:
            if (candidate / _KB_INDEX_FILENAME).exists():
                self.kb_index_dir = candidate
                break

        if self.kb_index_dir is None:
            return

        try:
            from .kb import KBCommandsMixin  # type: ignore[import-untyped]

            class _MiniKB(KBCommandsMixin):
                """Minimal shell exposing index_dir + vault_path + _load_index."""

                def __init__(self, idx_dir: Path):
                    self.index_dir = idx_dir
                    self.vault_path = idx_dir
                    self.config: Dict[str, Any] = {}

                def _load_index(self) -> Dict[str, Any]:
                    fp = self.index_dir / _KB_INDEX_FILENAME
                    if not fp.exists():
                        return {"documents": []}
                    import json as _json
                    with open(fp, "r", encoding="utf-8") as fh:
                        return _json.load(fh)

                def _ok(self, data: Any, **kw: Any) -> Any:
                    return {"ok": True, "data": data, **kw}

                def _err(self, code: int, msg: str) -> Any:
                    return {"ok": False, "error": code, "message": msg}

            self._kb_commands_instance = _MiniKB(self.kb_index_dir)
        except ImportError:
            # kb_commands unavailable -- degrade gracefully
            self._kb_commands_instance = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_path(self, base: Path, file_ref: str) -> Optional[Path]:
        """Safe path join that prevents directory traversal."""
        target = (base / file_ref).resolve()
        if not target.is_relative_to(base.resolve()):
            return None
        return target

    # ------------------------------------------------------------------
    # 1. Read Memory
    # ------------------------------------------------------------------

    def read_memory(
        self,
        keyword: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, str]]:
        """Read project memory entries indexed by MEMORY.md.

        Args:
            keyword: Filter by keyword (case-insensitive match on name
                     and description).
            limit:   Maximum entries to return.

        Returns:
            List of {"name", "description", "content"} dicts.
        """
        entries = _parse_memory_index(self.memory_index)

        if keyword:
            kw = keyword.lower()
            entries = [
                e for e in entries
                if kw in e["name"].lower() or kw in e["description"].lower()
            ]

        results: List[Dict[str, str]] = []
        for entry in entries[:limit]:
            file_path = self._safe_path(self.memory_dir, entry["file"])
            if file_path is None:
                continue  # skip unsafe paths
            content = ""
            if file_path.exists():
                raw = file_path.read_text(encoding="utf-8")
                content = _strip_front_matter(raw)
            results.append({
                "name": entry["name"],
                "description": entry["description"],
                "content": content,
            })

        return results

    # ------------------------------------------------------------------
    # 2. Write Memory
    # ------------------------------------------------------------------

    def write_memory(
        self,
        name: str,
        content: str,
        description: str = "",
    ) -> bool:
        """Write a memory entry and append it to the MEMORY.md index.

        Args:
            name:        Human-readable title (used for index + filename).
            content:     Markdown body.
            description: One-line summary shown in MEMORY.md.

        Returns:
            True on success, False on failure.
        """
        if not description:
            description = content[:120].split("\n")[0].strip()

        filename = _to_kebab(name) + ".md"
        file_path = self.memory_dir / filename

        # Ensure directory exists
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Write file with front-matter
        try:
            file_path.write_text(
                _build_memory_entry(name, description, content),
                encoding="utf-8",
            )
        except OSError:
            return False

        # Update MEMORY.md index
        index_line = f"- [{name}]({filename}) — {description}"
        if self.memory_index.exists():
            existing = self.memory_index.read_text(encoding="utf-8")
            # Skip duplicate
            if f"]({filename})" in existing:
                return True
            if existing.rstrip():
                existing = existing.rstrip("\n") + "\n"
            updated = existing + index_line + "\n"
        else:
            updated = f"# Memory Index\n\n{index_line}\n"

        try:
            self.memory_index.write_text(updated, encoding="utf-8")
        except OSError:
            return False

        return True

    # ------------------------------------------------------------------
    # 3. Search Knowledge Base
    # ------------------------------------------------------------------

    def search_kb(
        self,
        query: str,
        limit: int = _KB_SEARCH_LIMIT,
    ) -> List[Dict[str, Any]]:
        """Search the structured knowledge base.

        Returns the real engine results when available; otherwise falls
        back to a lightweight local text scan over documents.json.

        Returns:
            List of {"title", "content", "score"} dicts.
        """
        if self._kb_commands_instance is not None:
            return self._search_kb_engine(query, limit)
        return self._search_kb_fallback(query, limit)

    def _search_kb_engine(
        self, query: str, limit: int,
    ) -> List[Dict[str, Any]]:
        """Use KBCommandsMixin.query for an authoritative search."""
        try:
            raw = self._kb_commands_instance.query(
                query, limit=limit, rerank=False,
            )
            docs = raw.get("data", []) if isinstance(raw, dict) else []
            results: List[Dict[str, Any]] = []
            for item in docs:
                doc = item.get("doc", {})
                doc_path = self._safe_path(self.kb_index_dir, doc.get("path", ""))
                text = ""
                if doc_path is not None and doc_path.exists():
                    text = doc_path.read_text(encoding="utf-8")[:2000]
                results.append({
                    "title": doc.get("title", ""),
                    "content": text or doc.get("summary", ""),
                    "score": item.get("score", 0),
                })
            return results
        except Exception as e:
            logger.debug("caught exception: %s", e)
            return []

    def _search_kb_fallback(
        self, query: str, limit: int,
    ) -> List[Dict[str, Any]]:
        """Lightweight local scan when the KB engine is not importable."""
        if self.kb_index_dir is None:
            return []

        import json as _json

        index_file = self.kb_index_dir / _KB_INDEX_FILENAME
        if not index_file.exists():
            return []

        try:
            with open(index_file, "r", encoding="utf-8") as fh:
                index = _json.load(fh)
        except (OSError, _json.JSONDecodeError):
            return []

        query_words = query.lower().split()
        scored: List[Dict[str, Any]] = []

        for doc in index.get("documents", []):
            from .kb.kb_utils import score_document
            score = score_document(query_words, doc)

            if score > 0:
                doc_path = self._safe_path(self.kb_index_dir, doc.get("path", ""))
                content = ""
                if doc_path is not None and doc_path.exists():
                    content = doc_path.read_text(encoding="utf-8")[:2000]
                scored.append({
                    "title": doc.get("title", ""),
                    "content": content or doc.get("summary", ""),
                    "score": score,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------------
    # 4. Get Context for Task
    # ------------------------------------------------------------------

    def get_context_for_task(self, task_description: str) -> str:
        """Compose a context string for an Agent Team task.

        Searches memory first, then KB, and merges the results into a
        single formatted document suitable for system_prompt injection.
        """
        parts: List[str] = []

        # --- Memory ---
        mem_results = self.read_memory(keyword=task_description, limit=3)
        if mem_results:
            mem_section = "\n\n".join(
                f"### {m['name']}\n{m['description']}\n\n{m['content'][:500]}"
                for m in mem_results
                if m["content"]
            )
            if mem_section:
                parts.append(f"## Project Memory\n\n{mem_section}")

        # --- Knowledge Base ---
        kb_results = self.search_kb(task_description, limit=3)
        if kb_results:
            kb_section = "\n\n".join(
                f"### {k['title']} (relevance: {k['score']})\n{k['content'][:500]}"
                for k in kb_results
            )
            if kb_section:
                parts.append(f"## Knowledge Base\n\n{kb_section}")

        if not parts:
            return ""

        header = f"## Context for: {task_description}\n"
        return header + "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # 5. Save Task Result
    # ------------------------------------------------------------------

    def save_task_result(
        self,
        task_id: str,
        result: str,
        learnings: str = "",
    ) -> bool:
        """Persist a task outcome as a memory entry.

        The entry name is derived from *task_id*.  If *learnings* is
        provided they are appended as a separate section.

        Returns:
            True on success, False on failure.
        """
        parts = [f"Task ID: {task_id}\n", f"Result:\n{result}"]
        if learnings:
            parts.append(f"Learnings:\n{learnings}")

        body = "\n\n".join(parts)
        name = f"Task Result: {task_id}"
        description = f"Outcome of task {task_id}"

        return self.write_memory(name=name, content=body, description=description)
