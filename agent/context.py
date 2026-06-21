"""System Prompt 组装器（Jinja2 模板）"""

from pathlib import Path
from typing import Dict, Any, List


class ContextAssembler:
    """上下文组装器"""

    def __init__(self, templates_dir: Path = Path("templates")):
        self.templates_dir = Path(templates_dir)
        self._cache: Dict[str, str] = {}
        self._cache_mtime: Dict[str, float] = {}

    def invalidate_cache(self):
        """手动清除模板缓存"""
        self._cache.clear()
        self._cache_mtime.clear()

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """简单 Jinja2-like 模板渲染（无外部依赖）"""
        template_file = self.templates_dir / template_name
        if not template_file.exists():
            return ""

        # 检查缓存（按文件修改时间判断是否失效）
        cache_key = template_name
        current_mtime = template_file.stat().st_mtime
        if cache_key in self._cache and self._cache_mtime.get(cache_key) == current_mtime:
            template = self._cache[cache_key]
        else:
            template = template_file.read_text(encoding="utf-8")
            self._cache[cache_key] = template
            self._cache_mtime[cache_key] = current_mtime

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

            # 支持有无空格的占位符: {{ key }} 和 {{key}}
            placeholder_spaced = f"{{{{ {key} }}}}"
            placeholder_plain = f"{{{{{key}}}}}"
            template = template.replace(placeholder_spaced, rendered)
            template = template.replace(placeholder_plain, rendered)

        return template

    def build_system_prompt(self, **kwargs) -> str:
        """组装完整的 system prompt"""
        parts = []

        # 1. SOUL（灵魂档案）
        soul_path = self.templates_dir / "SOUL.md"
        if soul_path.exists():
            soul_cache_key = "__soul__"
            soul_mtime = soul_path.stat().st_mtime
            if soul_cache_key in self._cache and self._cache_mtime.get(soul_cache_key) == soul_mtime:
                parts.append(self._cache[soul_cache_key])
            else:
                soul_content = soul_path.read_text(encoding="utf-8")
                self._cache[soul_cache_key] = soul_content
                self._cache_mtime[soul_cache_key] = soul_mtime
                parts.append(soul_content)

        # 2. 身份模板（包含工具、技能、子代理、队友、记忆、用户、历史、工作区）
        memory_ctx = kwargs.get("memory", {})
        user = kwargs.get("user", "")
        history = kwargs.get("history", [])
        workspace = kwargs.get("workspace_path", "")

        # 构建非列表节
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

        # 传递原始列表，由 _render_template 统一渲染格式
        identity = self._render_template(
            "agent/identity.md",
            {
                "tools_section": kwargs.get("tools", []),
                "skills_section": kwargs.get("skills", []),
                "subagents_section": kwargs.get("subagents", []),
                "team_section": kwargs.get("team", []),
                "memory_section": memory_section,
                "user_section": user_section,
                "history_section": history_section,
                "workspace_path": workspace
            }
        )
        parts.append(identity)

        return "\n".join(parts)
