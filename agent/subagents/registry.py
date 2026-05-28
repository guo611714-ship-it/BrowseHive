"""子代理规格定义与注册中心"""

from dataclasses import dataclass
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


class SubagentRegistry:
    """子代理注册中心"""

    _BUILTIN_SPECS = {
        "xiaohuangmen": SubagentSpec(
            name="xiaohuangmen",
            display_name="通传小黄门",
            description="轻量只读，适合短命令、快速确认、跑腿探路",
            allowed_tools=["read_file", "glob", "grep", "web_fetch"],
            max_turns=5,
            model_role="secondary"
        ),
        "sili_suitang": SubagentSpec(
            name="sili_suitang",
            display_name="司礼监随堂",
            description="只读文书，适合阅读代码、查阅文档、整理提纲",
            allowed_tools=["read_file", "glob", "grep", "web_fetch", "load_skill"],
            max_turns=10,
            model_role="secondary",
            read_only=True
        ),
        "dongchang_tanshi": SubagentSpec(
            name="dongchang_tanshi",
            display_name="东厂探事",
            description="只读查访，适合抓网页、查资料、探索性搜索",
            allowed_tools=["web_fetch", "glob", "grep", "load_skill"],
            max_turns=30,
            model_role="secondary",
            read_only=True
        ),
        "shangbao_dianbu": SubagentSpec(
            name="shangbao_dianbu",
            display_name="尚宝监典簿",
            description="只读核验，适合盘点文件、校对清单、检查遗漏",
            allowed_tools=["read_file", "glob", "grep"],
            max_turns=20,
            model_role="secondary",
            read_only=True
        ),
        "neiguan_yingzao": SubagentSpec(
            name="neiguan_yingzao",
            display_name="内官监营造",
            description="可读写、可执行命令，适合修改文件、搭建工程、跑命令验收",
            allowed_tools=["read_file", "write_file", "edit_file", "run_command", "glob", "grep"],
            max_turns=100,
            model_role="main"
        ),
        # 兼容别名
        "researcher": SubagentSpec(
            name="researcher",
            display_name="研究员",
            description="别名：东厂探事",
            allowed_tools=["web_fetch", "glob", "grep", "load_skill"],
            max_turns=30,
            model_role="secondary",
            read_only=True
        ),
        "reader": SubagentSpec(
            name="reader",
            display_name="阅读员",
            description="别名：司礼监随堂",
            allowed_tools=["read_file", "glob", "grep", "web_fetch", "load_skill"],
            max_turns=10,
            model_role="secondary",
            read_only=True
        ),
        "coder": SubagentSpec(
            name="coder",
            display_name="工程师",
            description="别名：内官监营造",
            allowed_tools=["read_file", "write_file", "edit_file", "run_command", "glob", "grep"],
            max_turns=100,
            model_role="main"
        )
    }

    # 别名映射
    _ALIASES = {
        "general": "neiguan_yingzao",
        "researcher": "dongchang_tanshi",
        "reader": "sili_suitang",
        "coder": "neiguan_yingzao"
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
            if spec.name not in cls._ALIASES  # 不显示别名
        ]

    @classmethod
    def validate_tool_access(cls, agent_type: str, tool_name: str) -> bool:
        """验证工具访问权限"""
        spec = cls.get_spec(agent_type)
        if not spec:
            return False
        return tool_name in spec.allowed_tools
