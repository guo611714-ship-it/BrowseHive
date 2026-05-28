"""模型编排器：为每个 Agent 路由到指定模型"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional
from .llm_client import LLMClient, load_llm_client_from_config

logger = logging.getLogger(__name__)


class ModelOrchestrator:
    """模型路由器与客户端池"""

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self._config = self._load_config()
        self._client_cache: Dict[str, LLMClient] = {}
        self._default_model = self._config.get("agents", {}).get("defaults", {}).get("model")
        self._default_provider = self._config.get("agents", {}).get("defaults", {}).get("provider", "openai")

        # 预加载默认模型（仅当配置有效时）
        if self._default_model:
            self._get_or_create_client(self._default_model)

    def _load_config(self) -> Dict:
        """加载 model_config.json"""
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
            return {}
        except (PermissionError, OSError) as e:
            logger.error(f"配置文件读取失败: {e}")
            return {}

    def _get_or_create_client(self, model_name: str) -> Optional[LLMClient]:
        """获取或创建指定模型的 LLM client"""
        if not model_name or not isinstance(model_name, str):
            logger.warning(f"无效的模型名称: {model_name}")
            return None

        if model_name in self._client_cache:
            return self._client_cache[model_name]

        # 查找模型配置
        model_cfg = None
        for m in self._config.get("models", []):
            if m.get("name") == model_name:
                model_cfg = m
                break

        if not model_cfg:
            logger.warning(f"模型 '{model_name}' 未在 config 中配置")
            return None

        provider = model_cfg.get("provider") or self._default_provider
        main_id = model_cfg.get("mainModelId") or model_name
        api_key = model_cfg.get("apiKey")
        api_base = model_cfg.get("apiBase")
        max_tokens = model_cfg.get("maxTokens", 20000)
        if max_tokens is None:
            max_tokens = 20000
        temperature = model_cfg.get("temperature")
        if temperature is None:
            temperature = 0.1

        # 从 provider 配置再读一次 apiKey/apiBase（优先级 provider > model）
        provider_cfg = self._config.get("providers", {}).get(provider, {})
        if not api_key:
            api_key = provider_cfg.get("apiKey", "")
        if not api_base:
            api_base = provider_cfg.get("apiBase")

        client = LLMClient(
            provider=provider,
            model=main_id,
            api_key=api_key,
            api_base=api_base,
            max_tokens=max_tokens,
            temperature=temperature
        )
        self._client_cache[model_name] = client
        return client

    def get_client_for_agent(self, agent_name: str, agent_config: Optional[Dict] = None) -> Optional[LLMClient]:
        """
        根据 agent 配置返回对应的 LLM client。
        若指定的模型不存在，则回退到默认模型。

        Args:
            agent_name: agent 名称（用于日志）
            agent_config: teammate 配置字典，可选。若未提供或模型无效，则使用默认模型。

        Returns:
            LLMClient 实例或 None（仅当默认模型也不存在时）
        """
        model_name = None
        if agent_config:
            model_name = agent_config.get("model")

        if not model_name:
            model_name = self._default_model

        client = self._get_or_create_client(model_name)
        if client is None and model_name != self._default_model:
            # 二级回退：使用默认模型
            client = self._get_or_create_client(self._default_model)
        return client

    def list_available_models(self) -> Dict[str, str]:
        """列出所有可用的模型及其 provider"""
        return {
            m["name"]: f"{m.get('provider')}/{m.get('mainModelId')}"
            for m in self._config.get("models", [])
        }
