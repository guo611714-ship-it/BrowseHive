"""LLM 客户端抽象 - 支持多供应商、多Key轮转、自动重试"""

import json
import httpx
import logging
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path

# 共享限流器 + Key池
from shared import RateLimiter
from shared.api_key_pool import APIKeyPool
from .utils import _parse_retry_after, _error_response

logger = logging.getLogger(__name__)


class LLMClient:
    """统一 LLM 接口"""

    def __init__(self, provider: str, model: str, api_key: str = "", api_base: Optional[str] = None,
                 max_tokens: int = 20000, temperature: float = 0.1,
                 api_keys: Optional[List[str]] = None,
                 timeout_override: Optional[int] = None):
        self.provider = provider
        self.model = model
        self._timeout_override = timeout_override
        self.api_key = api_key
        self.api_base = api_base
        # 动态max_tokens：根据模型能力自动调整
        if max_tokens and max_tokens <= 128:
            self.max_tokens = 4096  # 最低保底，避免截断
        else:
            self.max_tokens = max_tokens or 4096
        self.temperature = temperature

        # 多Key池
        self._key_pool: Optional[APIKeyPool] = None
        if api_keys and api_key and api_key not in api_keys:
            # 独立api_key不在列表中 → 合并去重后构建池
            self._key_pool = APIKeyPool(
                keys=[api_key] + api_keys, provider=provider,
                interval=2.0, window=60, max_requests=8, account_max_requests=60
            )
        elif api_keys and len(api_keys) > 1:
            self._key_pool = APIKeyPool(
                keys=api_keys, provider=provider,
                interval=2.0, window=60, max_requests=8, account_max_requests=60
            )
        elif api_keys and not api_key:
            self.api_key = api_keys[0]

        # 单Key限流（仅pool不存在时使用）
        self._rate_limiter = RateLimiter(interval=2.0, window=60, max_requests=8)

        # 持久化HTTP客户端（连接池复用）
        self._http_client = httpx.AsyncClient(timeout=120)

    async def aclose(self):
        """关闭底层HTTP客户端，释放连接池资源"""
        if self._http_client:
            await self._http_client.aclose()

    def __del__(self):
        """安全兜底：确保HTTP客户端被关闭（仅在aclose未被调用时触发）"""
        if getattr(self, "_http_client", None) and not self._http_client.is_closed:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.aclose())
                else:
                    loop.run_until_complete(self.aclose())
            except Exception as e:
                logger.debug("LLMClient cleanup failed: %s", e)
                import warnings
                warnings.warn(
                    "LLMClient was deleted without calling aclose(). "
                    "Always use 'await client.aclose()' or 'async with' pattern.",
                    ResourceWarning, stacklevel=2
                )

    async def _get_api_key(self) -> Optional[str]:
        if self._key_pool:
            return await self._key_pool.next_key_async()
        return self.api_key

    def _report_result(self, key: Optional[str], status_code: int, retry_after: float = 30.0):
        """向Key池报告请求结果，429/401/403/5xx自动禁用Key"""
        if self._key_pool and key:
            if status_code == 429:
                self._key_pool.report_429(key, retry_after=retry_after)
            elif status_code in (401, 403):
                self._key_pool.report_auth_failure(key)
            elif status_code >= 500:
                # 5xx服务器错误：短暂禁用（可能是限流或过载）
                self._key_pool.report_429(key, retry_after=min(retry_after, 15.0))
            elif status_code < 400:
                self._key_pool.report_success(key)

    async def chat(self, messages: List[Dict[str, Any]], system: Optional[str] = None,
                   tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """调用聊天接口（自动重试 + Key切换）"""
        api_key = await self._get_api_key()
        if not api_key:
            return _error_response("[限流] 所有API Key均不可用，请稍后重试")

        # 单Key限流检查
        if not self._key_pool:
            rate_msg = self._rate_limiter.check(self.provider)
            if rate_msg:
                return _error_response(rate_msg)

        # 重试逻辑：429自动切换Key，最多重试3次
        from .model_orchestrator import DEFAULT_MODEL_SPEED_TIERS
        for attempt in range(3):
            # 动态超时：根据模型速度等级调整（快30s/中60s/慢120s）
            if self._timeout_override:
                timeout = self._timeout_override
            else:
                try:
                    timeout = DEFAULT_MODEL_SPEED_TIERS.get(self.model, 60)
                except ImportError:
                    timeout = 60
            try:
                result = await asyncio.wait_for(
                    self._dispatch(messages, system, tools, api_key),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                result = _error_response(f"[超时] LLM调用超过{timeout}秒")
                logger.warning(f"LLM调用超时 {timeout}s (attempt {attempt+1}, model={self.model})")
            status_code = result.get("status_code", 200)

            if status_code == 429:
                if self._key_pool:
                    # 最后一次迭代：peek而不check，避免phantom timestamp
                    if attempt < 2:
                        api_key = await self._get_api_key()
                    else:
                        api_key = await self._key_pool.peek_key_async()
                    if not api_key:
                        break
                    await asyncio.sleep(2.0)
                    continue
                # 单Key模式：指数退避重试
                delay = 2.0 * (2 ** attempt)
                logger.warning(f"429限流, 单Key退避重试 ({attempt+1}/3, 等待{delay:.0f}s)")
                await asyncio.sleep(delay)
                continue

            if status_code in (401, 403):
                # 认证失败：尝试切换Key
                if self._key_pool:
                    api_key = await self._get_api_key()
                    if not api_key:
                        break
                    continue
                # 单Key模式：不重试
                break

            break  # 成功或其他错误，直接返回

        return result

    async def _dispatch(self, messages, system, tools, api_key: str) -> Dict:
        """路由到对应provider"""
        base = self.api_base
        if self.provider == "deepseek":
            base = base or "https://api.deepseek.com/v1"
            return await self._call_openai(messages, system, tools, api_key, base)
        elif self.provider == "anthropic":
            return await self._call_anthropic(messages, system, tools, api_key)
        elif self.provider in ("openai", "nvidia"):
            return await self._call_openai(messages, system, tools, api_key, base)
        else:
            return _error_response(f"[错误] 不支持的 provider: {self.provider}")

    async def _call_openai(self, messages: List, system: Optional[str], tools: Optional[List],
                           api_key: str, base: str) -> Dict:
        """调用 OpenAI 兼容 API"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        body = {
            "model": self.model,
            "messages": full_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        base = base or "https://api.openai.com/v1"
        try:
            resp = await self._http_client.post(f"{base}/chat/completions", json=body, headers=headers)

            retry_after = _parse_retry_after(resp.headers)
            self._report_result(api_key, resp.status_code, retry_after)

            # 429 透传（结构化status_code，不做字符串匹配）
            if resp.status_code == 429:
                return _error_response("[429] Too Many Requests", 429)

            # 400 + tools -> 模型不支持 tool calling
            if resp.status_code == 400 and tools:
                body_no_tools = {k: v for k, v in body.items() if k not in ("tools", "tool_choice")}
                resp = await self._http_client.post(f"{base}/chat/completions", json=body_no_tools, headers=headers)
                retry_after = _parse_retry_after(resp.headers)
                self._report_result(api_key, resp.status_code, retry_after)
                if resp.status_code == 429:
                    return _error_response("[429] Too Many Requests", 429)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            return _error_response(f"[网络错误] {type(e).__name__}: {e}")
        except json.JSONDecodeError as e:
            return _error_response(f"[响应错误] 无效的 JSON 响应: {e}")

        choices = data.get("choices") or []
        if not choices:
            return {"content": "[API 错误] 响应缺少 choices 字段", "usage": data.get("usage", {}),
                    "tool_calls": [], "status_code": resp.status_code}

        message = choices[0].get("message") or {}
        content = message.get("content", "") or ""
        usage = data.get("usage", {})
        finish_reason = choices[0].get("finish_reason", "")

        # 输出长度检测：finish_reason='length' 表示响应被截断
        if finish_reason == "length":
            logger.warning(
                f"响应被截断 finish_reason=length, model={self.model}, "
                f"content_len={len(content)}, max_tokens={self.max_tokens}"
            )

        tool_calls = []
        native_calls = message.get("tool_calls") or []
        for tc in native_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({"id": tc.get("id", ""), "name": name, "arguments": args})

        if not tool_calls and content:
            tool_calls = _parse_xml_tool_calls(content)

        return {
            "content": content,
            "usage": usage,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "status_code": resp.status_code
        }

    async def _call_anthropic(self, messages: List, system: Optional[str], tools: Optional[List],
                              api_key: str) -> Dict:
        """调用 Anthropic Claude API"""
        headers = {
            "x-api-key": api_key,
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
            resp = await self._http_client.post(f"{base}/v1/messages", json=body, headers=headers)

            retry_after = _parse_retry_after(resp.headers)
            self._report_result(api_key, resp.status_code, retry_after)

            if resp.status_code == 429:
                return _error_response("[429] Too Many Requests", 429)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            return _error_response(f"[网络错误] {type(e).__name__}: {e}")
        except json.JSONDecodeError as e:
            return _error_response(f"[响应错误] 无效的 JSON 响应: {e}")

        content_list = data.get("content") or []
        if not content_list:
            return {"content": "[API 错误] 响应缺少 content 字段", "usage": data.get("usage", {}),
                    "tool_calls": [], "status_code": resp.status_code}

        content = ""
        tool_calls = []
        for item in content_list:
            if item.get("type") == "text":
                content += item.get("text", "")
            elif item.get("type") == "tool_use":
                tool_calls.append({
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "arguments": item.get("input", {})
                })

        usage = data.get("usage", {})
        # Anthropic truncation: stop_reason='max_tokens' means response was cut off
        stop_reason = data.get("stop_reason", "")
        if stop_reason == "max_tokens":
            logger.warning(
                f"响应被截断 stop_reason=max_tokens, model={self.model}, "
                f"content_len={len(content)}, max_tokens={self.max_tokens}"
            )
        return {
            "content": content,
            "usage": usage,
            "tool_calls": tool_calls,
            "finish_reason": stop_reason,
            "status_code": resp.status_code
        }


def _parse_xml_tool_calls(text: str) -> List[Dict]:
    """从文本中解析 XML 格式的 tool calls（兼容 minimax 等模型）"""
    import re
    calls = []
    pattern = r'<invoke\s+name="([^"]+)"(?:\s+args="([^"]*)")?>(.*?)</invoke>'
    for m in re.finditer(pattern, text, re.DOTALL):
        name = m.group(1)
        args_str = m.group(2) or ""
        params_text = m.group(3) or ""
        args = {}
        for pm in re.finditer(r'<param\s+name="([^"]+)">\s*(.*?)\s*</param>', params_text, re.DOTALL):
            args[pm.group(1)] = pm.group(2).strip()
        if args_str and not args:
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {"raw": args_str}
        calls.append({"id": f"xml_{len(calls)}", "name": name, "arguments": args})
    return calls


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

    model_name = defaults.get("model", "deepseek-work")
    provider_name = defaults.get("provider", "deepseek")

    model_cfg = next((m for m in models if m["name"] == model_name), {})
    provider_cfg = providers.get(provider_name, {})

    api_keys = provider_cfg.get("apiKeys") or []
    api_key = provider_cfg.get("apiKey") or model_cfg.get("apiKey", "")
    if not api_key and api_keys:
        api_key = api_keys[0]
    api_base = provider_cfg.get("apiBase") or model_cfg.get("apiBase")

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
        temperature=temperature,
        api_keys=api_keys or None
    )
