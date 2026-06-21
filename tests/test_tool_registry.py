"""tool_registry模块测试"""

import pytest
from agent.tools.tool_registry import (
    tool, get_tool_schemas, get_tool_implementation,
    get_all_tools, list_tools, TOOL_REGISTRY,
    _python_type_to_json_type,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """每个测试前清空注册表，测试后恢复"""
    original = dict(TOOL_REGISTRY)
    yield
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.update(original)


class TestPythonTypeToJsonType:
    def test_string(self):
        assert _python_type_to_json_type(str) == "string"

    def test_integer(self):
        assert _python_type_to_json_type(int) == "integer"

    def test_float(self):
        assert _python_type_to_json_type(float) == "number"

    def test_boolean(self):
        assert _python_type_to_json_type(bool) == "boolean"

    def test_list(self):
        assert _python_type_to_json_type(list) == "array"

    def test_dict_type(self):
        assert _python_type_to_json_type(dict) == "object"

    def test_unknown_type_defaults_to_string(self):
        assert _python_type_to_json_type(object) == "string"


class TestToolDecorator:
    def test_registers_tool(self):
        @tool("test_tool", "A test tool")
        def my_tool(x: str) -> str:
            """Test tool.

            :param x: input value
            """
            return x

        assert "test_tool" in TOOL_REGISTRY
        assert TOOL_REGISTRY["test_tool"]["implementation"] is my_tool

    def test_schema_structure(self):
        @tool("my_func", "My function")
        def func(a: int, b: str = "hello") -> str:
            """
            :param a: first param
            :param b: second param
            """
            return b

        schema = [s for s in get_tool_schemas() if s["function"]["name"] == "my_func"][0]
        assert schema["type"] == "function"
        assert schema["function"]["description"] == "My function"

        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        assert "a" in params["properties"]
        assert "b" in params["properties"]
        assert params["properties"]["a"]["type"] == "integer"
        assert params["properties"]["b"]["type"] == "string"
        assert params["properties"]["b"]["default"] == "hello"
        assert "a" in params["required"]
        assert "b" not in params["required"]

    def test_param_description_from_docstring(self):
        @tool("desc_tool", "Tool with descriptions")
        def func(name: str, age: int = 0) -> str:
            """
            :param name: the user name
            :param age: the user age
            """
            return name

        schema = [s for s in get_tool_schemas() if s["function"]["name"] == "desc_tool"][0]
        props = schema["function"]["parameters"]["properties"]
        assert props["name"]["description"] == "the user name"
        assert props["age"]["description"] == "the user age"

    def test_metadata_attached_to_function(self):
        @tool("meta_tool", "Metadata test")
        def func() -> str:
            return "ok"

        assert func._tool_name == "meta_tool"
        assert func._tool_schema["type"] == "function"

    def test_unserializable_default_skipped(self):
        @tool("bad_default", "Test")
        def func(x: str = lambda: None) -> str:
            return x

        schema = get_tool_schemas()[-1]
        props = schema["function"]["parameters"]["properties"]
        assert "default" not in props["x"]


class TestGetToolImplementation:
    def test_existing_tool(self):
        @tool("impl_test", "Test")
        def func() -> str:
            return "done"

        impl = get_tool_implementation("impl_test")
        assert impl is func

    def test_nonexistent_tool(self):
        assert get_tool_implementation("no_such_tool") is None


class TestGetAllTools:
    def test_returns_dict(self):
        @tool("all_test", "Test")
        def func() -> str:
            return "ok"

        tools = get_all_tools()
        assert isinstance(tools, dict)
        assert "all_test" in tools


class TestListTools:
    def test_returns_list_of_names(self):
        @tool("list_test", "Test")
        def func() -> str:
            return "ok"

        names = list_tools()
        assert isinstance(names, list)
        assert "list_test" in names
