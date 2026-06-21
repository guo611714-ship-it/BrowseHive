import asyncio
import logging
import time
from collections import Counter
from fastapi import APIRouter, HTTPException, Depends
from agent_sse.models.requests import ParallelRequest
from agent_sse.models.responses import ParallelResponse, TaskResult
from agent_sse.dependencies import get_agent_loop
from agent_sse.parallel.worktree_manager import WorktreeManager
from agent_sse.parallel.executor import ParallelExecutor
from agent_sse.parallel.merger import ResultMerger
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["parallel"])


@router.post("/parallel", response_model=ParallelResponse)
async def parallel_execute(request: ParallelRequest, loop=Depends(get_agent_loop)):
    if not loop:
        raise HTTPException(status_code=503, detail="AgentLoop not running")

    start_time = time.time()
    # 使用项目根目录，不依赖进程 CWD
    repo_path = Path(__file__).resolve().parent.parent.parent
    wm = WorktreeManager(repo_path)
    executor = ParallelExecutor(loop)
    merger = ResultMerger(repo_path)

    # Validate no overlapping files (O(n) via Counter)
    all_files = []
    for task in request.tasks:
        all_files.extend(task.files)
    if len(all_files) != len(set(all_files)):
        counts = Counter(all_files)
        overlapping = [f for f, c in counts.items() if c > 1]
        raise HTTPException(status_code=400, detail=f"Overlapping files: {overlapping}")

    # Create worktrees
    task_info = {}
    for task in request.tasks:
        try:
            wt_path = wm.create(task.id)
            task_info[task.id] = {"files": task.files, "worktree": wt_path, "description": task.description}
        except Exception as e:
            for tid in task_info:
                wm.cleanup(tid)
            raise HTTPException(status_code=500, detail=f"Worktree creation failed: {e}")

    # Execute in parallel
    sem = asyncio.Semaphore(request.constraints.max_concurrent)

    async def _run_task(task_id, info):
        async with sem:
            return task_id, await executor.execute_task(
                task_id=task_id, description=info["description"],
                files=info["files"], worktree_path=info["worktree"],
                timeout=request.constraints.timeout_per_task,
            )

    exec_results = await asyncio.gather(
        *[_run_task(tid, info) for tid, info in task_info.items()],
        return_exceptions=True,
    )

    # Process results
    results = []
    conflicts = []
    successful_tasks = {}

    for item in exec_results:
        if isinstance(item, Exception):
            results.append(TaskResult(task_id="unknown", status="failed", error=str(item)))
            continue
        task_id, execution = item
        results.append(TaskResult(
            task_id=task_id, status=execution.status,
            files_changed=execution.files_changed, tests_passed=execution.tests_passed,
            output=execution.output[:500], error=execution.error,
            duration_ms=execution.duration_ms,
        ))
        if execution.status == "success":
            successful_tasks[task_id] = {"files": task_info[task_id]["files"], "worktree": task_info[task_id]["worktree"]}

    if successful_tasks:
        conflicts = merger.detect_conflicts(successful_tasks)

    merged = False
    if not conflicts and not request.constraints.dry_run and successful_tasks:
        merged = merger.merge_file_level(successful_tasks, repo_path)

    wm.cleanup_all()

    from agent_sse.utils.metrics import metrics
    total_ms = int((time.time() - start_time) * 1000)
    await metrics.record_response_time("parallel", total_ms)

    return ParallelResponse(
        ok=True, results=results, conflicts=conflicts,
        merged=merged, total_duration_ms=total_ms,
    )
