"""LLM 客户端抽象 - 支持多供应商"""

import os
import json
import httpx
from typing import Dict, Any, Optional, List
from pathlib import Path


class LLMClient:
    """统一 LLM 接口"""

    def __init__(self, provider: str, model: str, api_key: str, api_base: Optional[str] = None,
                 max_tokens: int = 20000, temperature: float = 0.1):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def chat(self, messages: List[Dict[str, Any]], system: Optional[str] = None,
                   tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """调用聊天接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            system: 系统提示
            tools: 工具定义（可选）

        Returns:
            {"content": "...", "usage": {...}}
        """
        if not self.api_key:
            return {
                "content": "[配置缺失] 请在 model_config.json 中配置 API Key",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        if self.provider == "deepseek":
            return await self._call_deepseek(messages, system, tools)
        elif self.provider == "anthropic":
            return await self._call_anthropic(messages, system, tools)
        elif self.provider in ("openai", "nvidia"):
            # NVIDIA NIM 使用 OpenAI 兼容 API
            return await self._call_openai(messages, system, tools)
        else:
            return {"content": f"[错误] 不支持的 provider: {self.provider}", "usage": {}}

    async def _call_deepseek(self, messages: List, system: Optional[str], tools: Optional[List]) -> Dict:
        """调用 DeepSeek API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }
        if system:
            body["messages"] = [{"role": "system", "content": system}] + body["messages"]
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{self.api_base}/chat/completions", json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            return {"content": f"[网络错误] {type(e).__name__}: {e}", "usage": {}}
        except json.JSONDecodeError as e:
            return {"content": f"[响应错误] 无效的 JSON 响应: {e}", "usage": {}}

        # 安全检查：提取 content
        choices = data.get("choices") or []
        if not choices:
            return {"content": "[API 错误] 响应缺少 choices 字段", "usage": data.get("usage", {})}
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        usage = data.get("usage", {})
        return {"content": content, "usage": usage}

    async def _call_anthropic(self, messages: List, system: Optional[str], tools: Optional[List]) -> Dict:
        """调用 Anthropic Claude API"""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": messages
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        base = self.api_base or "https://api.anthropic.com"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{base}/v1/messages", json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            return {"content": f"[网络错误] {type(e).__name__}: {e}", "usage": {}}
        except json.JSONDecodeError as e:
            return {"content": f"[响应错误] 无效的 JSON 响应: {e}", "usage": {}}

        # 安全检查：提取 content（支持 text 和 tool_use）
        content_list = data.get("content") or []
        if not content_list:
            return {"content": "[API 错误] 响应缺少 content 字段", "usage": data.get("usage", {})}
        # 提取文本内容
        content = ""
        for item in content_list:
            if item.get("type") == "text":
                content += item.get("text", "")
            elif item.get("type") == "tool_use":
                # 对于 tool_use，暂时只记录
                content += f"[工具调用: {item.get('name')}]"
        usage = data.get("usage", {})
        return {"content": content, "usage": usage}

    async def _call_openai(self, messages: List, system: Optional[str], tools: Optional[List]) -> Dict:
        """调用 OpenAI API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        if tools:
            body["tools"] = tools

        base = self.api_base or "https://api.openai.com/v1"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{base}/chat/completions", json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            return {"content": f"[网络错误] {type(e).__name__}: {e}", "usage": {}}
        except json.JSONDecodeError as e:
            return {"content": f"[响应错误] 无效的 JSON 响应: {e}", "usage": {}}

        # 安全检查：提取 content
        choices = data.get("choices") or []
        if not choices:
            return {"content": "[API 错误] 响应缺少 choices 字段", "usage": data.get("usage", {})}
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        usage = data.get("usage", {})
        return {"content": content, "usage": usage}


def load_llm_client_from_config(config_path: Path) -> LLMClient:
    """从 model_config.json 加载 LLM 客户端"""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"model_config.json 格式错误: {e}")
    except FileNotFoundError:
        raise ValueError(f"配置文件未找到: {config_path}")

    defaults = cfg.get("agents", {}).get("defaults", {})
    models = cfg.get("models", [])
    providers = cfg.get("providers", {})

    # 默认使用 agents.defaults 的设置，但优先 provider 里的 apiKey
    model_name = defaults.get("model", "deepseek-work")
    provider_name = defaults.get("provider", "deepseek")

    model_cfg = next((m for m in models if m["name"] == model_name), {})
    provider_cfg = providers.get(provider_name, {})

    # 组合：优先 provider 的 apiKey，其次 model 的 apiKey
    api_key = provider_cfg.get("apiKey") or model_cfg.get("apiKey", "")
    api_base = provider_cfg.get("apiBase") or model_cfg.get("apiBase")

    # 类型安全转换
    max_tokens = defaults.get("maxTokens")
    if max_tokens is None:
        max_tokens = 20000
    else:
        try:
            max_tokens = int(max_tokens)
        except (ValueError, TypeError):
            max_tokens = 20000

    temperature = defaults.get("temperature")
    if temperature is None:
        temperature = 0.1
    else:
        try:
            temperature = float(temperature)
        except (ValueError, TypeError):
            temperature = 0.1

    return LLMClient(
        provider=provider_name,
        model=model_cfg.get("mainModelId", model_name) or model_name,
        api_key=api_key or "",
        api_base=api_base,
        max_tokens=max_tokens,
        temperature=temperature
    )
