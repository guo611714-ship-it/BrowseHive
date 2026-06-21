"""Performance benchmark tests for the fix engine pipeline.

Measures wall-clock time for core operations to catch performance regressions.
Thresholds are intentionally generous (2-3x expected) to avoid flaky tests
on slow CI runners.
"""

import time
import pytest

from agent.engine.manifest import (
    TaskManifest, FixTask, SmartSharder, TaskPriority, SchedulingStrategy,
)
from agent.engine.conflict import ConflictPredictor
from agent.engine.scheduler import ResultAggregator


def _make_task(task_id: int, files: list[str] | None = None) -> FixTask:
    """Create a minimal FixTask for benchmarking."""
    return FixTask(
        task_id=f"bench-{task_id}",
        description=f"Benchmark task {task_id}",
        files=files or [f"src/module_{task_id % 10}.py"],
        priority=TaskPriority.NORMAL,
    )


# ============================================================
# 1. SmartSharder — 100 tasks
# ============================================================

def test_sharder_speed():
    """Shard 100 tasks in under 100ms."""
    sharder = SmartSharder()
    tasks = [_make_task(i) for i in range(100)]
    manifest = TaskManifest(tasks=tasks, strategy=SchedulingStrategy.AUTO)

    start = time.perf_counter()
    shards = sharder.shard(manifest)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"\n  SmartSharder: 100 tasks -> {len(shards)} shards in {elapsed_ms:.1f}ms")
    assert elapsed_ms < 100, f"Sharding took {elapsed_ms:.1f}ms, expected < 100ms"


# ============================================================
# 2. ConflictPredictor — 50 task pairs
# ============================================================

def test_conflict_predictor_speed():
    """Predict conflicts for 50 tasks in under 50ms."""
    predictor = ConflictPredictor()
    tasks = [_make_task(i) for i in range(50)]

    start = time.perf_counter()
    groups = predictor.predict_conflicts(tasks)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"\n  ConflictPredictor: 50 tasks -> {len(groups)} groups in {elapsed_ms:.1f}ms")
    assert elapsed_ms < 50, f"Prediction took {elapsed_ms:.1f}ms, expected < 50ms"


# ============================================================
# 3. TaskManifest creation — 1000 objects
# ============================================================

def test_manifest_creation_speed():
    """Create 1000 TaskManifest objects in under 100ms."""
    start = time.perf_counter()
    manifests = []
    for i in range(1000):
        manifests.append(
            TaskManifest(
                tasks=[_make_task(i)],
                strategy=SchedulingStrategy.AUTO,
                max_concurrent=3,
            )
        )
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"\n  TaskManifest creation: 1000 objects in {elapsed_ms:.1f}ms")
    assert len(manifests) == 1000
    assert elapsed_ms < 100, f"Creation took {elapsed_ms:.1f}ms, expected < 100ms"


# ============================================================
# 4. ResultAggregator — 100 results
# ============================================================

def test_aggregator_speed():
    """Aggregate 100 mock results in under 50ms."""
    results = [
        {
            "task_id": f"bench-{i}",
            "status": "completed",
            "files_modified": [f"src/module_{i % 10}.py"],
            "changes": [{"type": "replace", "old": "a", "new": "b"}],
        }
        for i in range(100)
    ]

    start = time.perf_counter()
    aggregated = ResultAggregator.aggregate(results)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"\n  ResultAggregator: 100 results in {elapsed_ms:.1f}ms")
    assert "merged_files" in aggregated
    assert elapsed_ms < 50, f"Aggregation took {elapsed_ms:.1f}ms, expected < 50ms"


# ============================================================
# 5. Full pipeline (mocked dispatch) — 50 tasks
# ============================================================

def test_full_pipeline_mock_speed():
    """Full pipeline with mocked dispatch: shard -> predict -> aggregate, 50 tasks in under 500ms."""
    sharder = SmartSharder()
    predictor = ConflictPredictor()
    tasks = [_make_task(i) for i in range(50)]
    manifest = TaskManifest(tasks=tasks, strategy=SchedulingStrategy.AUTO)

    start = time.perf_counter()

    # Step 1: shard
    shards = sharder.shard(manifest)

    # Step 2: predict conflicts
    flat_tasks = [t for s in shards for t in s.tasks]
    groups = predictor.predict_conflicts(flat_tasks)

    # Step 3: mock aggregated results (one per task)
    mock_results = [
        {"task_id": t.task_id, "status": "completed", "files_modified": t.files, "changes": []}
        for t in flat_tasks
    ]
    aggregated = ResultAggregator.aggregate(mock_results)

    elapsed_ms = (time.perf_counter() - start) * 1000

    print(
        f"\n  Full pipeline: {len(tasks)} tasks -> {len(shards)} shards, "
        f"{len(groups)} conflict groups, {len(aggregated.get('merged_files', {}))} merged files "
        f"in {elapsed_ms:.1f}ms"
    )
    assert elapsed_ms < 500, f"Full pipeline took {elapsed_ms:.1f}ms, expected < 500ms"
