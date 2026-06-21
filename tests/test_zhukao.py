"""主考代理测试"""
import pytest
import asyncio


class TestZhukaoRegistration:
    def test_zhukao_in_registry(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("zhukao")
        assert spec is not None

    def test_zhukao_display_name(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("zhukao")
        assert spec.display_name == "主考"

    def test_zhukao_allowed_tools(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("zhukao")
        assert "read_file" in spec.allowed_tools
        assert "ast_parse" in spec.allowed_tools

    def test_zhukao_forbidden_tools(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("zhukao")
        assert "write_file" not in spec.allowed_tools
        assert "exec_python" not in spec.allowed_tools


class TestZhukaoCore:
    def setup_method(self):
        from agent.subagents.zhukao import ZhukaoAgent
        self.agent = ZhukaoAgent()

    def test_extract_signatures(self):
        code = "def hello(x, y):\n    return x + y"
        sigs = self.agent._extract_signatures(code)
        assert "def hello(x, y)" in sigs

    def test_self_check_valid(self):
        code = "def test_one(): assert 1 == 1"
        result = self.agent._self_check(code)
        assert result["ok"] is True
        assert "test_one" in result["test_names"]

    def test_self_check_invalid(self):
        code = "def test_one("
        result = self.agent._self_check(code)
        assert result["ok"] is False

    def test_format_output(self):
        result = self.agent._format_output(
            "tests/test_foo.py", "code", "unit", ["test_a"]
        )
        assert result["test_file"] == "tests/test_foo.py"
        assert result["test_names"] == ["test_a"]

    def test_l1_prompt_has_conftest(self):
        assert "{conftest_context}" in self.agent.L1_PROMPT

    def test_l2_prompt_has_blueprint(self):
        assert "{blueprint}" in self.agent.L2_PROMPT


class TestCircuitBreaker:
    """熔断器测试"""

    def setup_method(self):
        from agent.subagents.zhukao import ZhukaoAgent
        self.agent = ZhukaoAgent()

    def test_circuit_breaker_success(self):
        """成功时直接返回结果"""
        async def ok_func():
            return {"ok": True, "test_json": {"test_file": "test.py"}}

        result = asyncio.run(self.agent._circuit_breaker(ok_func))
        assert result["ok"] is True
        assert result["test_json"]["test_file"] == "test.py"

    def test_circuit_breaker_retry_then_success(self):
        """第1次失败，第2次成功"""
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"ok": False, "error": "timeout"}
            return {"ok": True, "test_json": {}}

        result = asyncio.run(self.agent._circuit_breaker(flaky_func))
        assert result["ok"] is True
        assert call_count == 2

    def test_circuit_breaker_degraded_on_failure(self):
        """重试后仍失败，返回降级结果"""
        async def fail_func():
            return {"ok": False, "error": "model error"}

        result = asyncio.run(self.agent._circuit_breaker(fail_func))
        assert result["ok"] is False
        assert result["degraded"] is True
        assert result["error"] == "model error"

    def test_circuit_breaker_exception_degraded(self):
        """函数抛异常，返回降级结果"""
        async def crash_func():
            raise RuntimeError("boom")

        result = asyncio.run(self.agent._circuit_breaker(crash_func))
        assert result["ok"] is False
        assert result["degraded"] is True
        assert "boom" in result["error"]


class TestDianbuUpgrade:
    def test_dianbu_not_readonly(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("shangbao_dianbu")
        assert spec.read_only is False

    def test_dianbu_has_exec_python(self):
        from agent.subagents.registry import SubagentRegistry
        spec = SubagentRegistry.get_spec("shangbao_dianbu")
        assert "exec_python" in spec.allowed_tools


class TestDianbuVerify:
    def test_parse_pass_all(self):
        from agent.subagents.dianbu_verify import parse_pytest_output
        output = "2 passed in 0.5s"
        result = parse_pytest_output(output, ["test_a", "test_b"])
        assert result["pass"] is True

    def test_parse_fail_single(self):
        from agent.subagents.dianbu_verify import parse_pytest_output
        output = "FAILED tests/test_foo.py::test_a - AssertionError: 1 != 2\n1 failed in 0.5s"
        result = parse_pytest_output(output, ["test_a", "test_b"])
        assert result["pass"] is False
        assert "test_a" in result["failed_tests"]

    def test_parse_fail_multiple(self):
        from agent.subagents.dianbu_verify import parse_pytest_output
        output = """FAILED tests/test_foo.py::test_a - AssertionError
FAILED tests/test_foo.py::test_b - AssertionError
2 failed in 0.5s"""
        result = parse_pytest_output(output, ["test_a", "test_b", "test_c"])
        assert result["pass"] is False
        assert len(result["failed_tests"]) == 2

    def test_parse_error_evidence(self):
        from agent.subagents.dianbu_verify import parse_pytest_output
        output = "FAILED tests/test_foo.py::test_a - AssertionError: expected 1 got 2\n======"
        result = parse_pytest_output(output, ["test_a"])
        assert "error_evidence" in result
        assert "AssertionError" in result["error_evidence"]
