"""End-to-end integration tests for Parallel Fix Engine.

Exercises the full pipeline: TaskManifest -> Shard -> Schedule -> Aggregate
with mocked dispatch (no real LLM calls).
"""

import asyncio

import pytest
from unittest.mock import patch

from agent.engine.fix_engine import ParallelFixEngine, quick_fix
from agent.engine.manifest import (
    FixTask,
    SchedulingStrategy,
    TaskManifest,
)
from agent.engine.scheduler import EnhancedScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUCCESS_RESULT = {
    "status": "success",
    "summary": "fixed",
    "agent_type": "neiguan_yingzao",
}


def _run(coro):
    """Run an async coroutine from a synchronous test."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _mock_schedule(self, manifest):
    """Replacement for EnhancedScheduler.schedule — returns mock results.

    Patching a class attribute with an async function still triggers Python's
    descriptor protocol, so ``self`` is auto-injected and the coroutine
    returned must be ``await``-ed (matching the original ``async def``).
    """
    from agent.engine.manifest import SmartSharder, SchedulingStrategy
    from agent.engine.conflict import ConflictPredictor

    sharder = SmartSharder(predictor=ConflictPredictor())
    shards = sharder.shard(manifest)

    results = []
    for shard in shards:
        for task in shard.tasks:
            result = dict(SUCCESS_RESULT)
            result.update(task.to_dispatch_args())
            result["output"] = f"mock output for {task.task_id}"
            results.append(result)

    return {
        "status": "success",
        "shards": shards,
        "results": results,
        "stats": {
            "total_shards": len(shards),
            "completed_shards": len(shards),
            "total_tasks": manifest.task_count,
            "completed_tasks": manifest.task_count,
            "failed_tasks": 0,
            "serial_tasks": 0,
            "parallel_tasks": manifest.task_count,
        },
        "failed_items": [],
    }


# ============================================================
# 1. Single task – full pipeline end-to-end
# ============================================================


def test_full_pipeline_single_task():
    with patch.object(EnhancedScheduler, "schedule", _mock_schedule):
        engine = ParallelFixEngine()
        manifest = TaskManifest(
            tasks=[FixTask(task_id="t1", description="fix x", files=["a.py"])]
        )
        result = _run(engine.submit(manifest))

    assert result["status"] == "success"
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "success"
    assert "shards" in result and result["shards"]
    assert "merged" in result
    assert result["stats"]["total_tasks"] == 1


# ============================================================
# 2. Parallel tasks – 5 tasks on different files
# ============================================================


def test_full_pipeline_parallel_tasks():
    with patch.object(EnhancedScheduler, "schedule", _mock_schedule):
        engine = ParallelFixEngine()
        tasks = [
            FixTask(task_id=f"t{i}", description=f"fix {i}", files=[f"file_{i}.py"])
            for i in range(5)
        ]
        manifest = TaskManifest(tasks=tasks)
        result = _run(engine.submit(manifest))

    assert result["status"] == "success"
    assert len(result["results"]) == 5
    assert result["stats"]["completed_tasks"] == 5
    assert result["stats"]["failed_tasks"] == 0
    assert len(result["shards"]) >= 1


# ============================================================
# 3. Same-file tasks forced SERIAL strategy
# ============================================================


def test_full_pipeline_same_file_serial():
    tasks = [
        FixTask(task_id=f"t{i}", description=f"fix {i}", files=["shared.py"])
        for i in range(3)
    ]
    manifest = TaskManifest(tasks=tasks, strategy=SchedulingStrategy.SERIAL)
    engine = ParallelFixEngine()
    plan = engine.analyze(manifest)

    assert len(plan["shards"]) == 3
    assert plan["execution_plan"]["strategy"] == "serial"


# ============================================================
# 4. Mixed parallel + serial (depends_on forces ordering)
# ============================================================


def test_full_pipeline_mixed():
    with patch.object(EnhancedScheduler, "schedule", _mock_schedule):
        tasks = [
            FixTask(task_id="a", description="fix a", files=["a.py"]),
            FixTask(task_id="b", description="fix b", files=["b.py"]),
            FixTask(task_id="c", description="fix c", files=["c.py"], depends_on=["a"]),
            FixTask(task_id="d", description="fix d", files=["d.py"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        engine = ParallelFixEngine()
        plan = engine.analyze(manifest)

    order = []
    for shard in plan["shards"]:
        order.extend(shard["tasks"])
    assert "a" in order
    assert "c" in order
    assert order.index("a") < order.index("c")


# ============================================================
# 5. quick_fix() API – one-liner
# ============================================================


def test_quick_fix_api():
    import agent.engine.fix_engine as fe

    fe._engine = None  # reset singleton
    try:
        with patch.object(EnhancedScheduler, "schedule", _mock_schedule):
            result = _run(quick_fix([dict(task_id="qf1", description="quick", files=["x.py"])]))
        assert result["status"] == "success"
        assert len(result["results"]) == 1
    finally:
        fe._engine = None


# ============================================================
# 6. analyze() only – no scheduling / aggregation
# ============================================================


def test_analyze_only():
    with patch.object(EnhancedScheduler, "schedule") as mock_sched:
        engine = ParallelFixEngine()
        manifest = TaskManifest(
            tasks=[
                FixTask(task_id="x", description="x", files=["x.py"]),
                FixTask(task_id="y", description="y", files=["y.py"]),
            ]
        )
        plan = engine.analyze(manifest)

    assert "manifest_summary" in plan
    assert "shards" in plan
    assert plan["execution_plan"]["total_shards"] >= 1
    mock_sched.assert_not_called()


# ============================================================
# 7. Empty manifest – edge case
# ============================================================


def test_empty_manifest():
    engine = ParallelFixEngine()
    result = _run(engine.submit(TaskManifest(tasks=[])))

    assert result["status"] == "empty"
    assert result["message"] == "No tasks to execute"


# ============================================================
# 8. Partial failure – one fails, others succeed
# ============================================================


async def _failing_schedule(self, manifest):
    from agent.engine.manifest import SmartSharder
    from agent.engine.conflict import ConflictPredictor

    shards = SmartSharder(predictor=ConflictPredictor()).shard(manifest)

    results = []
    for task in manifest.tasks:
        if task.task_id == "bad":
            r = {
                "status": "failed",
                "summary": "boom",
                "agent_type": task.agent_type,
            }
        else:
            r = {**SUCCESS_RESULT, "output": f"ok {task.task_id}"}
        results.append(r)

    failed_count = sum(1 for r in results if r["status"] != "success")
    return {
        "status": "partial",
        "shards": shards,
        "results": results,
        "stats": {
            "total_shards": len(shards),
            "completed_shards": len(shards),
            "total_tasks": manifest.task_count,
            "completed_tasks": manifest.task_count - failed_count,
            "failed_tasks": failed_count,
            "serial_tasks": 0,
            "parallel_tasks": manifest.task_count,
        },
        "failed_items": [r for r in results if r["status"] != "success"],
    }


def test_failed_task_partial_success():
    with patch.object(EnhancedScheduler, "schedule", _failing_schedule):
        engine = ParallelFixEngine()
        manifest = TaskManifest(
            tasks=[
                FixTask(task_id="good1", description="g1", files=["a.py"]),
                FixTask(task_id="bad", description="will fail", files=["b.py"]),
                FixTask(task_id="good2", description="g2", files=["c.py"]),
            ]
        )
        result = _run(engine.submit(manifest))

    assert result["status"] == "partial"
    assert result["stats"]["failed_tasks"] == 1
    assert result["stats"]["completed_tasks"] == 2
    assert len(result["failed_items"]) == 1


# ============================================================
# 9. Dependency chain – ordering verification
# ============================================================


def test_dependency_chain():
    with patch.object(EnhancedScheduler, "schedule", _mock_schedule):
        tasks = [
            FixTask(task_id="s1", description="1st", files=["a.py"]),
            FixTask(task_id="s2", description="2nd", files=["b.py"], depends_on=["s1"]),
            FixTask(task_id="s3", description="3rd", files=["c.py"], depends_on=["s2"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        engine = ParallelFixEngine()
        plan = engine.analyze(manifest)

    flat_ids = [t for s in plan["shards"] for t in s["tasks"]]
    assert flat_ids.index("s1") < flat_ids.index("s2")
    assert flat_ids.index("s2") < flat_ids.index("s3")


# ============================================================
# 10. max_concurrent limit surfaced in the plan
# ============================================================


def test_max_concurrent_limit():
    with patch.object(EnhancedScheduler, "schedule", _mock_schedule):
        engine = ParallelFixEngine()
        tasks = [
            FixTask(task_id=f"t{i}", description=str(i), files=[f"f{i}.py"])
            for i in range(10)
        ]
        manifest = TaskManifest(tasks=tasks, max_concurrent=3)
        plan = engine.analyze(manifest)

    assert plan["execution_plan"]["max_concurrent"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
