"""Three-Way Merge -- backward-compatible re-export from scheduler module."""

from .scheduler import (
    ThreeWayMerge,
    MergeResult,
    ConflictMarker,
    _lcs_lines,
    _backtrack,
    _compute_diff_hunks,
    integrate_with_scheduler,
)
from .utils import git_show as _git_show

__all__ = [
    "ThreeWayMerge",
    "MergeResult",
    "ConflictMarker",
    "_lcs_lines",
    "_backtrack",
    "_compute_diff_hunks",
    "integrate_with_scheduler",
    "_git_show",
]
