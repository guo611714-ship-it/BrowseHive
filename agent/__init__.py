"""Agent Team 核心包"""

__version__ = "1.0.0"
__author__ = "Claude Code"

# 引擎桥接注入点（Skill 从这里获取引擎实例）
from .dependencies import engine_ctx  # noqa: F401
