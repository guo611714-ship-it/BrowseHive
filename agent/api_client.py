"""OpenAI-compatible API client."""
import os
from typing import Optional, Dict, Any, List
import requests


class OpenAICompatClient:
    """Generic OpenAI-compatible client. Accepts base_url, api_key, model."""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        completions_path: str = "/v1/chat/completions",
    ):
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")
        self.model = model or "default"
        self.completions_path = completions_path
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def chat(self, message: str, system_prompt: str = None, temperature: float = 0.7) -> str:
        """Single message chat."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return self._complete(messages, temperature)

    def chat_with_history(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """Multi-message chat with history."""
        return self._complete(messages, temperature)

    def _complete(self, messages: List[Dict[str, str]], temperature: float) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        url = f"{self.base_url}{self.completions_path}"
        resp = self.session.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
