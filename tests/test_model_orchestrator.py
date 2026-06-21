"""agent.model_orchestrator 模块测试

测试 ModelOrchestrator 的核心功能：
- 模型路由表初始化（默认配置 / 自定义配置）
- 复杂度评分与模型选择
- fallback 链（502 时自动切换下一个稳定模型）
- 健康状态持久化（save/load health.json）
- 模型不可用时的降级逻辑
"""

import json
import threading
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

import pytest

from agent.model_orchestrator import (
    ModelOrchestrator,
    DEFAULT_COMPLEXITY_ROUTE,
    DEFAULT_AGENT_MODEL_MAP,
    DEFAULT_SCENARIO_MODEL_MAP,
)


# ────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────

def _make_config(
    models: List[Dict[str, Any]] = None,
    defaults: Dict[str, Any] = None,
    routing: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """构造最小 model_config.json 内容"""
    return {
        "providers": {
            "nvidia": {
                "apiKey": "test-key",
                "apiBase": "https://integrate.api.nvidia.com/v1",
            }
        },
        "models": models or [
            {
                "name": "nvidia-step-3.7-flash",
                "provider": "nvidia",
                "mainModelId": "stepfun/step-3.7-flash",
                "maxTokens": 8000,
                "capabilities": {"role": "agentic"},
            },
            {
                "name": "nvidia-mistral-nemotron",
                "provider": "nvidia",
                "mainModelId": "mistral-nemotron-ultra-2505",
                "maxTokens": 8000,
                "capabilities": {"role": "coding"},
            },
            {
                "name": "nvidia-glm-5.1",
                "provider": "nvidia",
                "mainModelId": "zhipuai/glm-5.1",
                "maxTokens": 8000,
                "capabilities": {"role": "reasoning"},
            },
        ],
        "agents": {"defaults": defaults or {"model": "nvidia-step-3.7-flash", "provider": "nvidia"}},
        "routing": routing or {},
    }


def _write_config(tmp_path: Path, config: Dict[str, Any] = None) -> Path:
    """将配置写入 tmp_path 并返回路径"""
    cfg = config or _make_config()
    cfg_path = tmp_path / "model_config.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return cfg_path


def _make_orchestrator(tmp_path: Path, **kwargs) -> ModelOrchestrator:
    """构建 ModelOrchestrator，将 health.json 隔离到 tmp_path"""
    cfg_path = _write_config(tmp_path, kwargs.pop("config", None))
    orch = ModelOrchestrator(cfg_path)
    orch._health._json_path = tmp_path / ".team" / "health.json"
    orch._health._json_path.parent.mkdir(parents=True, exist_ok=True)
    return orch


# ────────────────────────────────────────────────────────
# 1. 初始化与路由表
# ────────────────────────────────────────────────────────

class TestModelOrchestratorInit:
    """验证路由表正确加载"""

    def test_default_model_set(self, tmp_path: Path) -> None:
        """默认模型从 agents.defaults.model 加载"""
        orch = _make_orchestrator(tmp_path)
        assert orch._default_model == "nvidia-step-3.7-flash"

    def test_complexity_route_loaded(self, tmp_path: Path) -> None:
        """complexity_route 使用默认值"""
        orch = _make_orchestrator(tmp_path)
        assert orch._complexity_route == DEFAULT_COMPLEXITY_ROUTE

    def test_custom_complexity_route(self, tmp_path: Path) -> None:
        """自定义 complexity_route 覆盖默认值"""
        custom = {"1": "nvidia-gemma-e2b", "3": "custom-model"}
        cfg = _make_config(routing={"complexity_route": custom})
        orch = _make_orchestrator(tmp_path, config=cfg)
        assert orch._complexity_route[1] == "nvidia-gemma-e2b"
        assert orch._complexity_route[3] == "custom-model"

    def test_role_index_built(self, tmp_path: Path) -> None:
        """角色索引按 capabilities.role 分组"""
        orch = _make_orchestrator(tmp_path)
        assert "nvidia-step-3.7-flash" in orch._role_index.get("agentic", [])
        assert "nvidia-mistral-nemotron" in orch._role_index.get("coding", [])

    def test_list_available_models(self, tmp_path: Path) -> None:
        """list_available_models 返回 name→provider/modelId 映射"""
        orch = _make_orchestrator(tmp_path)
        available = orch.list_available_models()
        assert "nvidia-step-3.7-flash" in available
        assert "nvidia" in available["nvidia-step-3.7-flash"]


# ────────────────────────────────────────────────────────
# 2. 复杂度评分
# ────────────────────────────────────────────────────────

class TestComplexityScoring:
    """验证 score_complexity 关键词评分"""

    def test_score_level5(self, tmp_path: Path) -> None:
        """含多文档/端到端/根因 → 5分"""
        orch = _make_orchestrator(tmp_path)
        assert orch.score_complexity("进行全链路多文档关联分析") == 5

    def test_score_level4(self, tmp_path: Path) -> None:
        """含审计/推理/架构 → 4分"""
        orch = _make_orchestrator(tmp_path)
        assert orch.score_complexity("代码架构设计与审计") == 4

    def test_score_level3(self, tmp_path: Path) -> None:
        """含分析/总结/代码 → 3分"""
        orch = _make_orchestrator(tmp_path)
        assert orch.score_complexity("分析并编写单元测试") == 3

    def test_score_level2(self, tmp_path: Path) -> None:
        """含搜索/查找/格式化 → 2分"""
        orch = _make_orchestrator(tmp_path)
        assert orch.score_complexity("搜索并格式化日志") == 2

    def test_score_level1_default(self, tmp_path: Path) -> None:
        """无匹配关键词 → 1分"""
        orch = _make_orchestrator(tmp_path)
        assert orch.score_complexity("你好") == 1


# ────────────────────────────────────────────────────────
# 3. get_model_for_complexity 路由
# ────────────────────────────────────────────────────────

class TestComplexityRouting:
    """验证不同复杂度返回对应模型"""

    @patch("agent.model_orchestrator.LLMClient")
    def test_complexity_1_returns_e2b(self, mock_cls, tmp_path: Path) -> None:
        """complexity=1 返回 gemma-e2b"""
        orch = _make_orchestrator(tmp_path)
        orch._get_or_create_client = MagicMock(return_value=mock_cls.return_value)
        client = orch.get_model_for_complexity(1)
        orch._get_or_create_client.assert_called_with("nvidia-gemma-e2b")

    @patch("agent.model_orchestrator.LLMClient")
    def test_complexity_5_returns_glm(self, mock_cls, tmp_path: Path) -> None:
        """complexity=5 返回 glm-5.1"""
        orch = _make_orchestrator(tmp_path)
        orch._get_or_create_client = MagicMock(return_value=mock_cls.return_value)
        client = orch.get_model_for_complexity(5)
        orch._get_or_create_client.assert_called_with("nvidia-glm-5.1")

    @patch("agent.model_orchestrator.LLMClient")
    def test_unknown_complexity_falls_back(self, mock_cls, tmp_path: Path) -> None:
        """不存在的 complexity 降级到默认模型"""
        orch = _make_orchestrator(tmp_path)
        orch._get_or_create_client = MagicMock(return_value=mock_cls.return_value)
        orch.get_model_for_complexity(99)
        orch._get_or_create_client.assert_called_with(orch._default_model)


# ────────────────────────────────────────────────────────
# 4. fallback 链
# ────────────────────────────────────────────────────────

class TestFallbackChain:
    """验证 502 时 fallback 按稳定性排序切换"""

    @patch("agent.model_orchestrator.LLMClient")
    def test_fallback_attempt_0(self, mock_cls, tmp_path: Path) -> None:
        """第0次 fallback 返回最稳定模型"""
        orch = _make_orchestrator(tmp_path)
        orch._get_or_create_client = MagicMock(return_value=mock_cls.return_value)
        orch.get_fallback_client(0)
        orch._get_or_create_client.assert_called_with("nvidia-mistral-nemotron")

    @patch("agent.model_orchestrator.LLMClient")
    def test_fallback_attempt_1(self, mock_cls, tmp_path: Path) -> None:
        """第1次 fallback 返回次稳定模型"""
        orch = _make_orchestrator(tmp_path)
        orch._get_or_create_client = MagicMock(return_value=mock_cls.return_value)
        orch.get_fallback_client(1)
        orch._get_or_create_client.assert_called_with("nvidia-step-3.5-flash")

    @patch("agent.model_orchestrator.LLMClient")
    def test_fallback_skips_unhealthy(self, mock_cls, tmp_path: Path) -> None:
        """不健康模型被跳过"""
        orch = _make_orchestrator(tmp_path)
        orch._health._health_status["nvidia-mistral-nemotron"] = False
        orch._get_or_create_client = MagicMock(return_value=mock_cls.return_value)
        orch.get_fallback_client(0)
        orch._get_or_create_client.assert_called_with("nvidia-step-3.5-flash")

    @patch("agent.model_orchestrator.LLMClient")
    def test_fallback_exceeds_chain(self, mock_cls, tmp_path: Path) -> None:
        """超过 fallback 链长度后回到默认模型"""
        orch = _make_orchestrator(tmp_path)
        orch._get_or_create_client = MagicMock(return_value=mock_cls.return_value)
        orch.get_fallback_client(100)
        orch._get_or_create_client.assert_called_with(orch._default_model)


# ────────────────────────────────────────────────────────
# 5. 健康状态持久化
# ────────────────────────────────────────────────────────

class TestHealthPersistence:
    """验证 save/load health 到 .team/health.json"""

    def test_save_and_load(self, tmp_path: Path) -> None:
        """保存后重新加载恢复状态"""
        orch = _make_orchestrator(tmp_path)
        orch.mark_model_unhealthy("nvidia-step-3.7-flash")
        orch._health._save()
        assert orch._health._json_path.exists()

        # 新实例加载同一路径
        orch2 = _make_orchestrator(tmp_path)
        orch2._health._json_path = orch._health._json_path
        orch2._health._load()
        assert orch2._health._health_status.get("nvidia-step-3.7-flash") is False

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """health.json 不存在时不报错"""
        orch = _make_orchestrator(tmp_path)
        orch._health._json_path = tmp_path / "nonexistent" / "health.json"
        orch._health._load()  # 不应抛异常

    def test_load_corrupt_file(self, tmp_path: Path) -> None:
        """health.json 损坏时不报错"""
        orch = _make_orchestrator(tmp_path)
        orch._health._json_path.write_text("not json !!!", encoding="utf-8")
        orch._health._load()  # 不应抛异常

    def test_record_result_persists(self, tmp_path: Path) -> None:
        """record_model_result 自动持久化"""
        orch = _make_orchestrator(tmp_path)
        orch.record_model_result("nvidia-step-3.7-flash", success=True, latency_ms=200)
        assert orch._health._json_path.exists()
        data = json.loads(orch._health._json_path.read_text(encoding="utf-8"))
        assert "nvidia-step-3.7-flash" in data.get("health_scores", {})


# ────────────────────────────────────────────────────────
# 6. 降级逻辑
# ────────────────────────────────────────────────────────

class TestDegradationLogic:
    """验证模型不可用时的自动降级"""

    def test_mark_unhealthy(self, tmp_path: Path) -> None:
        """mark_model_unhealthy 将模型标记为不健康"""
        orch = _make_orchestrator(tmp_path)
        orch.mark_model_unhealthy("nvidia-step-3.7-flash")
        assert orch._health._health_status["nvidia-step-3.7-flash"] is False

    def test_mark_healthy(self, tmp_path: Path) -> None:
        """mark_model_healthy 恢复健康标记"""
        orch = _make_orchestrator(tmp_path)
        orch.mark_model_unhealthy("nvidia-step-3.7-flash")
        orch.mark_model_healthy("nvidia-step-3.7-flash")
        assert orch._health._health_status["nvidia-step-3.7-flash"] is True

    def test_consecutive_fail_triggers_unhealthy(self, tmp_path: Path) -> None:
        """连续失败2次自动标记不健康"""
        orch = _make_orchestrator(tmp_path)
        orch.record_model_result("nvidia-glm-5.1", success=False)
        assert orch._health._health_status.get("nvidia-glm-5.1") is not False
        orch.record_model_result("nvidia-glm-5.1", success=False)
        assert orch._health._health_status["nvidia-glm-5.1"] is False

    def test_consecutive_success_restores_health(self, tmp_path: Path) -> None:
        """连续成功3次恢复健康"""
        orch = _make_orchestrator(tmp_path)
        orch.mark_model_unhealthy("nvidia-step-3.7-flash")
        for _ in range(3):
            orch.record_model_result("nvidia-step-3.7-flash", success=True)
        assert orch._health._health_status["nvidia-step-3.7-flash"] is True

    def test_get_healthy_models_excludes_unhealthy(self, tmp_path: Path) -> None:
        """get_healthy_models 排除不健康模型"""
        orch = _make_orchestrator(tmp_path)
        orch.mark_model_unhealthy("nvidia-mistral-nemotron")
        healthy = orch.get_healthy_models()
        assert "nvidia-mistral-nemotron" not in healthy
        assert len(healthy) > 0

    def test_health_report_structure(self, tmp_path: Path) -> None:
        """健康报告包含所有模型及其指标"""
        orch = _make_orchestrator(tmp_path)
        orch.record_model_result("nvidia-step-3.7-flash", success=True, latency_ms=150)
        report = orch.get_health_report()
        entry = report["nvidia-step-3.7-flash"]
        assert entry["healthy"] is True
        assert entry["success"] == 1
        assert entry["total"] == 1
        assert entry["avg_latency_ms"] == 150
