import shutil
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    merged: bool = False
    conflicts: List[str] = field(default_factory=list)
    files_copied: List[str] = field(default_factory=list)
    error: Optional[str] = None


class ResultMerger:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def detect_conflicts(self, task_results: Dict[str, Any]) -> List[str]:
        file_owners: Dict[str, List[str]] = {}
        for task_id, info in task_results.items():
            for f in info.get("files", []):
                file_owners.setdefault(f, []).append(task_id)
        conflicts = []
        for f, owners in file_owners.items():
            if len(owners) > 1:
                conflicts.append(f)
                logger.warning("Conflict detected: %s modified by %s", f, owners)
        return conflicts

    @staticmethod
    def _is_safe_path(base: Path, target: Path) -> bool:
        """Check that target is within base directory (prevent path traversal)."""
        try:
            target.resolve().relative_to(base.resolve())
            return True
        except ValueError:
            return False

    def merge_file_level(self, task_results: Dict[str, Any], dest_path: Path) -> bool:
        try:
            for task_id, info in task_results.items():
                src_wt = info["worktree"]
                for f in info.get("files", []):
                    # Path traversal防护
                    if ".." in f or f.startswith("/"):
                        logger.warning("Skipped unsafe path: %s from %s", f, task_id)
                        continue
                    src_file = src_wt / f
                    dest_file = dest_path / f
                    if not self._is_safe_path(src_wt, src_file) or not self._is_safe_path(dest_path, dest_file):
                        logger.warning("Skipped path traversal attempt: %s", f)
                        continue
                    if src_file.exists():
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(src_file), str(dest_file))
                        logger.info("Merged %s from %s", f, task_id)
            return True
        except Exception as e:
            logger.error("Merge failed: %s", e)
            return False

    def rollback(self, dest_path: Path, original_files: Dict[str, str]) -> None:
        for f, content in original_files.items():
            target = dest_path / f
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            logger.info("Rolled back %s", f)
