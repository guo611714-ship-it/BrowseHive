"""子代理规格定义与注册中心"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class SubagentSpec:
    """子代理规格定义"""
    name: str
    display_name: str
    description: str
    allowed_tools: List[str]
    max_turns: int
    model_role: str = "secondary"  # "main" 或 "secondary"
    read_only: bool = False
    preferred_model: Optional[str] = None  # 指定模型名（覆盖model_role）
    internal_tools: List[str] = field(default_factory=list)  # 仅此agent可用的内部工具


class SubagentRegistry:
    """子代理注册中心"""

    _BUILTIN_SPECS = {
        "xiaohuangmen": SubagentSpec(
            name="xiaohuangmen",
            display_name="通传小黄门",
            description="轻量只读，适合短命令、快速确认、跑腿探路",
            allowed_tools=["read_file", "glob", "grep", "web_fetch"],
            max_turns=5,
            model_role="secondary",
            preferred_model="nvidia-step-3.7-flash"
        ),
        "sili_suitang": SubagentSpec(
            name="sili_suitang",
            display_name="司礼监随堂",
            description="只读文书，适合阅读代码、查阅文档、整理提纲",
            allowed_tools=["read_file", "glob", "grep", "web_fetch", "load_skill", "kb_search"],
            max_turns=10,
            model_role="secondary",
            read_only=True,
            preferred_model="nvidia-step-3.7-flash"
        ),
        "dongchang_tanshi": SubagentSpec(
            name="dongchang_tanshi",
            display_name="东厂探事",
            description="只读查访，适合抓网页、查资料、探索性搜索、调用浏览器AI平台",
            allowed_tools=["web_fetch", "glob", "grep", "load_skill",
                           "ask_doubao", "ask_deepseek_browser", "ask_bing", "ask_ouyi", "smart_ask", "browser_status"],
            max_turns=30,
            model_role="secondary",
            read_only=True,
            preferred_model="nvidia-step-3.7-flash"
        ),
        "shangbao_dianbu": SubagentSpec(
            name="shangbao_dianbu",
            display_name="尚宝监典簿",
            description="校验执行：跑测试+覆盖率分析，适合盘点文件、校对清单、执行测试验收",
            allowed_tools=["read_file", "glob", "grep", "exec_python", "coverage"],
            max_turns=20,
            model_role="secondary",
            read_only=False,
            preferred_model="nvidia-mistral-nemotron"
        ),
        "neiguan_yingzao": SubagentSpec(
            name="neiguan_yingzao",
            display_name="内官监营造",
            description="可读写、可执行命令，适合修改文件、搭建工程、跑命令验收",
            allowed_tools=["read_file", "write_file", "edit_file", "run_command", "glob", "grep",
                           "create_backup_branch", "git_diff_summary", "git_revert_to"],
            max_turns=100,
            model_role="main",
            preferred_model="nvidia-minimax-m2.7"
        ),
        "liubu_liulanqi": SubagentSpec(
            name="liubu_liulanqi",
            display_name="浏览器操作员",
            description="操控浏览器执行网页任务：导航、点击、输入、截图分析、页面数据提取、JS执行、多标签管理、表单填写、Cookie管理。支持多模态理解，适合网页数据采集、表单自动化、界面测试等任务",
            allowed_tools=["navigate", "click_element", "type_text", "scroll_page",
                           "wait_for_element", "screenshot_analyze", "get_page_text",
                           "get_page_ocr", "download_file", "smart_ask",
                           "start_browser_session", "end_browser_session", "get_session_memory",
                           "exec_js_tool", "multi_tab", "wait_for", "fill_form",
                           "upload_file", "manage_cookie", "screenshot_and_ask", "page_monitor",
                           "read_file", "write_file", "glob", "grep"],
            max_turns=50,
            model_role="main",
            read_only=False,
            preferred_model="nvidia-step-3.7-flash",
            internal_tools=["navigate", "click_element", "type_text", "scroll_page",
                           "wait_for_element", "screenshot_analyze", "get_page_text",
                           "get_page_ocr", "download_file"]
        ),
        # 翰林 — 代码生成+自检
        "hanlin": SubagentSpec(
            name="hanlin",
            display_name="翰林",
            description="代码生成、重构、修复，配备AST+Lint自检，可调用FixManifest并行执行",
            allowed_tools=[
                "read_file", "write_file", "read_codebase",
                "exec_python", "run_command",
                "ast_parse", "ruff_check",
                "git_diff", "git_stash", "git_log",
                "fix_manifest", "smart_ask",
                "glob", "grep",
                "run_tests", "full_stack_verify",
            ],
            max_turns=50,
            model_role="main",
            read_only=False,
            preferred_model="nvidia-step-3.7-flash"
        ),
        # 主考 — 测试出题
        "zhukao": SubagentSpec(
            name="zhukao",
            display_name="主考",
            description="提学御史，甩卷出题：读代码→生成测试JSON（不写文件不执行）",
            allowed_tools=[
                "read_file", "read_codebase", "glob", "grep", "ast_parse",
                "run_tests",
            ],
            max_turns=30,
            model_role="secondary",
            read_only=False,
            preferred_model="nvidia-step-3.7-flash"
        ),
    }

    # 别名映射（英文/通用名 → 内部标识）
    _ALIASES = {
        "general": "neiguan_yingzao",
        "researcher": "dongchang_tanshi",
        "reader": "sili_suitang",
        "coder": "neiguan_yingzao",
        "browser": "liubu_liulanqi",
        "web": "liubu_liulanqi",
        # 兼容旧英文标识
        "browser_agent": "liubu_liulanqi",
        "code_agent": "hanlin",
        "coder_agent": "hanlin",
        "neiguanjian": "neiguan_yingzao",
        "engineering": "neiguan_yingzao",
    }

    @classmethod
    def get_spec(cls, agent_type: str) -> Optional[SubagentSpec]:
        """获取子代理规格"""
        # 解析别名
        canonical = cls._ALIASES.get(agent_type, agent_type)
        return cls._BUILTIN_SPECS.get(canonical)

    @classmethod
    def list_available(cls) -> List[Dict]:
        """列出所有可用子代理"""
        return [
            {
                "name": spec.name,
                "display_name": spec.display_name,
                "description": spec.description,
                "allowed_tools": spec.allowed_tools,
                "max_turns": spec.max_turns,
                "model_role": spec.model_role,
                "read_only": spec.read_only
            }
            for spec in cls._BUILTIN_SPECS.values()
        ]

    @classmethod
    def validate_tool_access(cls, agent_type: str, tool_name: str) -> bool:
        """验证工具访问权限"""
        spec = cls.get_spec(agent_type)
        if not spec:
            return False
        return tool_name in spec.allowed_tools

    @classmethod
    def is_internal_tool(cls, tool_name: str) -> Optional[str]:
        """检查工具是否为内部工具（仅特定agent可用）。返回拥有该工具的agent名，或None"""
        for spec in cls._BUILTIN_SPECS.values():
            if tool_name in spec.internal_tools:
                return spec.name
        return None

    @classmethod
    def check_internal_access(cls, agent_type: str, tool_name: str) -> bool:
        """检查内部工具访问权限。非owner agent调用内部工具返回False"""
        owner = cls.is_internal_tool(tool_name)
        if owner is None:
            return True  # 非内部工具，任何agent都可访问
        return agent_type == owner  # 仅owner可访问
