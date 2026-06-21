"""Claude/Anthropic API 客户端."""
import os
import json
import requests
from typing import Optional, Dict, Any, List


class AnthropicClient:
    """Anthropic Claude API 客户端（官方接口）."""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7-20250514")
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        })

    def chat(self, message: str, system_prompt: str = None, max_tokens: int = 4096, temperature: float = 0.7) -> str:
        """发送对话消息."""
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": message}]
        }
        if system_prompt:
            payload["system"] = system_prompt
        payload["temperature"] = temperature

        resp = self.session.post(f"{self.base_url}/v1/messages", json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]

    def chat_with_history(self, messages: List[Dict[str, str]], max_tokens: int = 4096, temperature: float = 0.7) -> str:
        """带历史记录的对话."""
        # 转换消息格式为Anthropic格式
        anthropic_messages = []
        system_prompt = None

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages
        }
        if system_prompt:
            payload["system"] = system_prompt
        payload["temperature"] = temperature

        resp = self.session.post(f"{self.base_url}/v1/messages", json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


if __name__ == "__main__":
    client = AnthropicClient()
    print("[Claude API测试]")
    if client.api_key:
        print("API Key: 已配置")
        try:
            result = client.chat("用一句话介绍你自己")
            print(f"回复: {result[:100]}...")
        except Exception as e:
            print(f"错误: {e}")
    else:
        print("API Key未配置，请在.env中设置ANTHROPIC_API_KEY")
