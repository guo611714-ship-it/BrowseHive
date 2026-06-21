# agent_sse/config/routing_config.py
"""路由配置"""

import os
import yaml
from pathlib import Path
from typing import List, Dict


def load_keys_from_file() -> List[str]:
    """从 keys.yaml 文件加载 Key"""
    keys_file = Path(__file__).parent / "keys.yaml"
    if keys_file.exists():
        with open(keys_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("keys", [])
    return []


def load_keys_from_env() -> List[str]:
    """从环境变量加载 Key"""
    keys_str = os.environ.get("NVIDIA_API_KEYS", "")
    if keys_str:
        return [k.strip() for k in keys_str.split(",") if k.strip()]
    return []


def get_api_keys() -> List[str]:
    """获取 API Key 列表（优先环境变量）"""
    keys = load_keys_from_env()
    if not keys:
        keys = load_keys_from_file()
    return keys


def get_base_url() -> str:
    """获取 API Base URL"""
    return os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")


# 自定义路由规则
ROUTING_RULES = {
    # 按 agent 分配模型
    "agent_model_map": {
        "xiaohuangmen": "nvidia-step-3.7-flash",
        "sili_suitang": "nvidia-step-3.7-flash",
        "dongchang_tanshi": "nvidia-step-3.7-flash",
        "shangbao_dianbu": "nvidia-mistral-nemotron",
        "neiguan_yingzao": "nvidia-minimax-m2.7",
        "liubu_liulanqi": "nvidia-step-3.7-flash",
        "hanlin": "nvidia-step-3.7-flash",
        "zhukao": "nvidia-step-3.7-flash",
        "planner": "nvidia-step-3.7-flash",
        "multimodal": "nvidia-step-3.7-flash",
    },
    # 按复杂度分配模型
    "complexity": {
        1: "nvidia-gemma-e2b",
        2: "nvidia-step-3.5-flash",
        3: "nvidia-step-3.5-flash",
        4: "nvidia-step-3.7-flash",
        5: "nvidia-minimax-m2.7",
    },
}

# Key 轮询策略
KEY_ROTATION_MODE = "global"

# Key 配额耗尽自动切换规则
KEY_ROTATION_RULES = {
    "max_failure_rate": 0.2,
    "max_usage_rate": 0.9,
    "cooldown_seconds": 60,
    "min_calls_for_stats": 10,
}
