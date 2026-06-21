# agent_sse/adapters/hermes_adapter.py
"""Hermes API 适配层（支持 SSE 流式）"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, AsyncGenerator, List
from fastapi import Request

from .key_router import KeyRouter
from .field_mapper import FieldMapper
from ..config.routing_config import get_api_keys, get_base_url

logger = logging.getLogger(__name__)


class HermesAdapter:
    """Hermes API 适配层"""

    def __init__(self):
        self.hermes_client = None
        self.fallback_client = None
        self.enable_fallback = True
        self.timeout = 10
        self._initialized = False
        self._key_router = None
        self._registered_tools: Dict[str, Any] = {}  # name -> async callable
        self._memory_store: Dict[str, Any] = {}  # 记忆存储
        self._sub_agents: Dict[str, Any] = {}  # 子代理注册表

    async def initialize(self, workspace_path: Any):
        """初始化适配器"""
        try:
            # 初始化 Key 路由
            api_keys = get_api_keys()
            if not api_keys:
                raise ValueError("未配置 API Key")
            self._key_router = KeyRouter(keys=api_keys, mode="global")

            # 导入 hermes_bridge
            import sys
            from pathlib import Path

            # 使用环境变量或默认路径
            hermes_path = os.environ.get("HERMES_AGENT_PATH")
            if hermes_path:
                agent_path = Path(hermes_path)
            else:
                agent_path = Path(__file__).parent.parent.parent / "agent-team-dashboard" / "agent-team-dashboard" / "dist" / "win-unpacked" / "resources"

            if str(agent_path) not in sys.path:
                sys.path.insert(0, str(agent_path))

            from agent.hermes_bridge import get_hermes_bridge
            self.hermes_client = get_hermes_bridge(workspace_path)

            # 注册所有工具（Agent Team + Hermes 原生）
            self._register_tools()

            self._initialized = True
            logger.info("Hermes 适配器初始化成功, 已注册 %d 个工具", len(self._registered_tools))
        except Exception as e:
            logger.error(f"Hermes 适配器初始化失败: {e}")
            self._initialized = False

    def _register_tools(self):
        """注册所有工具到 Hermes 适配层

        合并来源:
        1. Agent Team TOOL_REGISTRY -- 通过 @tool 装饰器自动注册的工具
        2. Hermes Bridge 原生工具 -- memory/cron/skill 相关工具
        """
        self._registered_tools.clear()

        # --- 来源 1: Agent Team 工具 (TOOL_REGISTRY) ---
        try:
            from agent.tools.tool_registry import TOOL_REGISTRY
            agent_tool_count = 0
            for name, entry in TOOL_REGISTRY.items():
                impl = entry.get("implementation")
                if impl and callable(impl):
                    self._registered_tools[name] = impl
                    agent_tool_count += 1
            logger.info("从 TOOL_REGISTRY 注册 %d 个 Agent Team 工具", agent_tool_count)
        except ImportError:
            logger.warning("TOOL_REGISTRY 不可用，跳过 Agent Team 工具注册")
        except Exception as e:
            logger.error("Agent Team 工具注册失败: %s", e)

        # --- 来源 2: Hermes Bridge 原生工具 ---
        hermes_tool_count = 0
        if self.hermes_client:
            try:
                hermes_tools = self.hermes_client.get_tools()
                for name, impl in hermes_tools.items():
                    if callable(impl):
                        self._registered_tools[name] = impl
                        hermes_tool_count += 1
                logger.info("从 Hermes Bridge 注册 %d 个原生工具", hermes_tool_count)
            except Exception as e:
                logger.error("Hermes Bridge 工具注册失败: %s", e)

        logger.info(
            "工具注册完成: %d 个 Agent Team + %d 个 Hermes = %d 个总计",
            agent_tool_count, hermes_tool_count, len(self._registered_tools),
        )

    def get_registered_tools(self) -> Dict[str, Any]:
        """获取已注册工具的名称 -> 实现映射"""
        return dict(self._registered_tools)

    # ── Task 9: tool_loop 替换 ──────────────────────────────────────

    async def execute_tool_loop(self, tool_name: str, args: Dict, context: Dict) -> Dict:
        """替换 tool_loop.py 的工具调用逻辑

        优先级:
        1. 已注册工具（Agent Team + Hermes 原生）
        2. Hermes 远程调用
        """
        # 优先使用已注册的工具
        if tool_name in self._registered_tools:
            try:
                result = await asyncio.wait_for(
                    self._registered_tools[tool_name](**args) if args else self._registered_tools[tool_name](),
                    timeout=self.timeout
                )
                return {"status": "success", "output": result}
            except asyncio.TimeoutError:
                logger.warning("工具 %s 执行超时 (%ds)", tool_name, self.timeout)
                return {"error": f"工具 {tool_name} 执行超时", "code": 408}
            except Exception as e:
                logger.error("工具 %s 执行失败: %s", tool_name, e)
                return {"error": str(e), "code": 500}

        # 否则调用 Hermes
        return await self.execute_tool(tool_name, args, context)

    # ── Task 12: 记忆系统替换 ──────────────────────────────────────

    async def memory_store(self, key: str, value: Any, namespace: str = "default") -> bool:
        """存储记忆条目"""
        ns = self._memory_store.setdefault(namespace, {})
        ns[key] = value
        logger.debug("记忆存储: [%s] %s", namespace, key)
        return True

    async def memory_retrieve(self, key: str, namespace: str = "default") -> Optional[Any]:
        """检索记忆条目"""
        ns = self._memory_store.get(namespace, {})
        value = ns.get(key)
        if value is not None:
            logger.debug("记忆命中: [%s] %s", namespace, key)
        return value

    async def memory_search(self, query: str, namespace: str = "default", limit: int = 10) -> List[Dict]:
        """搜索记忆（简单关键词匹配）"""
        ns = self._memory_store.get(namespace, {})
        results = []
        query_lower = query.lower()
        for key, value in ns.items():
            if query_lower in key.lower() or (isinstance(value, str) and query_lower in value.lower()):
                results.append({"key": key, "value": value, "namespace": namespace})
                if len(results) >= limit:
                    break
        return results

    async def memory_delete(self, key: str, namespace: str = "default") -> bool:
        """删除记忆条目"""
        ns = self._memory_store.get(namespace, {})
        if key in ns:
            del ns[key]
            logger.debug("记忆删除: [%s] %s", namespace, key)
            return True
        return False

    # ── Task 13: 子代理替换 ──────────────────────────────────────

    def register_sub_agent(self, name: str, agent: Any) -> None:
        """注册子代理"""
        self._sub_agents[name] = agent
        logger.info("子代理注册: %s", name)

    def get_sub_agent(self, name: str) -> Optional[Any]:
        """获取子代理"""
        return self._sub_agents.get(name)

    async def spawn_sub_agent(self, name: str, task: str, context: Optional[Dict] = None) -> Dict:
        """创建并执行子代理任务"""
        agent = self._sub_agents.get(name)
        if agent is None:
            return {"error": f"子代理 {name} 未注册", "code": 404}

        try:
            result = await asyncio.wait_for(
                agent.run(task, context or {}),
                timeout=self.timeout * 3
            )
            return {"status": "success", "agent": name, "result": result}
        except asyncio.TimeoutError:
            logger.warning("子代理 %s 执行超时", name)
            return {"error": f"子代理 {name} 执行超时", "code": 408}
        except Exception as e:
            logger.error("子代理 %s 执行失败: %s", name, e)
            return {"error": str(e), "code": 500}

    async def list_sub_agents(self) -> Dict[str, str]:
        """列出所有已注册子代理"""
        return {name: type(agent).__name__ for name, agent in self._sub_agents.items()}

    async def chat_stream(self, request: Request) -> AsyncGenerator[str, None]:
        """流式对话接口，透传 Hermes 的 SSE 输出"""
        if not self._initialized:
            yield FieldMapper.map_sse_error("Hermes 未初始化", 500)
            return

        # 获取 Key
        key = self._key_router.get_next_key()

        try:
            # 字段映射：请求
            old_request = await request.json()
            hermes_request = FieldMapper.map_chat_request(old_request)

            # 调用 Hermes 流式接口
            async for chunk in self._hermes_chat_stream(hermes_request, key):
                yield chunk

            self._key_router.report_success(key)
        except Exception as e:
            self._key_router.report_failure(key)

            if self.enable_fallback and self.fallback_client:
                async for chunk in self.fallback_client.chat_stream(request):
                    yield chunk
            else:
                yield FieldMapper.map_sse_error("服务暂时不可用", 500)

    async def chat(self, message: str) -> str:
        """非流式对话接口"""
        if not self._initialized:
            return FieldMapper.map_sse_error("Hermes 未初始化", 500)

        # 获取 Key
        key = self._key_router.get_next_key()

        try:
            result = await asyncio.wait_for(
                self._hermes_chat({"prompt": message}, key),
                timeout=self.timeout
            )

            if not result:
                raise ValueError("Hermes 返回空结果")

            self._key_router.report_success(key)
            # 字段映射：响应
            return str(FieldMapper.map_chat_response(result))
        except Exception as e:
            self._key_router.report_failure(key)

            if self.enable_fallback and self.fallback_client:
                return await self.fallback_client.chat(message)
            raise

    async def execute_tool(self, tool_name: str, args: Dict, context: Dict) -> Dict:
        """工具调用接口

        按优先级路由:
        1. 已注册工具（Agent Team + Hermes 原生）
        2. Hermes 远程调用
        3. Fallback 客户端
        """
        if not self._initialized:
            return {"error": "Hermes 未初始化", "code": 500}

        # 优先: 从已注册工具中查找并直接调用
        impl = self._registered_tools.get(tool_name)
        if impl:
            try:
                result = await asyncio.wait_for(
                    impl(**args) if args else impl(),
                    timeout=self.timeout
                )
                return {"status": "success", "output": result}
            except asyncio.TimeoutError:
                logger.warning("工具 %s 执行超时 (%ds)", tool_name, self.timeout)
                return {"error": f"工具 {tool_name} 执行超时", "code": 408}
            except Exception as e:
                logger.error("工具 %s 执行失败: %s", tool_name, e)
                return {"error": str(e), "code": 500}

        # 降级: Hermes 远程调用
        key = self._key_router.get_next_key()
        try:
            hermes_request = FieldMapper.map_tool_request({
                "tool": tool_name,
                "args": args,
                "context": context
            })

            result = await asyncio.wait_for(
                self._hermes_execute_tool(hermes_request, key),
                timeout=self.timeout
            )

            if not result or not isinstance(result, dict):
                raise ValueError("Hermes 工具返回结果异常")

            self._key_router.report_success(key)
            return FieldMapper.map_tool_response(result)
        except Exception as e:
            self._key_router.report_failure(key)

            if self.enable_fallback and self.fallback_client:
                return await self.fallback_client.execute_tool(tool_name, args, context)
            raise

    async def _hermes_chat_stream(self, request: Dict, key: str) -> AsyncGenerator[str, None]:
        """Hermes 流式调用"""
        # TODO: 实现 Hermes 流式调用
        yield f'data: {{"delta": "test"}}\n\n'

    async def _hermes_chat(self, request: Dict, key: str) -> Dict:
        """Hermes 非流式调用"""
        # TODO: 实现 Hermes 非流式调用
        return {"response": "test", "stop_reason": "stop"}

    async def _hermes_execute_tool(self, request: Dict, key: str) -> Dict:
        """Hermes 工具调用"""
        # TODO: 实现 Hermes 工具调用
        return {"status": "success", "output": "test"}


# 全局实例
hermes_adapter = HermesAdapter()
