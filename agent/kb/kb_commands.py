"""kb_commands.py - CLI command implementations for Knowledge Base Manager

All user-facing commands via KBCommandsMixin: list, query, import, graph,
classify, version, sync, backup, cache management.

This file is now a thin re-export facade. The actual implementations live
in agent/kb/commands/ sub-modules.
"""

from .commands import KBCommandsMixin

__all__ = ["KBCommandsMixin"]
