"""Core modules for AI Chat MCP."""

# 基础配置（无依赖，先导入）
from .config import config

# 平台定义（依赖 config）
from .platforms import PLATFORMS, is_login_page, assess_complexity, detect_task_type

__all__ = [
    "config",
    "PLATFORMS",
    "is_login_page",
    "assess_complexity",
    "detect_task_type",
]

# 复杂模块不自动加载，由调用方按需导入
