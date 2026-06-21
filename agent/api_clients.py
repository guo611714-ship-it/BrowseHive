"""Consolidated thin wrapper API clients (VolcEngine, DeepSeek, Doubao).

Previously these lived in separate root-level files:
  volcengine_client.py, deepseek_client.py, doubao_client.py
All three inherit from OpenAICompatClient with provider-specific defaults.
"""

import os
from typing import Optional
from agent.api_client import OpenAICompatClient


class VolcEngineClient(OpenAICompatClient):
    """火山引擎 API 客户端."""

    def __init__(self, api_key=None, base_url=None, model=None):
        super().__init__(
            api_key=api_key or os.environ.get("VOLCENGINE_API_KEY", ""),
            base_url=base_url or os.environ.get(
                "VOLCENGINE_BASE_URL",
                "https://ark.cn-beijing.volces.com/api/v3",
            ),
            model=model or os.environ.get("VOLCENGINE_MODEL", "volcano-ai"),
            completions_path="/chat/completions",
        )


class DeepSeekClient(OpenAICompatClient):
    """DeepSeek API 客户端（OpenAI兼容接口）."""

    def __init__(self, api_key=None, base_url=None, model=None):
        super().__init__(
            api_key=api_key or os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=base_url or os.environ.get(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com",
            ),
            model=model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )


class DoubaoClient(OpenAICompatClient):
    """豆包 API 客户端（火山引擎兼容接口）."""

    def __init__(self, api_key=None, base_url=None, model=None):
        super().__init__(
            api_key=api_key or os.environ.get("DOUBAO_API_KEY", ""),
            base_url=base_url or os.environ.get(
                "DOUBAO_BASE_URL",
                "https://ark.doubao.com",
            ),
            model=model or os.environ.get("DOUBAO_MODEL", "doubao-1-5-pro"),
        )
