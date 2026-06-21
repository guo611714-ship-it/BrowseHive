"""ParallelExecutor - runs sub-agent tasks in isolated worktrees with timeout control."""

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskExecution:
    task_id: str
    description: str
    files: List[str]
    worktree_path: Path
    status: str = "pending"
    output: str = ""
    error: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)
    tests_passed: Optional[bool] = None
    duration_ms: int = 0


class ParallelExecutor:
    """Executes agent tasks in isolated worktrees with timeout enforcement."""

    def __init__(self, agent_loop: Any):
        self.agent_loop = agent_loop

    async def execute_task(
        self,
        task_id: str,
        description: str,
        files: List[str],
        worktree_path: Path,
        timeout: int = 120,
    ) -> TaskExecution:
        """Run a single task through the agent loop with a timeout."""
        execution = TaskExecution(
            task_id=task_id,
            description=description,
            files=files,
            worktree_path=worktree_path,
            status="running",
        )
        start = time.time()
        try:
            message = self._build_task_message(description, files, worktree_path)
            result = await asyncio.wait_for(
                self.agent_loop.process_message(message),
                timeout=timeout,
            )
            execution.output = result or ""
            execution.status = "success"
            execution.files_changed = await self._detect_changed_files(worktree_path)
        except asyncio.TimeoutError:
            execution.status = "timeout"
            execution.error = f"Task timed out after {timeout}s"
        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)
        finally:
            execution.duration_ms = int((time.time() - start) * 1000)
        return execution

    def _build_task_message(
        self, description: str, files: List[str], worktree_path: Path
    ) -> str:
        """Construct the prompt message sent to the agent loop."""
        file_list = ", ".join(files)
        return (
            f"你在独立工作区中执行任务。工作区路径: {worktree_path}\n\n"
            f"任务: {description}\n"
            f"允许修改的文件: {file_list}\n"
            f"约束: 只能修改上述文件，不能修改其他文件。"
        )

    async def _detect_changed_files(self, worktree_path: Path) -> List[str]:
        """Detect files changed in the worktree via git diff (non-blocking)."""
        import functools
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                functools.partial(
                    subprocess.run,
                    ["git", "diff", "--name-only"],
                    cwd=str(worktree_path),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            )
            return [f for f in result.stdout.strip().splitlines() if f]
        except Exception:
            return []
