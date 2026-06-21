"""AI平台统一API路由器."""
import os
from typing import Optional, Dict, Any
from config_loader import load_config, APIConfig
from deepseek_client import DeepSeekClient
from doubao_client import DoubaoClient
from volcengine_client import VolcEngineClient
from anthropic_client import AnthropicClient
from ouyi_api import chat as ouyi_chat, write as ouyi_write, mindmap as ouyi_mindmap


class AIRouter:
    """统一AI平台路由器."""

    def __init__(self, config: APIConfig = None):
        self.config = config or load_config()
        self._clients = {}

    def get_client(self, platform: str):
        """获取指定平台的客户端."""
        if platform in self._clients:
            return self._clients[platform]

        client_map = {
            "deepseek": lambda: DeepSeekClient(
                api_key=self.config.deepseek_key,
                base_url=self.config.deepseek_base_url,
                model=self.config.deepseek_model
            ),
            "doubao": lambda: DoubaoClient(
                api_key=self.config.doubao_key,
                base_url=self.config.doubao_base_url,
                model=self.config.doubao_model
            ),
            "volcengine": lambda: VolcEngineClient(
                api_key=self.config.volcengine_key,
                base_url=self.config.volcengine_base_url,
                model=self.config.volcengine_model
            ),
            "anthropic": lambda: AnthropicClient(
                api_key=self.config.anthropic_key,
                base_url=self.config.anthropic_base_url,
                model=self.config.anthropic_model
            ),
        }

        if platform not in client_map:
            raise ValueError(f"不支持的平台: {platform}，可选: {list(client_map.keys())}")

        self._clients[platform] = client_map[platform]()
        return self._clients[platform]

    def chat(self, platform: str, message: str, system_prompt: str = None, **kwargs) -> str:
        """智能路由对话."""
        # 检查平台是否可用
        available = self.get_available_platforms()
        if platform not in available:
            raise ValueError(f"平台 {platform} 未配置API密钥")

        # 优先使用浏览器方式（如果已登录）
        if platform == "ouyi":
            return ouyi_chat(message, system_prompt=system_prompt)

        client = self.get_client(platform)
        return client.chat(message, system_prompt=system_prompt, **kwargs)

    def get_available_platforms(self) -> Dict[str, bool]:
        """返回所有平台可用性状态."""
        status = {
            "deepseek": bool(self.config.deepseek_key),
            "doubao": bool(self.config.doubao_key),
            "volcengine": bool(self.config.volcengine_key),
            "anthropic": bool(self.config.anthropic_key),
            "ouyi": bool(self.config.ouyi_token),
        }
        return {k: v for k, v in status.items() if v}

    def list_platforms(self) -> str:
        """列出所有平台状态."""
        lines = ["可用平台:"]
        for platform, available in self.get_available_platforms().items():
            status = "✓ 已配置" if available else "✗ 未配置"
            lines.append(f"  {platform}: {status}")
        return "\n".join(lines)


# 全局路由器实例
_router: Optional[AIRouter] = None


def get_router() -> AIRouter:
    """获取全局路由器实例."""
    global _router
    if _router is None:
        _router = AIRouter()
    return _router


if __name__ == "__main__":
    router = get_router()
    print(router.list_platforms())

    # 测试DeepSeek
    if "deepseek" in router.get_available_platforms():
        print("\n[DeepSeek测试]")
        try:
            result = router.chat("deepseek", "用一句话介绍DeepSeek")
            print(f"回复: {result[:100]}...")
        except Exception as e:
            print(f"错误: {e}")
