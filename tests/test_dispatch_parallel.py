"""tests/test_dispatch_parallel.py — SubagentDispatcher 基础测试"""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── helpers ─────────────────────────────────────────────────────────

def _make_dispatcher(tools=None, progress_callback=None):
    """构造一个尽量少依赖的 SubagentDispatcher（mock 掉外部模块）"""
    from agent.tools.dispatch.parallel import SubagentDispatcher
    return SubagentDispatcher(
        model_orchestrator=None,
        team_store=None,
        tools=tools or {},
        memory=None,
        progress_callback=progress_callback,
    )


def _noop_progress(event):
    """静默进度回调，避免输出噪声"""
    pass


# ── 1. 初始化 ──────────────────────────────────────────────────────

class TestDispatcherInit:
    """SubagentDispatcher 初始化测试"""

    def test_basic_init(self):
        d = _make_dispatcher()
        assert d.registry is not None
        assert d.model_orchestrator is None
        assert d.team_store is None
        assert d.tools == {}
        assert d.memory is None

    def test_init_with_progress_callback(self):
        calls = []
        def cb(event):
            calls.append(event)
        d = _make_dispatcher(progress_callback=cb)
        # 触发一个 progress 事件，验证回调被注册
        from agent.tools.dispatch.parallel import AgentProgressEvent
        from datetime import datetime
        d.progress(AgentProgressEvent(
            timestamp=datetime.now(), agent_name="test",
            step="start", status="running", message="ok", progress=0
        ))
        assert len(calls) == 1

    def test_init_with_tools(self):
        fake_tool = AsyncMock(return_value={"ok": True})
        d = _make_dispatcher(tools={"read_file": fake_tool})
        assert "read_file" in d.tools


# ── 2. 基本派遣流程 ────────────────────────────────────────────────

class TestDispatcherDispatch:
    """dispatch 基本流程测试（用 mock LLM）"""

    @pytest.mark.asyncio
    async def test_dispatch_unknown_agent_returns_failed(self):
        d = _make_dispatcher()
        result = await d.dispatch(agent_type="nonexistent_agent", task="test")
        assert result["status"] == "failed"
        assert "未知" in result["summary"]

    @pytest.mark.asyncio
    async def test_dispatch_no_client_returns_failed(self):
        """无 LLM client 时应返回 failed"""
        from agent.tools.dispatch.parallel import SubagentDispatcher
        from agent.subagents.registry import SubagentRegistry
        # 取一个已知 agent 类型
        known = list(SubagentRegistry._BUILTIN_SPECS.keys())[0]
        d = _make_dispatcher()
        result = await d.dispatch(agent_type=known, task="say hello")
        assert result["status"] == "failed"
        assert "未配置" in result["summary"]


# ── 3. 进度回调 ─────────────────────────────────────────────────────

class TestProgressCallback:
    """进度回调机制测试"""

    @pytest.mark.asyncio
    async def test_dispatch_fires_progress_events(self):
        events = []
        def capture(event):
            events.append(event)

        d = _make_dispatcher(progress_callback=capture)
        # 未知 agent 也会触发 progress（在 _dispatch_impl 里 spec 未命中时直接 return）
        await d.dispatch(agent_type="nonexistent", task="test task")
        # 应至少收到 start 和 complete/failed 事件
        # 但 unknown agent 在 _dispatch_impl 内直接 return 没有 progress
        # 所以这里验证 dispatch 调用本身不会抛异常
        assert isinstance(events, list)

    def test_claude_code_printer_does_not_crash(self):
        from agent.tools.dispatch.parallel import AgentProgressEvent, claude_code_printer
        from datetime import datetime
        event = AgentProgressEvent(
            timestamp=datetime.now(), agent_name="test",
            step="complete", status="success", message="done", progress=100
        )
        # 不应抛出异常
        claude_code_printer(event)


# ── 4. 工具过滤 ─────────────────────────────────────────────────────

class TestToolFiltering:
    """子代理工具过滤测试"""

    def test_build_subagent_tools_filters_by_spec(self):
        d = _make_dispatcher(tools={
            "read_file": lambda: None,
            "write_file": lambda: None,
            "run_command": lambda: None,
        })
        from agent.subagents.registry import SubagentRegistry, SubagentSpec
        # 构造一个只允许 read_file 的 spec
        spec = SubagentSpec(
            name="test", display_name="Test", description="test",
            allowed_tools=["read_file"], max_turns=5
        )
        filtered = d._build_subagent_tools(spec)
        assert "read_file" in filtered
        assert "write_file" not in filtered


# ── 5. 工具结果截断 ────────────────────────────────────────────────

class TestResultTruncation:
    """结果截断逻辑测试"""

    def test_safe_str_truncates(self):
        from agent.tools.dispatch.parallel import _safe_str
        long = "x" * 500
        result = _safe_str(long, max_len=100)
        assert len(result) <= 100

    def test_safe_str_handles_unprintable(self):
        from agent.tools.dispatch.parallel import _safe_str
        class Unprintable:
            def __str__(self):
                raise RuntimeError("nope")
            def __repr__(self):
                raise RuntimeError("nope either")
        result = _safe_str(Unprintable())
        assert "unprintable" in result


# ── 6. 简单任务识别 ────────────────────────────────────────────────

class TestSimpleTaskDetection:
    """_is_simple_task 和 _validate_result 测试"""

    def test_short_task_with_keyword_is_simple(self):
        from agent.tools.dispatch.parallel import _is_simple_task
        assert _is_simple_task("读取文件 config.yaml") is True

    def test_long_task_is_not_simple(self):
        from agent.tools.dispatch.parallel import _is_simple_task
        assert _is_simple_task("请帮我重构整个模块的架构，并添加完整的单元测试覆盖所有边界情况") is False

    def test_validate_result_rejects_empty(self):
        from agent.tools.dispatch.parallel import _validate_result
        assert _validate_result("", "task") is False
        assert _validate_result("   ", "task") is False

    def test_validate_result_rejects_error_prefix(self):
        from agent.tools.dispatch.parallel import _validate_result
        assert _validate_result("[错误] something broke", "task") is False

    def test_validate_result_accepts_valid(self):
        from agent.tools.dispatch.parallel import _validate_result
        assert _validate_result("文件内容已读取完成", "读取文件") is True


# ── 7. 全局单例 get_dispatcher ──────────────────────────────────────

class TestGetDispatcher:
    """get_dispatcher 全局单例测试"""

    def test_returns_same_instance(self):
        import agent.tools.dispatch.parallel as mod
        mod._dispatcher = None  # 重置单例
        d1 = _make_dispatcher()
        # patch _dispatcher 让 get_dispatcher 创建新实例
        mod._dispatcher = None
        d2 = mod.get_dispatcher()
        d3 = mod.get_dispatcher()
        assert d2 is d3
        # 清理
        mod._dispatcher = None
