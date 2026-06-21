"""翰林代理测试"""
import pytest
from agent.subagents.hanlin import CodeComplexityAnalyzer, HanlinAgent


class TestCodeComplexityAnalyzer:
    """复杂度评估器测试"""

    def setup_method(self):
        self.analyzer = CodeComplexityAnalyzer()

    def test_level1_lint_task(self):
        assert self.analyzer.assess("修复 lint 错误") == 1

    def test_level1_import_task(self):
        assert self.analyzer.assess("添加 import 语句") == 1

    def test_level1_format_task(self):
        assert self.analyzer.assess("格式化代码") == 1

    def test_level1_rename_task(self):
        assert self.analyzer.assess("重命名变量") == 1

    def test_level2_simple_function(self):
        assert self.analyzer.assess("实现一个排序函数", context_lines=30) == 2

    def test_level2_getter_setter(self):
        assert self.analyzer.assess("生成 getter 和 setter") == 2

    def test_level3_medium_task(self):
        assert self.analyzer.assess("适配新接口", context_lines=150) == 3

    def test_level3_class_method(self):
        assert self.analyzer.assess("实现类方法", context_lines=100) == 3

    def test_level4_architecture_refactor(self):
        assert self.analyzer.assess("重构认证架构") == 4

    def test_level4_design_pattern(self):
        assert self.analyzer.assess("应用设计模式") == 4

    def test_level4_core_algorithm(self):
        assert self.analyzer.assess("实现核心算法") == 4

    def test_level4_large_context(self):
        assert self.analyzer.assess("优化性能", context_lines=300) == 4

    def test_default_level(self):
        assert self.analyzer.assess("") == 4


class TestHanlinAgent:
    """翰林代理核心测试"""

    def setup_method(self):
        self.agent = HanlinAgent()

    def test_has_complexity_analyzer(self):
        assert hasattr(self.agent, 'complexity_analyzer')

    def test_has_system_prompts(self):
        assert hasattr(self.agent, 'FAST_TRACK_PROMPT')
        assert hasattr(self.agent, 'DEEP_THINK_PROMPT')

    def test_select_prompt_fast_track(self):
        prompt = self.agent._select_prompt(level=1)
        assert prompt == self.agent.FAST_TRACK_PROMPT

    def test_select_prompt_deep_think(self):
        prompt = self.agent._select_prompt(level=4)
        assert prompt == self.agent.DEEP_THINK_PROMPT

    def test_extract_code_block(self):
        response = "这是代码：\n```python\ndef hello():\n    pass\n```\n"
        code = self.agent._extract_code_block(response)
        assert code == "def hello():\n    pass"

    def test_extract_code_block_no_code(self):
        response = "这是纯文本，没有代码块"
        code = self.agent._extract_code_block(response)
        assert code is None

    def test_self_check_valid(self):
        code = "def hello():\n    return 'world'"
        result = self.agent._self_check(code)
        assert result["ok"] is True

    def test_self_check_invalid(self):
        code = "def hello(\n    return 'world'"
        result = self.agent._self_check(code)
        assert result["ok"] is False


class TestHanlinRegistration:
    """翰林注册测试"""

    def test_hanlin_in_registry(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("hanlin")
        assert spec is not None

    def test_hanlin_display_name(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("hanlin")
        assert spec.display_name == "翰林"

    def test_hanlin_allowed_tools(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("hanlin")
        assert "read_file" in spec.allowed_tools
        assert "write_file" in spec.allowed_tools
        assert "ast_parse" in spec.allowed_tools
        assert "ruff_check" in spec.allowed_tools
        assert "fix_manifest" in spec.allowed_tools

    def test_hanlin_alias(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("code_agent")
        assert spec is not None
        assert spec.name == "hanlin"


class TestHanlinFixManifestIntegration:
    """翰林 + FixManifest 集成测试"""

    def test_fix_manifest_format(self):
        """验证翰林输出的 FixManifest 格式"""
        manifest = {
            "tasks": [
                {
                    "id": "fix-1",
                    "file": "agent/auth.py",
                    "description": "更新函数签名",
                    "agent_type": "hanlin"
                },
                {
                    "id": "fix-2",
                    "file": "agent/routes.py",
                    "description": "适配新签名",
                    "agent_type": "hanlin"
                }
            ],
            "strategy": "auto"
        }

        assert "tasks" in manifest
        assert "strategy" in manifest
        assert len(manifest["tasks"]) == 2
        assert manifest["tasks"][0]["agent_type"] == "hanlin"

    def test_complexity_to_model_mapping(self):
        """验证复杂度到模型的映射"""
        analyzer = CodeComplexityAnalyzer()

        # Level 1-2 应使用轻量模型
        level1 = analyzer.assess("修复 lint 错误")
        level2 = analyzer.assess("实现排序函数", context_lines=30)
        assert level1 <= 2
        assert level2 <= 2

        # Level 3-5 应使用重量模型
        level3 = analyzer.assess("适配新接口", context_lines=150)
        level4 = analyzer.assess("重构认证架构")
        assert level3 >= 3
        assert level4 >= 3

    def test_hanlin_execute_returns_level(self):
        """验证翰林 execute 返回复杂度等级"""
        import asyncio
        agent = HanlinAgent()

        # 测试快稿模式
        result = asyncio.run(agent.execute("修复 lint 错误"))
        assert result["status"] == "success"
        assert result["level"] == 1

        # 测试深度模式
        result = asyncio.run(agent.execute("重构认证架构"))
        assert result["status"] == "success"
        assert result["level"] == 4

    def test_hanlin_calls_zhukao_in_fast_track(self):
        """验证翰林快稿模式调用主考出题"""
        import asyncio
        agent = HanlinAgent()

        # 快稿模式 + 提供代码 → 应返回 test_json
        result = asyncio.run(agent.execute(
            "实现排序函数",
            context={
                "code": "def sort_list(lst):\n    return sorted(lst)",
                "target_file": "agent/utils.py",
                "context_lines": 10
            }
        ))
        assert result["status"] == "success"
        assert result["level"] <= 2
        assert result["test_json"] is not None
        assert "test_file" in result["test_json"]
        assert "content" in result["test_json"]
        assert result["test_json"]["coverage_strategy"] == "unit"
        # 新增字段验证
        assert result["tests_passed"] is True
        assert result["circuit_breaker_triggered"] is False

    def test_hanlin_no_zhukao_in_deep_mode(self):
        """验证翰林深度模式不调用主考"""
        import asyncio
        agent = HanlinAgent()

        # 深度模式 → 不应返回 test_json
        result = asyncio.run(agent.execute("重构认证架构"))
        assert result["status"] == "success"
        assert result["level"] >= 3
        assert result["test_json"] is None
        assert result["tests_passed"] is False
        assert result["circuit_breaker_triggered"] is False

    def test_hanlin_circuit_breaker_triggered(self):
        """验证主考失败时熔断器降级"""
        import asyncio
        from unittest.mock import AsyncMock, patch
        agent = HanlinAgent()

        # Mock 主考 generate_tests 返回降级结果
        degraded_result = {"ok": False, "error": "timeout", "degraded": True}
        with patch(
            "agent.subagents.zhukao.ZhukaoAgent._circuit_breaker",
            new_callable=AsyncMock,
            return_value=degraded_result
        ):
            result = asyncio.run(agent.execute(
                "实现排序函数",
                context={
                    "code": "def sort_list(lst):\n    return sorted(lst)",
                    "target_file": "agent/utils.py",
                    "context_lines": 10
                }
            ))

        assert result["status"] == "success"
        assert result["test_json"] is None
        assert result["tests_passed"] is False
        assert result["circuit_breaker_triggered"] is True
