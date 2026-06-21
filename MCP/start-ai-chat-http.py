#!/usr/bin/env python3
"""AI Chat MCP - Streamable HTTP 常驻服务.

基于 MCP 2025-03-26 规范的 Streamable HTTP 传输。
多个 Claude 会话共享同一个实例。

用法: python start-ai-chat-http.py
端口: 8090 (可通过 MCP_PORT 环境变量修改)
端点: http://127.0.0.1:8090/mcp
"""

import os
import sys
import importlib.util

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUNBUFFERED"] = "1"

# 导入 ai-chat-mcp 模块
script_dir = os.path.join(os.path.dirname(__file__), "scripts")
spec = importlib.util.spec_from_file_location("ai_chat_mcp", os.path.join(script_dir, "ai-chat-mcp.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

port = int(os.environ.get("MCP_PORT", "8090"))
mod.mcp.settings.port = port

print(f"[ai-chat] Streamable HTTP on http://127.0.0.1:{port}/mcp", file=sys.stderr)
mod.mcp.run(transport="streamable-http")
