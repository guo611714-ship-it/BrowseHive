"""第三方API配置加载器."""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class APIConfig:
    """API配置容器."""
    # 欧亿AI
    ouyi_token: Optional[str] = None
    ouyi_base_url: str = "https://api-8.rcouyi.com"

    # DeepSeek
    deepseek_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 豆包
    doubao_key: Optional[str] = None
    doubao_base_url: str = "https://ark.doubao.com"
    doubao_model: str = "doubao-1-5-pro"

    # 火山引擎
    volcengine_key: Optional[str] = None
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_model: str = "volcano-ai"

    # Claude/Anthropic
    anthropic_key: Optional[str] = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-opus-4-7-20250514"

    # 代理
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None


def load_config(env_file: str = ".env") -> APIConfig:
    """从环境变量或.env文件加载配置."""
    # 如果存在.env文件，尝试加载（简化版，实际可用python-dotenv）
    if os.path.exists(env_file):
        from dotenv import load_dotenv
        load_dotenv(env_file)

    return APIConfig(
        ouyi_token=os.environ.get("OUYI_API_TOKEN"),
        deepseek_key=os.environ.get("DEEPSEEK_API_KEY"),
        deepseek_base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        doubao_key=os.environ.get("DOUBAO_API_KEY"),
        doubao_base_url=os.environ.get("DOUBAO_BASE_URL", "https://ark.doubao.com"),
        doubao_model=os.environ.get("DOUBAO_MODEL", "doubao-1-5-pro"),
        volcengine_key=os.environ.get("VOLCENGINE_API_KEY"),
        volcengine_base_url=os.environ.get("VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        volcengine_model=os.environ.get("VOLCENGINE_MODEL", "volcano-ai"),
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY"),
        anthropic_base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7-20250514"),
        http_proxy=os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        https_proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    )


def get_available_apis(config: APIConfig) -> dict:
    """返回已配置的API列表."""
    return {
        "ouyi": bool(config.ouyi_token),
        "deepseek": bool(config.deepseek_key),
        "doubao": bool(config.doubao_key),
        "volcengine": bool(config.volcengine_key),
        "anthropic": bool(config.anthropic_key),
    }
