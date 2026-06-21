#!/usr/bin/env python3
"""
Meta MCP Server - BrowseHive 统一入口

动态代理所有子 MCP 的工具（ai-chat、browser-use、chrome-devtools）。
无需硬编码工具列表，自动发现并注册。
"""

import sys
import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp import Tool
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

# 配置
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_MCP_DIR = _PROJECT_ROOT / "MCP" / "scripts"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("meta-mcp")


class SubMCPServer:
    """子 MCP 服务器客户端."""

    def __init__(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._stdio_cm = None
        self.read_stream = None
        self.write_stream = None
        self.session: Optional[ClientSession] = None

    async def start(self) -> bool:
        try:
            logger.info(f"[{self.name}] 启动子进程...")
            env = os.environ.copy()
            env.update(self.env)

            params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=env,
                encoding="utf-8"
            )
            self._stdio_cm = stdio_client(params)
            self.read_stream, self.write_stream = await self._stdio_cm.__aenter__()
            self.session = ClientSession(self.read_stream, self.write_stream)
            # 等待子服务器初始化完成
            await asyncio.wait_for(self.session.initialize(), timeout=30.0)
            logger.info(f"已连接子 MCP: {self.name}")
            return True
        except Exception as e:
            logger.error(f"连接 {self.name} 失败: {e}", exc_info=True)
            await self._cleanup()
            return False

    def is_running(self) -> bool:
        return self.session is not None

    async def list_tools(self) -> List[Dict]:
        if not self.session:
            return []
        try:
            result = await self.session.list_tools()
            return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in result.tools]
        except Exception as e:
            logger.error(f"列出 {self.name} 工具失败: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self.session:
            return {"success": False, "error": f"{self.name} not connected"}
        try:
            result = await self.session.call_tool(tool_name, arguments)
            contents = []
            for item in result.content:
                if hasattr(item, 'text'):
                    contents.append(item.text)
                elif hasattr(item, 'data'):
                    contents.append(item.data)
                else:
                    contents.append(str(item))
            return {"success": not result.isError, "content": contents, "error": result.errorMessage if result.isError else None}
        except Exception as e:
            logger.error(f"调用 {self.name}.{tool_name} 失败: {e}")
            return {"success": False, "error": str(e)}

    async def _cleanup(self):
        if self.session:
            try:
                await self.session.close()
            except:
                pass
            self.session = None
        self.read_stream = None
        self.write_stream = None

    async def stop(self):
        await self._cleanup()
        if self._stdio_cm:
            try:
                await self._stdio_cm.__aexit__(None, None, None)
            except:
                pass
            self._stdio_cm = None
        logger.info(f"已停止子 MCP: {self.name}")


class MetaManager:
    """管理子 MCP 服务器，动态代理工具."""

    def __init__(self):
        self.sub_servers: Dict[str, SubMCPServer] = {}
        self._tool_map: Dict[str, str] = {}  # tool_name -> server_name
        self._load_config()

    def _load_config(self):
        mcp_config_path = _PROJECT_ROOT / ".mcp.json"
        if not mcp_config_path.exists():
            logger.warning(f".mcp.json 未找到，仅使用 ai-chat")
            self.sub_servers['ai-chat'] = SubMCPServer(
                name="ai-chat",
                command=sys.executable,
                args=[str(_MCP_DIR / "ai-chat-mcp.py")],
                env={"AI_CHAT_LOG_LEVEL": "INFO"}
            )
            return

        try:
            with open(mcp_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"解析 .mcp.json 失败: {e}")
            return

        for name, srv_cfg in config.get("mcpServers", {}).items():
            if name not in ["ai-chat", "browser-use", "chrome-devtools"]:
                continue
            command = srv_cfg.get("command")
            args = srv_cfg.get("args", [])
            env = srv_cfg.get("env", {})
            if not command:
                logger.warning(f"服务器 {name} 无命令配置，跳过")
                continue
            self.sub_servers[name] = SubMCPServer(name=name, command=command, args=args, env=env)
            logger.info(f"已加载子 MCP: {name} -> {command}")

    async def ensure(self, name: str) -> bool:
        if name not in self.sub_servers:
            logger.error(f"未知服务器: {name}")
            return False
        server = self.sub_servers[name]
        if server.is_running():
            return True
        logger.info(f"正在启动 {name}...")
        try:
            ok = await asyncio.wait_for(server.start(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning(f"启动 {name} 超时")
            ok = False
        if ok:
            logger.info(f"服务器 {name} 已启动")
        else:
            logger.error(f"启动 {name} 失败")
        return ok

    async def start_all(self) -> bool:
        results = []
        for name, server in self.sub_servers.items():
            try:
                ok = await asyncio.wait_for(server.start(), timeout=30.0)
                results.append((name, ok))
            except asyncio.TimeoutError:
                logger.warning(f"启动 {name} 超时")
                results.append((name, False))
            except Exception as e:
                logger.error(f"启动 {name} 出错: {e}")
                results.append((name, False))
        logger.info(f"子服务器启动结果: {results}")
        return True

    async def stop_all(self):
        tasks = [s.stop() for s in self.sub_servers.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    def get_status(self) -> Dict:
        status = {}
        for name, server in self.sub_servers.items():
            status[name] = {
                "running": server.is_running(),
                "command": server.command,
                "args": server.args
            }
        return status

    async def refresh_tool_map(self):
        """扫描所有子服务器，构建工具名到服务器名的映射."""
        self._tool_map.clear()
        for server_name, server in self.sub_servers.items():
            if not server.is_running():
                continue
            tools = await server.list_tools()
            for tool in tools:
                name = tool["name"]
                if name in self._tool_map:
                    logger.warning(f"工具 '{name}' 在多个服务器中存在，使用第一个")
                else:
                    self._tool_map[name] = server_name
                    # 添加带前缀别名以避免冲突
                    alt_name = f"{server_name}_{name}"
                    if alt_name not in self._tool_map:
                        self._tool_map[alt_name] = server_name

    async def list_all_tools(self) -> List[Dict]:
        await self.refresh_tool_map()
        tools = []
        for tool_name, server_name in self._tool_map.items():
            server = self.sub_servers.get(server_name)
            if server:
                raw_tools = await server.list_tools()
                for t in raw_tools:
                    if t["name"] == tool_name or f"{server_name}_{t['name']}" == tool_name:
                        tools.append({
                            "name": tool_name,
                            "description": f"[{server_name}] {t['description']}",
                            "inputSchema": t["inputSchema"]
                        })
                        break
        return tools

    async def call_any_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """路由工具调用到正确的子服务器."""
        if tool_name not in self._tool_map:
            # 尝试带前缀重试
            for server_name in self.sub_servers:
                if tool_name.startswith(f"{server_name}_"):
                    actual = tool_name[len(server_name)+1:]
                    if actual in [t["name"] for t in await self.sub_servers[server_name].list_tools()]:
                        tool_name = actual
                        break
            else:
                return {"success": False, "error": f"Tool '{tool_name}' not found"}

        server_name = self._tool_map[tool_name]
        server = self.sub_servers.get(server_name)
        if not server:
            return {"success": False, "error": f"Server '{server_name}' not configured"}

        if not await self.ensure(server_name):
            return {"success": False, "error": f"Server '{server_name}' failed to start"}

        # 去除前缀（如果存在）
        actual_tool_name = tool_name
        if "_" in tool_name and tool_name.split("_")[0] in self.sub_servers:
            actual_tool_name = "_".join(tool_name.split("_")[1:])

        return await server.call_tool(actual_tool_name, arguments)

    async def register_dynamic_tools(self, mcp: FastMCP):
        """从子服务器动态发现工具并注册到 Meta MCP."""
        await self.refresh_tool_map()
        registered = 0

        for tool_name, server_name in self._tool_map.items():
            server = self.sub_servers.get(server_name)
            if not server:
                continue
            raw_tools = await server.list_tools()
            raw = None
            for t in raw_tools:
                if t["name"] == tool_name or f"{server_name}_{t['name']}" == tool_name:
                    raw = t
                    break
            if not raw:
                continue

            async def make_wrapper(name, server_name):
                async def wrapper(**kwargs):
                    result = await self.call_any_tool(name, kwargs)
                    if result["success"]:
                        return result["content"][0] if result["content"] else ""
                    raise RuntimeError(result.get("error", "Unknown error"))
                wrapper.__name__ = name
                wrapper.__doc__ = f"[{server_name}] {raw['description']}"
                return wrapper

            try:
                fn = await make_wrapper(tool_name, server_name)
                tool = Tool(
                    name=tool_name,
                    description=f"[{server_name}] {raw['description']}",
                    inputSchema=raw['inputSchema'],
                    fn=fn
                )
                mcp.add_tool(tool)
                registered += 1
                logger.info(f"已注册动态工具: {tool_name} -> {server_name}")
            except Exception as e:
                logger.error(f"注册工具 {tool_name} 失败: {e}")

        logger.info(f"动态工具注册完成: {registered} 个工具")


# 全局 Manager
manager = MetaManager()


@asynccontextmanager
async def server_lifespan(server: FastMCP):
    logger.info("Meta MCP 生命周期: 启动")
    # 启动所有子服务器（start_all 内部已有超时处理）
    await manager.start_all()
    # 动态注册工具（start_all 完成后即可注册，无需额外等待）
    await manager.register_dynamic_tools(server)
    try:
        yield manager
    finally:
        logger.info("Meta MCP 生命周期: 停止")
        await manager.stop_all()


# 创建 MCP 实例（工具在 lifespan 中动态注册）
mcp = FastMCP("BrowseHive Meta MCP", lifespan=server_lifespan)


# 资源定义（保留）
@mcp.resource("config://platforms")
async def config_platforms() -> str:
    config = {
        "platforms": {
            "doubao": {"url": "https://www.doubao.com/chat/", "mode": "expert"},
            "deepseek": {"url": "https://chat.deepseek.com/", "mode": "expert+deep_thinking"},
            "volcengine": {"url": "https://exp.volcengine.com/ark", "model": "Doubao-Seed-2.0-pro"},
            "ouyi": {"url": "https://ai.rcouyi.com/chat/3231313437280773", "mode": "GPT-5-chat-latest"}
        },
        "cdp": {"default_port": 9223}
    }
    return json.dumps(config, indent=2, ensure_ascii=False)


@mcp.resource("status://servers")
async def status_servers() -> str:
    return json.dumps(manager.get_status(), indent=2, ensure_ascii=False)


async def main():
    print("Starting BrowseHive Meta MCP Server...", file=sys.stderr)
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
