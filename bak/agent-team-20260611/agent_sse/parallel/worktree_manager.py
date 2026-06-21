"""Git worktree manager for parallel task isolation."""

import asyncio
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class WorktreeManager:
    """Manages git worktrees for parallel task execution.

    Each task gets its own worktree under .worktrees/<task_id>,
    branched from HEAD at creation time, providing full isolation.
    """

    def __init__(self, repo_path: Path, worktrees_dir: str = ".worktrees"):
        self.repo_path = repo_path
        self.worktrees_dir = repo_path / worktrees_dir
        self.worktrees_dir.mkdir(exist_ok=True)

    async def _run_git(self, *args: str, check: bool = True) -> str:
        """Run a git command in the repo root asynchronously."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(self.repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if check and proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed (rc={proc.returncode}): "
                f"{stderr.decode(errors='replace').strip()}"
            )
        return stdout.decode(errors="replace")

    async def get_base_commit(self) -> str:
        """Return the full SHA-1 of HEAD."""
        return (await self._run_git("rev-parse", "HEAD")).strip()

    async def create(self, task_id: str) -> Path:
        """Create a new worktree for the given task_id.

        Branches from HEAD into parallel/<task_id> and checks out
        into .worktrees/<task_id>.
        """
        branch = f"parallel/{task_id}"
        wt_path = self.worktrees_dir / task_id
        await self._run_git("branch", branch, check=False)
        await self._run_git("worktree", "add", str(wt_path), branch, check=True)
        logger.info("Created worktree: %s at %s", task_id, wt_path)
        return wt_path

    async def cleanup(self, task_id: str) -> None:
        """Remove the worktree and its branch for the given task_id."""
        wt_path = self.worktrees_dir / task_id
        if wt_path.exists():
            await self._run_git("worktree", "remove", str(wt_path), "--force", check=False)
        # Delete branch (check=False since branch may not exist)
        branch = f"parallel/{task_id}"
        await self._run_git("branch", "-D", branch, check=False)
        logger.info("Cleaned up worktree + branch: %s", task_id)

    async def list_worktrees(self) -> List[str]:
        """Return task_ids of all worktrees managed by this instance."""
        output = await self._run_git("worktree", "list", "--porcelain")
        task_ids = []
        for line in output.splitlines():
            if line.startswith("worktree "):
                wt_path = Path(line.split(" ", 1)[1])
                if wt_path.parent == self.worktrees_dir:
                    task_ids.append(wt_path.name)
        return task_ids

    async def cleanup_all(self) -> None:
        """Remove all managed worktrees."""
        task_ids = await self.list_worktrees()
        await asyncio.gather(*(self.cleanup(tid) for tid in task_ids))
