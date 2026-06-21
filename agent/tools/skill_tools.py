"""技能系统工具"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import re


def load_skill(skill_name: str) -> Dict[str, Any]:
    """
    加载技能定义

    Args:
        skill_name: 技能名称

    Returns:
        {"name": "...", "description": "...", "prompt": "...", "triggers": [...]}
    """
    skills_dir = Path("skills")
    skill_file = skills_dir / skill_name / "SKILL.md"

    if not skill_file.exists():
        return {"error": f"Skill not found: {skill_name}"}

    try:
        content = skill_file.read_text(encoding="utf-8")

        # 解析 YAML frontmatter
        match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        if not match:
            return {"error": "Invalid SKILL.md format"}

        frontmatter = yaml.safe_load(match.group(1))
        body = match.group(2)

        return {
            "name": skill_name,
            "description": frontmatter.get("description", ""),
            "triggers": frontmatter.get("triggers", []),
            "prompt": body[:5000]  # 限制大小
        }
    except Exception as e:
        return {"error": str(e)}


def list_skills() -> List[Dict]:
    """列出所有可用技能"""
    skills_dir = Path("skills")
    if not skills_dir.exists():
        return []

    skills = []
    for skill_path in skills_dir.iterdir():
        if skill_path.is_dir():
            skill_file = skill_path / "SKILL.md"
            if skill_file.exists():
                skills.append({
                    "name": skill_path.name,
                    "path": str(skill_path)
                })

    return skills


# 内置技能注册表（如果 skills/ 不存在则使用这些）
BUILTIN_SKILLS = {
    "clawhub": {
        "description": "技能库搜寻与安装",
        "prompt": "你可以通过 clawhub 搜索、安装和管理技能包。"
    },
    "ddg-web-search": {
        "description": "DuckDuckGo 搜索",
        "prompt": "使用 ddg-web-search 进行网络搜索。"
    },
    "github": {
        "description": "GitHub CLI 交互",
        "prompt": "通过 GitHub CLI 操作仓库、issues、PR。"
    },
    "skill-creator": {
        "description": "创建或更新技能",
        "prompt": "帮助用户创建新的 SKILL.md 或修改现有技能。"
    },
    "summarize": {
        "description": "URL、播客、文件总结",
        "prompt": "对 URL、文件或文本进行内容总结。"
    },
    "weather": {
        "description": "天气查询",
        "prompt": "查询指定城市的天气信息。"
    }
}