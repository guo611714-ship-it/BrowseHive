#!/usr/bin/env python3
"""
Meta MCP Client - 用于非-MCP环境直接调用 Meta MCP 工具

通过 stdio 连接 meta-mcp-server.py，提供简单的同步/异步 API。
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# 添加项目路径
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_MCP_DIR = _PROJECT_ROOT / "MCP" / "scripts"
sys.path.insert(0, str(_MCP_DIR))

from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession


class MetaMCPClient:
    """同步/异步 Meta MCP 客户端."""

    def __init__(
        self,
        python_exe: str = None,
        meta_script: str = None,
        env: Dict[str, str] = None,
        timeout: int = 30
    ):
        self.python_exe = python_exe or sys.executable
        self.meta_script = Path(meta_script or _MCP_DIR / "meta-mcp-server.py")
        self.env = env or {"PYTHONIOENCODING": "utf-8"}
        self.timeout = timeout
        self._session: Optional[ClientSession] = None
        self._streams = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            try:
                # 异步close转同步
                asyncio.run(self._aclose())
            except:
                pass

    async def _aclose(self):
        if self._session:
            await self._session.close()
        if self._streams:
            read, write = self._streams
            # stdio_client context manager cleanup
            # 简化：不显式关闭 streams，依赖上下文

    async def connect(self):
        """连接到 Meta MCP Server."""
        self._streams = await stdio_client(
            command=self.python_exe,
            args=[str(self.meta_script)],
            env={**os.environ, **self.env}
        ).__aenter__()
        read_stream, write_stream = self._streams
        self._session = ClientSession(read_stream, write_stream)
        await asyncio.wait_for(self._session.initialize(), timeout=self.timeout)

    def ensure_connected(self):
        if not self._session:
            asyncio.run(self.connect())

    def list_tools(self) -> Dict:
        """列出所有可用工具."""
        self.ensure_connected()
        result = asyncio.run(self._session.list_tools())
        return {"tools": [{"name": t.name, "description": t.description} for t in result.tools]}

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: int = None) -> Dict:
        """调用工具."""
        self.ensure_connected()
        timeout = timeout or self.timeout
        result = asyncio.run(asyncio.wait_for(
            self._session.call_tool(tool_name, arguments),
            timeout=timeout
        ))
        content = []
        for item in result.content:
            if hasattr(item, 'text'):
                content.append(item.text)
            elif hasattr(item, 'data'):
                content.append(item.data)
            else:
                content.append(str(item))
        return {
            "success": not result.isError,
            "content": content,
            "error": result.errorMessage if result.isError else None
        }

    # 便捷方法：常用工具
    def ask_doubao(self, message: str, timeout: int = 120) -> str:
        res = self.call_tool("ask_doubao", {"message": message, "timeout": timeout})
        if res["success"]:
            return res["content"][0] if res["content"] else ""
        raise RuntimeError(res["error"])

    def ask_deepseek(self, message: str, timeout: int = 120) -> str:
        res = self.call_tool("ask_deepseek", {"message": message, "timeout": timeout})
        if res["success"]:
            return res["content"][0] if res["content"] else ""
        raise RuntimeError(res["error"])

    def smart_ask(self, message: str, timeout: int = 120) -> str:
        res = self.call_tool("smart_ask", {"message": message, "timeout": timeout})
        if res["success"]:
            return res["content"][0] if res["content"] else ""
        raise RuntimeError(res["error"])

    def batch_ask(self, message: str, platforms: str = "doubao,deepseek", timeout: int = 120) -> str:
        res = self.call_tool("batch_ask", {"message": message, "platforms": platforms, "timeout": timeout})
        if res["success"]:
            return res["content"][0] if res["content"] else ""
        raise RuntimeError(res["error"])

    def process_pdf(self, pdf_path: str, query: str) -> str:
        res = self.call_tool("process_pdf", {"pdf_path": pdf_path, "query": query})
        if res["success"]:
            return res["content"][0] if res["content"] else ""
        raise RuntimeError(res["error"])

    def health_check(self) -> Dict:
        res = self.call_tool("health_check", {})
        if res["success"]:
            import json
            return json.loads(res["content"][0]) if res["content"] else {}
        raise RuntimeError(res["error"])

    def get_cache_stats(self) -> Dict:
        res = self.call_tool("get_cache_stats", {})
        if res["success"]:
            import json
            return json.loads(res["content"][0]) if res["content"] else {}
        raise RuntimeError(res["error"])


# 快速测试
if __name__ == "__main__":
    with MetaMCPClient() as client:
        tools = client.list_tools()
        print(f"发现 {len(tools['tools'])} 个工具")
        # 示例调用
        # print(client.ask_deepseek("你好，请用一句话介绍量子计算"))
