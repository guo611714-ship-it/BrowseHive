"""模型编排器：10模型细粒度路由 + 自动降级"""

import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Optional, List, Any
from .llm_client import LLMClient, load_llm_client_from_config
from .health_monitor import HealthMonitor

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10模型能力矩阵
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# | 模型 | 角色 | tc | 速度 | ctx | 强项 |
# | gemma-e2b | lightweight | ✗ | 极快 | 32K | 分类/摘要/简单问答 |
# | gemma-e4b | lightweight | ✗ | 极快 | 32K | 音频/相关性判断 |
# | step-3.5-flash | agentic | ✓ | 350tok/s | 256K | 纯文本极速/批量处理 |
# | step-3.7-flash | agentic | ✓ | 350tok/s | 256K | SWE-bench 74.4%/GUI/多模态 |
# | minimax-m2.7 | agentic | ✓ | 中等 | 204K | Agent Teams原生/Toolathon 46% |
# | mistral-nemotron | coding | ✓ | 中等 | 128K | HumanEval 92.68/MATH 91.14 |
# | qwen3-coder | coding | ✓ | 中等 | 200K | 代码专用/大规模审计 |
# | llama-maverick | reasoning | ✓ | 快 | 1M | 1M上下文/多模态推理/图表 |
# | mistral-large-3 | reasoning | ✓ | 慢 | 256K | 675B企业级/原生function calling |
# | glm-5.1 | reasoning | ✓ | 慢 | 131K | 754B最长链推理/数千次工具调用 |

# 任务类型 → 角色候选列表
_TASK_ROLE_MAP = {
    "coding": ["coding", "agentic", "general"],
    "agentic": ["agentic", "coding", "general"],
    "reasoning": ["reasoning", "general", "agentic"],
    "lightweight": ["lightweight", "general"],
    "multimodal": ["agentic", "reasoning"],
    "general": ["agentic", "reasoning", "coding"],
}

# 默认配置（当配置文件中没有对应配置时使用）
DEFAULT_COMPLEXITY_ROUTE = {
    1: "nvidia-gemma-e2b",
    2: "nvidia-step-3.7-flash",
    3: "nvidia-minimax-m2.7",
    4: "nvidia-mistral-large-3",
    5: "nvidia-glm-5.1",
}

DEFAULT_MODEL_SPEED_TIERS: Dict[str, int] = {
    "nvidia-gemma-e2b": 30,
    "nvidia-gemma-e4b": 30,
    "nvidia-step-3.5-flash": 30,
    "nvidia-step-3.7-flash": 30,
    "nvidia-minimax-m2.7": 60,
    "nvidia-mistral-nemotron": 60,
    "nvidia-qwen3-coder": 60,
    "nvidia-llama-maverick": 90,
    "nvidia-mistral-large-3": 120,
    "nvidia-glm-5.1": 120,
}

DEFAULT_AGENT_MODEL_MAP = {
    "xiaohuangmen": "nvidia-step-3.7-flash",
    "sili_suitang": "nvidia-step-3.7-flash",
    "dongchang_tanshi": "nvidia-step-3.7-flash",
    "shangbao_dianbu": "nvidia-mistral-nemotron",
    "neiguan_yingzao": "nvidia-minimax-m2.7",
    "liubu_liulanqi": "nvidia-step-3.7-flash",
}

DEFAULT_SCENARIO_MODEL_MAP = {
    "分类打标": "nvidia-gemma-e2b", "关键词提取": "nvidia-gemma-e2b",
    "笔记整理": "nvidia-step-3.5-flash", "文档摘要": "nvidia-step-3.5-flash",
    "检索重排序": "nvidia-gemma-e4b", "长文档导入": "nvidia-llama-maverick",
    "内容过时校验": "nvidia-mistral-nemotron",
    "小代码生成": "nvidia-step-3.7-flash", "代码审查": "nvidia-mistral-nemotron",
    "代码审计": "nvidia-qwen3-coder", "代码重构": "nvidia-qwen3-coder",
    "代码调试": "nvidia-glm-5.1", "性能优化": "nvidia-mistral-large-3",
    "架构设计": "nvidia-mistral-large-3",
    "短链任务": "nvidia-minimax-m2.7", "长链任务": "nvidia-glm-5.1",
    "DAG编排": "nvidia-minimax-m2.7", "任务拆分": "nvidia-step-3.5-flash",
    "结果校验": "nvidia-mistral-nemotron",
    "简单爬取": "nvidia-step-3.7-flash", "复杂GUI": "nvidia-glm-5.1",
    "截图解析": "nvidia-step-3.7-flash", "批量爬取": "nvidia-step-3.5-flash",
    "音频处理": "nvidia-gemma-e4b", "图表解析": "nvidia-llama-maverick",
    "多图推理": "nvidia-llama-maverick", "办公文档": "nvidia-minimax-m2.7",
    "方案选型": "nvidia-mistral-large-3", "数学推导": "nvidia-mistral-nemotron",
    "论文解读": "nvidia-llama-maverick", "根因分析": "nvidia-glm-5.1",
    "简单问答": "nvidia-gemma-e2b", "数据分类": "nvidia-gemma-e2b",
    "命令补全": "nvidia-gemma-e2b",
}


class ModelOrchestrator:
    """模型路由器与客户端池（含健康检查）"""

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self._config = self._load_config()
        self._client_cache: Dict[str, LLMClient] = {}
        self._complexity_cache: Dict[int, str] = {}
        self._complexity_cache_ttl = 300
        self._default_model = self._config.get("agents", {}).get("defaults", {}).get("model")
        self._health = HealthMonitor()
        self._default_provider = self._config.get("agents", {}).get("defaults", {}).get("provider", "openai")
        self._role_index: Dict[str, List[str]] = {}
        for m in self._config.get("models", []):
            role = m.get("capabilities", {}).get("role", "general")
            self._role_index.setdefault(role, []).append(m["name"])

        # 从配置文件加载路由配置，使用默认值作为fallback
        routing = self._config.get("routing", {})
        self._complexity_route = {
            int(k): v for k, v in routing.get("complexity_route", DEFAULT_COMPLEXITY_ROUTE).items()
        }
        self._model_speed_tiers = routing.get("model_speed_tiers", DEFAULT_MODEL_SPEED_TIERS)
        self._agent_model_map = routing.get("agent_model_map", DEFAULT_AGENT_MODEL_MAP)
        self._scenario_model_map = routing.get("scenario_model_map", DEFAULT_SCENARIO_MODEL_MAP)

        if self._default_model:
            self._get_or_create_client(self._default_model)

    async def shutdown(self):
        """关闭所有缓存的LLM客户端，释放HTTP连接池资源"""
        for client in self._client_cache.values():
            try:
                await client.aclose()
            except Exception as e:
                logger.warning(f"关闭LLM客户端失败: {e}")
        self._client_cache.clear()

    def setup_project_pools(self, project_count: int = 3,
                            keys_per_project: int = 3,
                            project_max: int = 15) -> dict:
        """为多个并行项目创建独立key子池。

        Args:
            project_count: 并行项目数
            keys_per_project: 每个项目分配的key数
            project_max: 每个项目每分钟最大请求数

        Returns:
            {project_id: APIKeyPool} 字典
        """
        from shared.api_key_pool import APIKeyPool

        # 收集所有可用key
        provider_cfg = self._config.get("providers", {}).get("nvidia", {})
        all_keys = provider_cfg.get("apiKeys", [])
        if not all_keys:
            logger.warning("无可用API Key，无法创建子池")
            return {}

        # 创建主池
        main_pool = APIKeyPool(
            keys=all_keys, provider="nvidia",
            interval=2.0, window=60, max_requests=8,
            account_max_requests=project_count * project_max,
        )

        # 为每个项目分配子池
        pools = {}
        for i in range(project_count):
            pid = f"project-{i+1}"
            pools[pid] = main_pool.create_sub_pool(
                pid, key_count=keys_per_project,
                project_max_requests=project_max,
            )

        logger.info(f"已创建 {project_count} 个项目子池, "
                     f"每个 {keys_per_project} key, "
                     f"限流 {project_max}/min")
        return pools

    def _load_config(self) -> Dict:
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"配置文件错误: {e}")
            return {}

    def _get_or_create_client(self, model_name: str) -> Optional[LLMClient]:
        if not model_name or not isinstance(model_name, str):
            return None
        if model_name in self._client_cache:
            return self._client_cache[model_name]
        model_cfg = None
        for m in self._config.get("models", []):
            if m.get("name") == model_name:
                model_cfg = m
                break
        if not model_cfg:
            return None
        provider = model_cfg.get("provider") or self._default_provider
        main_id = model_cfg.get("mainModelId") or model_name
        api_key = model_cfg.get("apiKey")
        api_base = model_cfg.get("apiBase")
        max_tokens = model_cfg.get("maxTokens", 20000) or 20000
        temperature = model_cfg.get("temperature", 0.1) or 0.1
        provider_cfg = self._config.get("providers", {}).get(provider, {})
        if not api_key:
            api_key = provider_cfg.get("apiKey", "")
        if not api_base:
            api_base = provider_cfg.get("apiBase")
        api_keys = provider_cfg.get("apiKeys") or []
        if not api_keys and api_key:
            api_keys = [api_key]
        client = LLMClient(provider=provider, model=main_id, api_key=api_key,
                           api_base=api_base, max_tokens=max_tokens,
                           temperature=temperature, api_keys=api_keys or None)
        self._client_cache[model_name] = client
        return client

    def get_client_for_agent(self, agent_name: str, agent_config: Optional[Dict] = None) -> Optional[LLMClient]:
        model_name = agent_config.get("model") if agent_config else None
        if not model_name:
            model_name = self._default_model
        client = self._get_or_create_client(model_name)
        if client is None and model_name != self._default_model:
            client = self._get_or_create_client(self._default_model)
        return client

    def get_client_for_task(self, task: str, agent_type: str = None,
                            prefer_speed: bool = False) -> Optional[LLMClient]:
        """细粒度模型选择：agent专属 > 场景匹配 > 复杂度 > 角色 > 默认"""
        # 1. agent专属模型
        if agent_type and agent_type in self._agent_model_map:
            client = self._get_or_create_client(self._agent_model_map[agent_type])
            if client:
                return client

        # 2. 场景匹配
        task_lower = task.lower()
        for scenario, model in self._scenario_model_map.items():
            if scenario in task_lower:
                client = self._get_or_create_client(model)
                if client:
                    return client

        # 3. 复杂度路由
        task_type = self._analyze_task(task)
        role_candidates = _TASK_ROLE_MAP.get(task_type, ["general", "agentic"])
        for role in role_candidates:
            models = self._role_index.get(role, [])
            if models:
                if prefer_speed:
                    return self._get_or_create_client(self._sort_by_speed(models)[0])
                return self._get_or_create_client(models[0])

        return self._get_or_create_client(self._default_model)

    def score_complexity(self, task: str) -> int:
        """关键词快速评分（1-5）"""
        t = task.lower()
        if any(w in t for w in ["多文档", "关联", "端到端", "根因", "全链路", "数百轮"]):
            return 5
        if any(w in t for w in ["审计", "推理", "评估", "优化", "重构", "设计", "架构", "调试"]):
            return 4
        if any(w in t for w in ["分析", "总结", "实现", "创建", "编写", "修改", "代码"]):
            return 3
        if any(w in t for w in ["搜索", "查找", "转换", "格式化", "统计", "列出"]):
            return 2
        return 1

    def get_model_for_complexity(self, complexity: int) -> Optional[LLMClient]:
        if complexity in self._complexity_cache:
            model_name = self._complexity_cache[complexity]
        else:
            model_name = self._complexity_route.get(complexity, self._default_model)
            self._complexity_cache[complexity] = model_name

        client = self._get_or_create_client(model_name)
        if client and not self._health.is_healthy(model_name):
            healthy = self._health.get_healthy_models()
            if healthy:
                alt_client = self._get_or_create_client(healthy[0])
                if alt_client:
                    logger.info(f"模型 {model_name} 不健康，切换到 {healthy[0]}")
                    return alt_client
        return client or self._get_or_create_client(self._default_model)

    def get_fallback_client(self, attempt: int) -> Optional[LLMClient]:
        """获取fallback模型（按稳定性排序，跳过不健康模型）"""
        stable_fallback = [
            "nvidia-mistral-nemotron",
            "nvidia-step-3.5-flash",
            "nvidia-step-3.7-flash",
            "nvidia-minimax-m2.7",
            "nvidia-llama-maverick",
        ]
        healthy_fallback = [m for m in stable_fallback if self._health.is_healthy(m)]
        if not healthy_fallback:
            healthy_fallback = stable_fallback
        if attempt < len(healthy_fallback):
            return self._get_or_create_client(healthy_fallback[attempt])
        return self._get_or_create_client(self._default_model)

    def mark_model_unhealthy(self, model_name: str):
        self._health.mark_unhealthy(model_name)

    def mark_model_healthy(self, model_name: str):
        self._health.mark_healthy(model_name)

    def record_model_result(self, model_name: str, success: bool, latency_ms: int = 0):
        self._health.record_result(model_name, success, latency_ms)

    def get_health_report(self) -> Dict[str, Any]:
        return self._health.get_report()

    def get_healthy_models(self) -> List[str]:
        return self._health.get_healthy_models()

    def _analyze_task(self, task: str) -> str:
        t = task.lower()
        scores: Dict[str, int] = {}
        for task_type, keywords in _KEYWORDS.items():
            score = sum(w for kw, w in keywords if kw.lower() in t)
            if score > 0:
                scores[task_type] = score
        return max(scores, key=scores.get) if scores else "general"

    def _sort_by_speed(self, model_names: List[str]) -> List[str]:
        speed = {
            "nvidia-gemma-e2b": 1, "nvidia-gemma-e4b": 1,
            "nvidia-step-3.7-flash": 2, "nvidia-step-3.5-flash": 2,
            "nvidia-llama-maverick": 3, "nvidia-mistral-nemotron": 4,
            "nvidia-minimax-m2.7": 5, "nvidia-qwen3-coder": 6,
            "nvidia-mistral-large-3": 7, "nvidia-glm-5.1": 8,
        }
        return sorted(model_names, key=lambda m: speed.get(m, 99))


    def list_available_models(self) -> Dict[str, str]:
        return {m["name"]: f"{m.get('provider')}/{m.get('mainModelId')}"
                for m in self._config.get("models", [])}


# 知识库搜索用中英文映射
ZH_EN_MAP = {
    "多模态": "multimodal", "推理": "reasoning", "安全": "safety guard",
    "代码": "code", "模型": "model", "训练": "training",
    "微调": "fine-tune lora", "检索": "retrieval rag",
    "agent": "agentic tool", "工具": "tool calling",
    "视觉": "vision image", "轻量": "lightweight small",
    "路由": "routing", "分类": "classification",
}

# 任务关键词
_KEYWORDS = {
    "coding": [("代码", 1), ("code", 1), ("编程", 2), ("审计", 2), ("重构", 2), ("调试", 2)],
    "agentic": [("搜索", 1), ("执行", 2), ("工具", 1), ("命令", 2), ("浏览器", 2)],
    "reasoning": [("分析", 2), ("推理", 2), ("设计", 2), ("架构", 2), ("评估", 2)],
    "lightweight": [("总结", 2), ("分类", 2), ("简单", 1), ("问答", 1)],
    "multimodal": [("图片", 2), ("截图", 2), ("视觉", 2), ("音频", 2)],
}
