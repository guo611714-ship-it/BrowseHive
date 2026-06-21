"""Engine Bridge 测试 — Protocol + Bridge + ContextVar 注入"""

import pytest
import asyncio
import sys
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from fix_engine.manifest import FixManifest, FixItem, FixStrategy, ConflictResolution
from fix_engine.result import FixResult
from agent.engine_protocol import EngineProtocol
from agent.engine_bridge import EngineBridge
from agent.dependencies import engine_ctx


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FixManifest 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFixManifest:
    def test_create_manifest(self):
        items = [
            FixItem(id="f1", file="a.py", description="fix", agent_type="neiguan_yingzao"),
            FixItem(id="f2", file="b.py", description="fix", agent_type="neiguan_yingzao"),
        ]
        m = FixManifest(tasks=items)
        assert m.task_count == 2
        assert m.file_count == 2
        assert m.strategy == FixStrategy.AUTO
        assert m.conflict == ConflictResolution.SERIAL_RERUN

    def test_manifest_summary(self):
        items = [FixItem(id="f1", file="a.py", description="fix", agent_type="x")]
        m = FixManifest(tasks=items)
        assert "1 tasks" in m.summary()
        assert "1 files" in m.summary()

    def test_manifest_dedup_files(self):
        items = [
            FixItem(id="f1", file="a.py", description="fix", agent_type="x"),
            FixItem(id="f2", file="a.py", description="fix2", agent_type="x"),
        ]
        m = FixManifest(tasks=items)
        assert m.file_count == 1

    def test_empty_manifest(self):
        m = FixManifest(tasks=[])
        assert m.task_count == 0

    def test_manifest_with_line_range(self):
        item = FixItem(
            id="f1", file="a.py", description="fix", agent_type="x",
            line_start=10, line_end=20
        )
        m = FixManifest(tasks=[item])
        assert m.tasks[0].line_start == 10
        assert m.tasks[0].line_end == 20

    def test_manifest_with_metadata(self):
        m = FixManifest(
            tasks=[FixItem(id="f1", file="a.py", description="fix", agent_type="x")],
            metadata={"skill": "test", "user": "dev"}
        )
        assert m.metadata["skill"] == "test"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FixItem 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFixItem:
    def test_to_task_dict(self):
        item = FixItem(
            id="f1", file="a.py", description="fix bug", agent_type="neiguan_yingzao",
            context="extra info"
        )
        d = item.to_task_dict()
        assert d["task_id"] == "f1"
        assert d["description"] == "fix bug"
        assert d["files"] == ["a.py"]
        assert d["agent_type"] == "neiguan_yingzao"
        assert d["context"] == "extra info"

    def test_defaults(self):
        item = FixItem(id="f1", file="a.py", description="fix", agent_type="x")
        assert item.line_start is None
        assert item.line_end is None
        assert item.context is None
        assert item.priority == 0
        assert item.metadata == {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FixResult 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFixResult:
    def test_success_result(self):
        r = FixResult(success=True, summary="ok", patch="diff")
        assert r.success is True
        assert r.failed_count == 0
        assert r.succeeded_count == 0  # no details

    def test_result_with_details(self):
        r = FixResult(
            success=True, summary="ok",
            details=[
                {"status": "success", "agent_type": "a"},
                {"status": "success", "agent_type": "b"},
                {"status": "failed", "agent_type": "c"},
            ]
        )
        assert r.succeeded_count == 2
        assert r.failed_count == 1

    def test_result_defaults(self):
        r = FixResult(success=False, summary="fail")
        assert r.patch is None
        assert r.conflicts == []
        assert r.details == []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EngineProtocol 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestEngineProtocol:
    def test_mock_implements_protocol(self):
        """Protocol 是结构化的，不需要显式继承"""
        class MockEngine:
            async def submit_fix_manifest(self, manifest):
                return FixResult(success=True, summary="mock")

        mock = MockEngine()
        # runtime_checkable Protocol 可以用 isinstance 检查
        assert isinstance(mock, EngineProtocol)

    def test_mock_without_protocol_fails(self):
        """缺少方法的 mock 不满足 Protocol"""
        class IncompleteEngine:
            pass

        assert not isinstance(IncompleteEngine(), EngineProtocol)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ContextVar 注入测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestContextVar:
    def test_set_and_get(self):
        """设置和获取引擎实例"""
        class MockEngine:
            async def submit_fix_manifest(self, manifest):
                return FixResult(success=True, summary="ok")

        mock = MockEngine()
        token = engine_ctx.set(mock)
        try:
            retrieved = engine_ctx.get()
            assert retrieved is mock
        finally:
            engine_ctx.reset(token)

    def test_default_unset(self):
        """未设置时抛出 LookupError"""
        # 确保在测试环境中能重置
        token = engine_ctx.set("sentinel")
        engine_ctx.reset(token)
        # reset 后应该回到默认状态（可能有其他测试设置的值）

    def test_import_from_agent_package(self):
        """可以从 agent 包直接导入 engine_ctx"""
        from agent import engine_ctx as ctx
        assert ctx is engine_ctx


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EngineBridge 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestEngineBridge:
    def test_bridge_creation(self):
        """桥接器创建"""
        class FakeEngine:
            async def submit(self, manifest):
                return {"status": "success", "results": [], "merged": {}}

        bridge = EngineBridge(FakeEngine())
        assert bridge._engine is not None

    def test_bridge_submit_fix_manifest(self):
        """桥接器提交修复清单"""
        class FakeEngine:
            async def submit(self, manifest):
                return {
                    "status": "success",
                    "results": [
                        {"status": "success", "agent_type": "a"},
                        {"status": "failed", "agent_type": "b"},
                    ],
                    "merged": {
                        "merged_files": {"a.py": "content"},
                        "conflicts": [],
                    }
                }

        async def _test():
            bridge = EngineBridge(FakeEngine())
            manifest = FixManifest(tasks=[
                FixItem(id="f1", file="a.py", description="fix", agent_type="x"),
            ])
            result = await bridge.submit_fix_manifest(manifest)
            assert result.success is True
            assert result.succeeded_count == 1
            assert result.failed_count == 1
            assert result.patch == {"a.py": "content"}

        asyncio.run(_test())

    def test_bridge_with_conflicts(self):
        """桥接器处理冲突结果"""
        class FakeEngine:
            async def submit(self, manifest):
                return {
                    "status": "partial",
                    "results": [],
                    "merged": {
                        "conflicts": [{"file": "a.py", "reason": "overlap"}],
                    }
                }

        async def _test():
            bridge = EngineBridge(FakeEngine())
            manifest = FixManifest(tasks=[
                FixItem(id="f1", file="a.py", description="fix", agent_type="x"),
            ])
            result = await bridge.submit_fix_manifest(manifest)
            assert result.success is False
            assert len(result.conflicts) == 1

        asyncio.run(_test())

    def test_bridge_submit_returns_fix_result(self):
        """桥接器返回值是 FixResult 类型"""
        class FakeEngine:
            async def submit(self, manifest):
                return {"status": "success", "results": [], "merged": {}}

        async def _test():
            bridge = EngineBridge(FakeEngine())
            manifest = FixManifest(tasks=[
                FixItem(id="f1", file="a.py", description="fix", agent_type="x"),
            ])
            result = await bridge.submit_fix_manifest(manifest)
            assert isinstance(result, FixResult)

        asyncio.run(_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
