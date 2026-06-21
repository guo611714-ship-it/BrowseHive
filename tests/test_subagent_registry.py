"""subagents/registry.py 测试 -- 子代理规格定义与注册中心"""

from agent.subagents.registry import SubagentSpec, SubagentRegistry


class TestSubagentSpec:
    """SubagentSpec 数据类测试"""

    def test_init(self):
        spec = SubagentSpec(
            name="test", display_name="Test", description="desc",
            allowed_tools=["tool_a"], max_turns=5
        )
        assert spec.name == "test"
        assert spec.model_role == "secondary"
        assert spec.read_only is False

    def test_defaults(self):
        spec = SubagentSpec(
            name="t", display_name="T", description="d",
            allowed_tools=[], max_turns=1
        )
        assert spec.internal_tools == []


class TestSubagentRegistry:
    """SubagentRegistry 注册中心测试"""

    def test_builtin_specs_count(self):
        assert len(SubagentRegistry._BUILTIN_SPECS) >= 6

    def test_get_spec_by_name(self):
        spec = SubagentRegistry.get_spec("xiaohuangmen")
        assert spec is not None
        assert spec.name == "xiaohuangmen"
        assert "read_file" in spec.allowed_tools

    def test_get_spec_alias(self):
        spec = SubagentRegistry.get_spec("general")
        assert spec is not None
        assert spec.name == "neiguan_yingzao"

    def test_get_spec_coder_alias(self):
        spec = SubagentRegistry.get_spec("coder")
        assert spec.name == "neiguan_yingzao"

    def test_get_spec_unknown(self):
        assert SubagentRegistry.get_spec("nonexistent") is None

    def test_list_available(self):
        available = SubagentRegistry.list_available()
        assert len(available) >= 6
        names = [a["name"] for a in available]
        assert "xiaohuangmen" in names

    def test_validate_tool_access_allowed(self):
        assert SubagentRegistry.validate_tool_access("xiaohuangmen", "read_file") is True

    def test_validate_tool_access_denied(self):
        assert SubagentRegistry.validate_tool_access("xiaohuangmen", "write_file") is False

    def test_validate_tool_access_unknown_agent(self):
        assert SubagentRegistry.validate_tool_access("nonexistent", "read_file") is False

    def test_is_internal_tool(self):
        assert SubagentRegistry.is_internal_tool("navigate") == "liubu_liulanqi"

    def test_is_internal_tool_non_internal(self):
        assert SubagentRegistry.is_internal_tool("read_file") is None

    def test_check_internal_access_owner(self):
        assert SubagentRegistry.check_internal_access("liubu_liulanqi", "navigate") is True

    def test_check_internal_access_non_owner(self):
        assert SubagentRegistry.check_internal_access("xiaohuangmen", "navigate") is False

    def test_check_internal_access_non_internal(self):
        assert SubagentRegistry.check_internal_access("xiaohuangmen", "read_file") is True
