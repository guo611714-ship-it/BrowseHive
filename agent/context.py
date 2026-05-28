"""System Prompt 组装器（Jinja2 模板）"""

from pathlib import Path
from typing import Dict, Any, List


class ContextAssembler:
    """上下文组装器"""

    def __init__(self, templates_dir: Path = Path("templates")):
        self.templates_dir = Path(templates_dir)

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """简单 Jinja2-like 模板渲染（无外部依赖）"""
        template_file = self.templates_dir / template_name
        if not template_file.exists():
            return ""

        template = template_file.read_text(encoding="utf-8")

        # 极简模板替换（仅支持 {{ variable }} 语法）
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, list):
                # 列表转 Markdown
                if key == "tools_section":
                    rendered = "### 内置工具\n\n"
                    for tool in value:
                        rendered += f"- `{tool}`\n"
                elif key == "skills_section":
                    rendered = "### 技能列表\n\n"
                    for skill in value:
                        rendered += f"- **{skill.get('name', 'Unknown')}**: {skill.get('description', '')}\n"
                elif key == "subagents_section":
                    rendered = "### 可用子代理\n\n"
                    for agent in value:
                        rendered += f"- **{agent.get('name', '')}**: {agent.get('description', '')}\n"
                elif key == "team_section":
                    rendered = "### Team 队友\n\n"
                    for tm in value:
                        rendered += f"- **{tm.get('name', '')}** ({tm.get('role', '')}): {tm.get('description', '')}\n"
                else:
                    rendered = "\n".join([f"- {item}" for item in value])
            elif isinstance(value, str):
                rendered = value
            else:
                rendered = str(value)

            template = template.replace(placeholder, rendered)

        return template

    def build_system_prompt(self, **kwargs) -> str:
        """组装完整的 system prompt"""
        parts = []

        # 1. SOUL（灵魂档案）
        soul_path = self.templates_dir / "SOUL.md"
        if soul_path.exists():
            parts.append(soul_path.read_text(encoding="utf-8"))

        # 2. 身份模板（包含工具、技能、子代理、队友、记忆、用户、历史、工作区）
        tools = kwargs.get("tools", [])
        skills = kwargs.get("skills", [])
        subagents = kwargs.get("subagents", [])
        team = kwargs.get("team", [])
        memory_ctx = kwargs.get("memory", {})
        user = kwargs.get("user", "")
        history = kwargs.get("history", [])
        workspace = kwargs.get("workspace_path", "")

        # 渲染子节
        tools_section_rendered = self._render_template("agent/tools_section.md", {"tools": tools}) if tools else ""
        skills_section_rendered = self._render_template("agent/skills_section.md", {"skills": skills}) if skills else ""
        subagents_section_rendered = self._render_template("agent/subagents_section.md", {"subagents": subagents}) if subagents else ""
        team_section_rendered = self._render_template("agent/team_section.md", {"team": team}) if team else ""

        memory_section = ""
        if memory_ctx.get("long_term"):
            memory_section += f"### 长期记忆\n{memory_ctx['long_term']}\n\n"
        if memory_ctx.get("user_prefs"):
            memory_section += f"### 用户偏好\n{memory_ctx['user_prefs']}\n\n"

        user_section = ""
        if user:
            user_section = f"### 用户档案\n{user}\n\n"

        history_section = ""
        if history:
            history_section = "### 最近对话\n"
            for msg in history[-10:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_section += f"**{role}**: {content[:200]}...\n\n"

        identity = self._render_template(
            "agent/identity.md",
            {
                "tools_section": tools_section_rendered,
                "skills_section": skills_section_rendered,
                "subagents_section": subagents_section_rendered,
                "team_section": team_section_rendered,
                "memory_section": memory_section,
                "user_section": user_section,
                "history_section": history_section,
                "workspace_path": workspace
            }
        )
        parts.append(identity)

        return "\n".join(parts)
