"""翰林代码工具测试"""
import pytest
from agent.tools.code_tools import ast_parse, ruff_check


class TestAstParse:
    """AST 语法校验测试"""

    def test_valid_syntax(self):
        code = "def hello():\n    return 'world'"
        result = ast_parse(code)
        assert result["ok"] is True
        assert result["error"] is None

    def test_invalid_syntax(self):
        code = "def hello(\n    return 'world'"
        result = ast_parse(code)
        assert result["ok"] is False
        assert "SyntaxError" in result["error"]

    def test_empty_code(self):
        result = ast_parse("")
        assert result["ok"] is True

    def test_complex_valid_code(self):
        code = '''
class MyClass:
    def __init__(self, x: int):
        self.x = x

    def method(self) -> int:
        return self.x * 2
'''
        result = ast_parse(code)
        assert result["ok"] is True

    def test_indentation_error(self):
        code = "def hello():\nreturn 'world'"
        result = ast_parse(code)
        assert result["ok"] is False


class TestRuffCheck:
    """Ruff Lint 检查测试"""

    def test_clean_code(self):
        code = "def hello():\n    return 'world'"
        result = ruff_check(code)
        assert result["ok"] is True
        assert result["fixed"] == ""

    def test_import_order(self):
        code = "import os\nimport sys\nimport json"
        result = ruff_check(code)
        # Ruff 可能报 import 排序问题，但不应崩溃
        assert "ok" in result

    def test_unused_import(self):
        code = "import os\nimport sys\ndef hello():\n    return 'world'"
        result = ruff_check(code)
        # Ruff 会检测未使用的 import
        assert "ok" in result

    def test_ruff_not_installed(self):
        """当 ruff 未安装时应优雅降级"""
        import unittest.mock as mock
        with mock.patch('subprocess.run', side_effect=FileNotFoundError):
            result = ruff_check("test code")
            assert result["ok"] is True  # 降级为通过
            assert "ruff not installed" in result.get("warning", "")


class TestToolRegistration:
    """工具注册测试"""

    def test_ast_parse_registered(self):
        from agent.tools.tool_registry import get_tool_schemas
        schemas = get_tool_schemas()
        names = [s["function"]["name"] for s in schemas]
        assert "ast_parse" in names

    def test_ruff_check_registered(self):
        from agent.tools.tool_registry import get_tool_schemas
        schemas = get_tool_schemas()
        names = [s["function"]["name"] for s in schemas]
        assert "ruff_check" in names
