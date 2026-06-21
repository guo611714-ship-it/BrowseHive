"""version.py - Version management and git operations mixins."""

import json
import subprocess
from pathlib import Path
from typing import List

from i18n import t
from ..kb_utils import _extract_title


class VersionMixin:
    """Mixin: version management and git operations commands."""

    def _git_run(self, args: List[str], check: bool = False) -> subprocess.CompletedProcess:
        """Run a git command in the vault directory."""
        return subprocess.run(
            ["git"] + args,
            cwd=str(self.vault_path),
            capture_output=True,
            text=True,
            check=check,
        )

    def _is_git_repo(self) -> bool:
        r = self._git_run(["rev-parse", "--is-inside-work-tree"])
        return r.returncode == 0 and r.stdout.strip() == "true"

    def version_list(self, doc_path: str, limit: int = 20):
        """List git history for a document"""
        if not self._is_git_repo():
            print(f"[WARN]  {t('version.no_git')}")
            return []

        vault_rel = str(Path(doc_path).resolve().relative_to(self.vault_path))
        r = self._git_run(["log", f"--max-count={limit}", "--format=%h|%ai|%s", "--", vault_rel])

        if r.returncode != 0 or not r.stdout.strip():
            print(f"[INFO]  {t('version.no_commits')}")
            return []

        lines = r.stdout.strip().splitlines()
        print(f"\n[VERSION] {t('version.list')}: {vault_rel}")
        print("=" * 80)
        for line in lines:
            parts = line.split("|", 2)
            if len(parts) == 3:
                hash_short, date_str, message = parts
                print(f"  {hash_short}  {date_str[:19]}  {message}")
        print("=" * 80)
        print(f"  total: {len(lines)}")
        return lines

    def version_diff(self, doc_path: str, rev1: str, rev2: str = "HEAD"):
        """Compare two versions of a document"""
        if not self._is_git_repo():
            print(f"[WARN]  {t('version.no_git')}")
            return ""

        vault_rel = str(Path(doc_path).resolve().relative_to(self.vault_path))
        r = self._git_run(["diff", rev1, rev2, "--", vault_rel])

        if r.returncode != 0:
            print(f"[ERR] git diff failed: {r.stderr.strip()}")
            return ""

        if not r.stdout.strip():
            print(f"[INFO]  {t('version.no_changes')}")
            return ""

        print(f"\n[VERSION] {t('version.diff')}: {vault_rel}")
        print(f"  {rev1} -> {rev2}")
        print("=" * 80)
        added = deleted = modified = 0
        for line in r.stdout.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                deleted += 1
            else:
                modified += 1
            print(line)
        print("=" * 80)
        print(f"  +{added} -{deleted} ~{modified}")
        return r.stdout

    def version_rollback(self, doc_path: str, rev: str):
        """Roll back a document to a specific version"""
        if not self._is_git_repo():
            print(f"[WARN]  {t('version.no_git')}")
            return False

        try:
            vault_rel = str(Path(doc_path).resolve().relative_to(self.vault_path))
        except ValueError:
            print(f"[ERR] 路径不在知识库内: {doc_path}")
            return False

        r = self._git_run(["checkout", rev, "--", vault_rel])

        if r.returncode != 0:
            print(f"[ERR] git checkout failed: {r.stderr.strip()}")
            return False

        print(f"[OK] {t('version.rollback', rev=rev)}: {vault_rel}")

        # Rebuild index for this document
        print(f"[INFO]  {t('version.rebuild_index')}")
        try:
            full_path = self.vault_path / vault_rel
            content = full_path.read_text(encoding="utf-8")
            title = _extract_title(content, full_path.stem)
            metadata = self._load_index()
            for doc in metadata.get("documents", []):
                if doc["path"] == vault_rel:
                    doc["title"] = title
                    break
            index_file = self.index_dir / "documents.json"
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN]  index rebuild skipped: {e}")

        return True
