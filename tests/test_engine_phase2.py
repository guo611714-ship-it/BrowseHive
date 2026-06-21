"""Phase 2 测试 — TaskQueue + ProgressBroadcaster + EngineService"""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.engine.manifest import FixTask, TaskManifest, TaskPriority
from agent.engine.task_queue import TaskQueue, TaskEntry, TaskStatus
from agent.engine.progress_sse import ProgressBroadcaster, SSEEvent


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TaskQueue 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTaskQueue:
    def test_empty_queue(self):
        q = TaskQueue()
        assert q.pending_count == 0
        assert q.running_count == 0
        assert q.stats["total"] == 0

    @pytest.mark.asyncio
    async def test_submit(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        manifest_id = await q.submit(m)
        assert manifest_id.startswith("m-")
        assert q.pending_count == 1

    @pytest.mark.asyncio
    async def test_submit_multiple(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix a", files=["a.py"]),
            FixTask(task_id="t2", description="fix b", files=["b.py"]),
            FixTask(task_id="t3", description="fix c", files=["c.py"]),
        ])
        manifest_id = await q.submit(m)
        assert q.pending_count == 3
        entries = q.get_manifest_entries(manifest_id)
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_next_batch(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
            FixTask(task_id="t2", description="fix", files=["b.py"]),
        ])
        await q.submit(m)
        batch = await q.next_batch(batch_size=2)
        assert len(batch) == 2
        # next_batch 从队列取出但不改状态，需 mark_running 才会变为 RUNNING
        # 队列为空但 entries 仍为 PENDING
        assert q.pending_count == 2  # 状态未变

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="low", description="low", files=["a.py"],
                    priority=TaskPriority.LOW),
            FixTask(task_id="critical", description="crit", files=["b.py"],
                    priority=TaskPriority.CRITICAL),
            FixTask(task_id="normal", description="norm", files=["c.py"],
                    priority=TaskPriority.NORMAL),
        ])
        await q.submit(m)
        batch = await q.next_batch(batch_size=3)
        # Critical should come first
        assert batch[0].task.task_id == "critical"

    @pytest.mark.asyncio
    async def test_mark_running(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        await q.submit(m)
        batch = await q.next_batch()
        await q.mark_running(batch[0].entry_id)
        assert q.running_count == 1
        assert batch[0].status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_mark_completed(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        await q.submit(m)
        batch = await q.next_batch()
        await q.mark_completed(batch[0].entry_id, {"status": "ok"})
        assert q.running_count == 0
        assert batch[0].status == TaskStatus.COMPLETED
        assert batch[0].result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_mark_failed(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        await q.submit(m)
        batch = await q.next_batch()
        await q.mark_failed(batch[0].entry_id, "timeout")
        assert batch[0].status == TaskStatus.FAILED
        assert batch[0].error == "timeout"

    @pytest.mark.asyncio
    async def test_cancel(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        await q.submit(m)
        batch = await q.next_batch()
        cancelled = await q.cancel(batch[0].entry_id)
        assert cancelled is True
        assert batch[0].status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_running_fails(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        await q.submit(m)
        batch = await q.next_batch()
        await q.mark_running(batch[0].entry_id)
        cancelled = await q.cancel(batch[0].entry_id)
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_cancel_manifest(self):
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
            FixTask(task_id="t2", description="fix", files=["b.py"]),
        ])
        manifest_id = await q.submit(m)
        cancelled = await q.cancel_manifest(manifest_id)
        assert cancelled == 2

    def test_stats(self):
        q = TaskQueue()
        stats = q.stats
        assert "total" in stats
        assert stats["total"] == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ProgressBroadcaster 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestProgressBroadcaster:
    def test_create(self):
        b = ProgressBroadcaster()
        assert b.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_subscribe(self):
        b = ProgressBroadcaster()
        queue = await b.subscribe("manifest-1")
        assert b.subscriber_count == 1
        await b.unsubscribe(queue, "manifest-1")
        assert b.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_subscribe_global(self):
        b = ProgressBroadcaster()
        queue = await b.subscribe()  # global
        assert b.subscriber_count == 1
        await b.unsubscribe(queue)
        assert b.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_publish_receives(self):
        b = ProgressBroadcaster()
        queue = await b.subscribe("m1")
        event = SSEEvent(event="progress", data={"msg": "hello"})
        b.publish("m1", event)
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.event == "progress"
        assert received.data["msg"] == "hello"

    @pytest.mark.asyncio
    async def test_publish_wrong_manifest(self):
        b = ProgressBroadcaster()
        queue = await b.subscribe("m1")
        event = SSEEvent(event="progress", data={"msg": "hello"})
        b.publish("m2", event)  # different manifest
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_publish_progress(self):
        b = ProgressBroadcaster()
        queue = await b.subscribe("m1")
        b.publish_progress("m1", shard_id=1, total_shards=3,
                          message="running", status="running")
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.data["shard_id"] == 1
        assert received.data["total_shards"] == 3

    @pytest.mark.asyncio
    async def test_publish_complete(self):
        b = ProgressBroadcaster()
        queue = await b.subscribe("m1")
        b.publish_complete("m1", {"status": "success"})
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.event == "complete"

    @pytest.mark.asyncio
    async def test_publish_error(self):
        b = ProgressBroadcaster()
        queue = await b.subscribe("m1")
        b.publish_error("m1", "something went wrong")
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.event == "error"
        assert received.data["error"] == "something went wrong"

    def test_sse_format(self):
        event = SSEEvent(event="test", data={"key": "value"}, id="123")
        formatted = event.format()
        assert "id: 123" in formatted
        assert "event: test" in formatted
        assert "data:" in formatted


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TaskEntry 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTaskEntry:
    def test_to_dict(self):
        task = FixTask(task_id="t1", description="fix", files=["a.py"])
        entry = TaskEntry(
            entry_id="e1", manifest_id="m1", task=task,
        )
        d = entry.to_dict()
        assert d["entry_id"] == "e1"
        assert d["task_id"] == "t1"
        assert d["status"] == "pending"
        assert d["files"] == ["a.py"]

    def test_elapsed_not_started(self):
        task = FixTask(task_id="t1", description="fix", files=["a.py"])
        entry = TaskEntry(entry_id="e1", manifest_id="m1", task=task)
        assert entry.elapsed == 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EngineService 集成测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestEngineService:
    @pytest.mark.asyncio
    async def test_analyze(self):
        from agent.engine.service import EngineService
        service = EngineService()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix a", files=["a.py"]),
            FixTask(task_id="t2", description="fix b", files=["b.py"]),
        ])
        plan = service.analyze(m)
        assert "shards" in plan
        assert "conflict_analysis" in plan
        assert plan["execution_plan"]["total_shards"] >= 1

    @pytest.mark.asyncio
    async def test_submit(self):
        from agent.engine.service import EngineService
        service = EngineService()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        result = await service.submit(m)
        assert result["status"] == "submitted"
        assert result["task_count"] == 1
        assert "manifest_id" in result

    @pytest.mark.asyncio
    async def test_status(self):
        from agent.engine.service import EngineService
        service = EngineService()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        result = await service.submit(m)
        manifest_id = result["manifest_id"]
        status = service.status(manifest_id)
        assert status["total"] == 1
        assert "by_status" in status

    @pytest.mark.asyncio
    async def test_cancel(self):
        from agent.engine.service import EngineService
        service = EngineService()
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        result = await service.submit(m)
        manifest_id = result["manifest_id"]
        cancel_result = await service.cancel(manifest_id)
        assert cancel_result["cancelled"] == 1

    def test_stats(self):
        from agent.engine.service import EngineService
        service = EngineService()
        stats = service.stats
        assert "queue" in stats
        assert "running" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
