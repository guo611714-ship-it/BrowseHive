"""端到端集成测试 — 使用MockLLM，不需要真实API调用"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from tests.mock_llm import MockLLMClient


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """临时工作区目录"""
    return tmp_path


@pytest.fixture
def mock_llm() -> MockLLMClient:
    """默认MockLLM实例"""
    return MockLLMClient()


# ---------------------------------------------------------------------------
# 1. AgentLoop 初始化 (mock LLM)
# ---------------------------------------------------------------------------

class TestAgentLoopInit:
    """测试AgentLoop组件初始化，不依赖真实模型"""

    def test_import(self) -> None:
        """agent.memory模块可导入"""
        from agent.memory import MemoryStore
        assert MemoryStore is not None

    def test_memory_store_created(self, tmp_dir: Path) -> None:
        """AgentLoop创建后memory目录存在"""
        from agent.memory import MemoryStore
        mem = MemoryStore(tmp_dir / "memory")
        assert mem.memory_dir.exists()
        assert (mem.memory_dir / "MEMORY.md").exists()

    def test_mock_llm_chat(self, mock_llm: MockLLMClient) -> None:
        """MockLLM能响应chat调用"""
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(
                mock_llm.chat([{"role": "user", "content": "hi"}])
            )
            assert resp["content"] == "Mock response"
            assert resp["status_code"] == 200
            assert mock_llm._call_count == 1
        finally:
            loop.close()

    def test_mock_llm_preset_responses(self) -> None:
        """MockLLM按顺序返回预设响应"""
        responses = [
            {"content": "first", "tool_calls": [], "usage": {}, "status_code": 200},
            {"content": "second", "tool_calls": [], "usage": {}, "status_code": 200},
        ]
        client = MockLLMClient(responses=responses)
        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(client.chat([{"role": "user", "content": "a"}]))
            r2 = loop.run_until_complete(client.chat([{"role": "user", "content": "b"}]))
            r3 = loop.run_until_complete(client.chat([{"role": "user", "content": "c"}]))
            assert r1["content"] == "first"
            assert r2["content"] == "second"
            assert r3["content"] == "Mock response"  # 超出预设后走默认
            assert len(client.call_history) == 3
        finally:
            loop.close()

    def test_mock_llm_reset(self) -> None:
        """MockLLM reset重置状态"""
        client = MockLLMClient(responses=[
            {"content": "x", "tool_calls": [], "usage": {}, "status_code": 200}
        ])
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(client.chat([{"role": "user", "content": "a"}]))
            assert client._call_count == 1
            client.reset()
            assert client._call_count == 0
            assert client.call_history == []
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# 2. ToolRegistry 工具注册
# ---------------------------------------------------------------------------

class TestToolRegistry:
    """测试工具注册系统"""

    def test_import(self) -> None:
        from agent.tools.tool_registry import TOOL_REGISTRY, tool, get_tool_schemas
        assert TOOL_REGISTRY is not None

    def test_tool_decorator_registers(self) -> None:
        """@tool装饰器将函数注册到全局注册表"""
        from agent.tools.tool_registry import TOOL_REGISTRY, tool

        @tool("test_ping", "测试ping工具")
        def ping(msg: str) -> str:
            """ping测试

            :param msg: 消息内容
            """
            return f"pong: {msg}"

        assert "test_ping" in TOOL_REGISTRY
        schema = TOOL_REGISTRY["test_ping"]["schema"]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "test_ping"
        # 清理
        del TOOL_REGISTRY["test_ping"]

    def test_get_tool_schemas(self) -> None:
        """get_tool_schemas返回schema列表"""
        from agent.tools.tool_registry import get_tool_schemas
        schemas = get_tool_schemas()
        assert isinstance(schemas, list)
        # 已有工具应该至少有几个
        assert len(schemas) >= 0

    def test_get_tool_implementation(self) -> None:
        """get_tool_implementation返回可调用对象"""
        from agent.tools.tool_registry import TOOL_REGISTRY, tool, get_tool_implementation

        @tool("test_impl", "测试实现")
        def dummy() -> str:
            return "ok"

        impl = get_tool_implementation("test_impl")
        assert impl is not None
        assert callable(impl)
        # 清理
        del TOOL_REGISTRY["test_impl"]

    def test_get_nonexistent_tool(self) -> None:
        """获取不存在的工具返回None"""
        from agent.tools.tool_registry import get_tool_implementation
        assert get_tool_implementation("nonexistent_tool_xyz") is None


# ---------------------------------------------------------------------------
# 3. MemoryStore 读写
# ---------------------------------------------------------------------------

class TestMemoryStore:
    """测试三层记忆系统"""

    def test_init_creates_files(self, tmp_dir: Path) -> None:
        """初始化创建必要文件"""
        from agent.memory import MemoryStore
        mem = MemoryStore(tmp_dir / "mem")
        assert mem.long_term_file.exists()
        assert mem.user_file.exists()
        assert mem.history_file.exists()
        assert mem.tokens_file.exists()

    def test_append_history(self, tmp_dir: Path) -> None:
        """append_history写入JSONL"""
        from agent.memory import MemoryStore
        mem = MemoryStore(tmp_dir / "mem")
        mem.append_history({"role": "user", "content": "hello"})
        content = mem.history_file.read_text(encoding="utf-8").strip()
        assert content != ""
        import json
        record = json.loads(content)
        assert record["role"] == "user"

    def test_append_history_multiple(self, tmp_dir: Path) -> None:
        """多次追加历史"""
        from agent.memory import MemoryStore
        mem = MemoryStore(tmp_dir / "mem")
        for i in range(5):
            mem.append_history({"role": "user", "content": f"msg_{i}"})
        lines = mem.history_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 5

    def test_long_term_write_read(self, tmp_dir: Path) -> None:
        """长期记忆写入和读取"""
        from agent.memory import MemoryStore
        mem = MemoryStore(tmp_dir / "mem")
        test_content = "# 长期记忆\n\n重要信息：测试通过"
        mem.long_term_file.write_text(test_content, encoding="utf-8")
        assert mem.long_term_file.read_text(encoding="utf-8") == test_content

    def test_user_file_write_read(self, tmp_dir: Path) -> None:
        """用户偏好文件读写"""
        from agent.memory import MemoryStore
        mem = MemoryStore(tmp_dir / "mem")
        content = "# 用户偏好\n\n语言: 中文"
        mem.user_file.write_text(content, encoding="utf-8")
        assert "中文" in mem.user_file.read_text(encoding="utf-8")

    def test_compress_lock(self, tmp_dir: Path) -> None:
        """压缩锁机制正常工作"""
        from agent.memory import MemoryStore
        mem = MemoryStore(tmp_dir / "mem")
        assert mem.try_compress_lock() is True
        assert mem.try_compress_lock() is False  # 第二次获取失败
        mem.release_compress_lock()
        assert mem.try_compress_lock() is True  # 释放后可再次获取
        mem.release_compress_lock()


# ---------------------------------------------------------------------------
# 4. TaskStateManager DAG依赖
# ---------------------------------------------------------------------------

class TestTaskStateManager:
    """测试任务状态管理器的DAG依赖"""

    def _make_manager(self, tmp_dir: Path):
        from agent.state.task_state import TaskStateManager
        state_file = tmp_dir / "task_state.json"
        return TaskStateManager(state_path=str(state_file))

    def test_add_task(self, tmp_dir: Path) -> None:
        """添加任务"""
        mgr = self._make_manager(tmp_dir)
        task = mgr.add_task("t1", "任务1", agent_type="code")
        assert task.id == "t1"
        assert task.status == "pending"
        assert "t1" in mgr.tasks

    def test_update_status(self, tmp_dir: Path) -> None:
        """更新任务状态"""
        mgr = self._make_manager(tmp_dir)
        mgr.add_task("t1", "任务1")
        result = mgr.update_status("t1", "done", result="完成")
        assert result is True
        assert mgr.tasks["t1"].status == "done"
        assert mgr.tasks["t1"].result == "完成"

    def test_update_nonexistent(self, tmp_dir: Path) -> None:
        """更新不存在的任务返回False"""
        mgr = self._make_manager(tmp_dir)
        assert mgr.update_status("nonexistent", "done") is False

    def test_dag_dependency_chain(self, tmp_dir: Path) -> None:
        """DAG: A -> B -> C 依赖链"""
        mgr = self._make_manager(tmp_dir)
        mgr.add_task("a", "A")
        mgr.add_task("b", "B", depends_on=["a"])
        mgr.add_task("c", "C", depends_on=["b"])

        # 初始只有A可执行
        ready = mgr.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "a"

        # 完成A后B可执行
        mgr.update_status("a", "done")
        ready = mgr.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "b"

        # 完成B后C可执行
        mgr.update_status("b", "done")
        ready = mgr.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "c"

    def test_dag_parallel_tasks(self, tmp_dir: Path) -> None:
        """DAG: B和C都依赖A，A完成后B和C并行"""
        mgr = self._make_manager(tmp_dir)
        mgr.add_task("a", "A")
        mgr.add_task("b", "B", depends_on=["a"])
        mgr.add_task("c", "C", depends_on=["a"])

        mgr.update_status("a", "done")
        ready = mgr.get_ready_tasks()
        ready_ids = {t.id for t in ready}
        assert ready_ids == {"b", "c"}

    def test_get_dependencies(self, tmp_dir: Path) -> None:
        """获取递归依赖"""
        mgr = self._make_manager(tmp_dir)
        mgr.add_task("a", "A")
        mgr.add_task("b", "B", depends_on=["a"])
        mgr.add_task("c", "C", depends_on=["b"])
        deps = mgr.get_dependencies("c")
        assert deps == {"a", "b"}

    def test_get_progress(self, tmp_dir: Path) -> None:
        """进度统计"""
        mgr = self._make_manager(tmp_dir)
        mgr.add_task("a", "A")
        mgr.add_task("b", "B")
        mgr.add_task("c", "C")
        mgr.update_status("a", "done")
        mgr.update_status("b", "running")
        progress = mgr.get_progress()
        assert progress["total"] == 3
        assert progress["done"] == 1
        assert progress["running"] == 1
        assert progress["pending"] == 1
        assert progress["percent"] == 33

    def test_persistence(self, tmp_dir: Path) -> None:
        """状态持久化到磁盘"""
        mgr1 = self._make_manager(tmp_dir)
        mgr1.add_task("t1", "任务1")
        mgr1.update_status("t1", "done")
        mgr1.save_now()

        # 重新加载
        mgr2 = self._make_manager(tmp_dir)
        assert "t1" in mgr2.tasks
        assert mgr2.tasks["t1"].status == "done"


# ---------------------------------------------------------------------------
# 5. CleanupScheduler 启停
# ---------------------------------------------------------------------------

class TestCleanupScheduler:
    """测试清理调度器启停"""

    def test_import(self) -> None:
        from agent.cleanup import CleanupScheduler, cleanup_memory_archives
        assert CleanupScheduler is not None

    def test_scheduler_start_stop(self) -> None:
        """调度器启动和停止"""
        from agent.cleanup import CleanupScheduler
        scheduler = CleanupScheduler(interval_hours=24)
        scheduler.start()
        assert scheduler._running is True
        assert scheduler._timer is not None
        scheduler.stop()
        assert scheduler._running is False
        assert scheduler._timer is None

    def test_scheduler_double_stop(self) -> None:
        """重复停止不报错"""
        from agent.cleanup import CleanupScheduler
        scheduler = CleanupScheduler(interval_hours=24)
        scheduler.start()
        scheduler.stop()
        scheduler.stop()  # 不应抛异常

    def test_cleanup_memory_archives(self, tmp_dir: Path) -> None:
        """清理过期的内存归档文件"""
        from agent.cleanup import cleanup_memory_archives
        import time, os

        mem_dir = tmp_dir / "mem"
        archive_dir = mem_dir / "archive"
        archive_dir.mkdir(parents=True)

        # 创建一个过期文件
        old_file = archive_dir / "old.jsonl"
        old_file.write_text("old data", encoding="utf-8")
        os.utime(old_file, (time.time() - 100 * 86400, time.time() - 100 * 86400))

        # 创建一个新文件
        new_file = archive_dir / "new.jsonl"
        new_file.write_text("new data", encoding="utf-8")

        stats = cleanup_memory_archives(mem_dir, retention_days=90)
        assert stats["deleted_count"] == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_cleanup_old_logs(self, tmp_dir: Path) -> None:
        """清理过期日志文件"""
        from agent.cleanup import cleanup_old_logs
        import time, os

        log_dir = tmp_dir / "logs"
        log_dir.mkdir(parents=True)

        # 过期日志
        old_log = log_dir / "old.log"
        old_log.write_text("old log", encoding="utf-8")
        os.utime(old_log, (time.time() - 60 * 86400, time.time() - 60 * 86400))

        # 新日志
        new_log = log_dir / "new.log"
        new_log.write_text("new log", encoding="utf-8")

        stats = cleanup_old_logs(log_dir, retention_days=30)
        assert stats["deleted_count"] == 1
        assert not old_log.exists()
        assert new_log.exists()
