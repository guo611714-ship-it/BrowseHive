"""平台路由器测试（Phase 2: L2 + 熔断 + 反馈）"""

import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from agent.tools.browser.platform_router import (
    l1_route, l2_route, l3_route, _l3_fallback, get_router,
    TaskRouter, RouteResult, ExecutionBlueprint,
    PlatformCircuitBreaker, FeedbackStore, score_answer_quality,
    PLATFORM_PROFILES, L1_RULES, _extract_json, _compute_similarity,
)


class TestL1Router:
    """L1正则拦截层测试"""

    def test_code_task_python(self):
        result = l1_route("写一个Python快速排序函数")
        assert result is not None
        assert result.level == "L1"
        assert result.platforms == ["deepseek"]
        assert result.mode == "fast"
        assert result.category == "code"

    def test_code_task_javascript(self):
        result = l1_route("帮我写JavaScript的debounce函数")
        assert result is not None
        assert result.platforms == ["deepseek"]
        assert result.category == "code"

    def test_academic_task_paper(self):
        result = l1_route("帮我解读论文的核心观点")
        assert result is not None
        assert result.level == "L1"
        assert result.platforms == ["chatglm"]
        assert result.category == "academic"

    def test_knowledge_task(self):
        result = l1_route("什么是量子计算的原理")
        assert result is not None
        assert result.platforms == ["chatglm"]
        assert result.category == "knowledge"

    def test_daily_task_email(self):
        result = l1_route("帮我写一封商务邮件")
        assert result is not None
        assert result.platforms == ["doubao"]
        assert result.category == "daily"

    def test_no_match(self):
        result = l1_route("今天天气怎么样")
        assert result is None

    def test_empty_query(self):
        assert l1_route("") is None
        assert l1_route("   ") is None
        assert l1_route(None) is None


class TestL2Router:
    """L2相似度层测试"""

    def test_code_similarity(self):
        result = l2_route("用Python写一个排序算法的函数")
        assert result is not None
        assert result.level == "L2"
        assert result.platforms == ["deepseek"]
        assert result.category == "code"
        assert result.confidence > 0.3

    def test_academic_similarity(self):
        result = l2_route("这篇论文的研究方法有问题")
        assert result is not None
        assert result.platforms == ["chatglm"]
        assert result.category == "academic"

    def test_daily_similarity(self):
        result = l2_route("帮我翻译这段话成英文")
        assert result is not None
        assert result.platforms == ["doubao"]
        assert result.category == "daily"

    def test_knowledge_similarity(self):
        result = l2_route("什么是机器学习的原理")
        assert result is not None
        assert result.platforms == ["chatglm"]
        assert result.category == "knowledge"

    def test_reasoning_similarity(self):
        result = l2_route("逻辑推理这个证明过程")
        assert result is not None
        assert result.platforms == ["deepseek"]
        assert result.category == "reasoning"

    def test_low_confidence_returns_none(self):
        """低置信度应返回None，留给L3"""
        result = l2_route("你好")
        assert result is None

    def test_empty_query(self):
        assert l2_route("") is None
        assert l2_route(None) is None


class TestComputeSimilarity:
    """相似度计算测试"""

    def test_exact_match(self):
        score = _compute_similarity("写代码", "code")
        assert score > 0.05  # 至少有一些匹配

    def test_partial_match(self):
        score = _compute_similarity("Python编程", "code")
        assert score > 0.05  # 至少有一些匹配

    def test_no_match(self):
        score = _compute_similarity("今天天气", "code")
        assert score < 0.2


class TestCircuitBreaker:
    """熔断降级测试"""

    def test_initial_state(self):
        cb = PlatformCircuitBreaker()
        assert cb.is_available("deepseek") is True
        assert cb.is_available("doubao") is True

    def test_failure_opens_circuit(self):
        cb = PlatformCircuitBreaker()
        cb.failure_threshold = 2
        cb.record_failure("deepseek")
        assert cb.is_available("deepseek") is True  # 1次失败，未熔断
        cb.record_failure("deepseek")
        assert cb.is_available("deepseek") is False  # 2次失败，熔断

    def test_success_resets_failures(self):
        cb = PlatformCircuitBreaker()
        cb.failure_threshold = 3
        cb.record_failure("deepseek")
        cb.record_failure("deepseek")
        cb.record_success("deepseek")  # 成功重置
        assert cb._failures["deepseek"] == 0
        assert cb.is_available("deepseek") is True

    def test_recovery_after_timeout(self):
        cb = PlatformCircuitBreaker()
        cb.failure_threshold = 1
        cb.recovery_timeout = 0.5  # 500ms
        cb.record_failure("deepseek")
        assert cb.is_available("deepseek") is False  # 熔断
        # 电路断开期间不可用
        assert cb.is_available("deepseek") is False
        # 等待恢复期后变为可用（半开）
        time.sleep(0.6)
        assert cb.is_available("deepseek") is True

    def test_get_status(self):
        cb = PlatformCircuitBreaker()
        cb.record_failure("deepseek")
        status = cb.get_status()
        assert "deepseek" in status
        assert status["deepseek"]["consecutive_failures"] == 1


class TestFeedbackStore:
    """反馈存储测试"""

    def test_record_and_retrieve(self, tmp_path):
        fs = FeedbackStore(json_path=tmp_path / "feedback.json")
        fs.record("测试查询", "deepseek", "code", 0.8, 1500)
        avg = fs.get_platform_avg_quality("deepseek")
        assert avg == 0.8

    def test_category_platform_quality(self, tmp_path):
        fs = FeedbackStore(json_path=tmp_path / "feedback.json")
        fs.record("写代码", "deepseek", "code", 0.9, 1000)
        fs.record("写代码", "doubao", "code", 0.6, 800)
        quality = fs.get_category_platform_quality("code")
        assert quality["deepseek"] > quality["doubao"]

    def test_best_platform_for_category(self, tmp_path):
        fs = FeedbackStore(json_path=tmp_path / "feedback.json")
        fs.record("写代码", "deepseek", "code", 0.9, 1000)
        fs.record("写代码", "doubao", "code", 0.6, 800)
        best = fs.get_best_platform_for_category("code")
        assert best == "deepseek"

    def test_get_stats(self, tmp_path):
        fs = FeedbackStore(json_path=tmp_path / "feedback.json")
        fs.record("测试", "deepseek", "code", 0.8, 1000)
        stats = fs.get_stats()
        assert stats["total_records"] == 1
        assert "deepseek" in stats["platforms"]

    def test_persistence(self, tmp_path):
        path = tmp_path / "feedback.json"
        fs1 = FeedbackStore(json_path=path)
        fs1.record("测试", "deepseek", "code", 0.8, 1000)
        # 重新加载
        fs2 = FeedbackStore(json_path=path)
        assert fs2.get_platform_avg_quality("deepseek") == 0.8


class TestScoreAnswerQuality:
    """答案质量评分测试"""

    def test_empty_answer(self):
        assert score_answer_quality("", "query", "deepseek") == 0.0

    def test_good_answer(self):
        answer = "这是一个很好的回答，包含了详细的代码示例和解释。\n\n```python\ndef hello():\n    pass\n```"
        score = score_answer_quality(answer, "写函数", "deepseek")
        assert score > 0.6

    def test_short_answer_penalty(self):
        answer = "好的"
        score = score_answer_quality(answer, "写函数", "deepseek")
        assert score < 0.5

    def test_refusal_penalty(self):
        answer = "抱歉，我无法回答这个问题，因为信息不足。"
        score = score_answer_quality(answer, "问题", "doubao")
        assert score < 0.4


class TestTaskRouter:
    """TaskRouter测试（Phase 2）"""

    def test_route_l1_hit(self):
        router = TaskRouter()
        result = router.route("写一个Python函数")
        assert result.level == "L1"
        assert result.platforms == ["deepseek"]

    def test_route_l2_hit(self):
        router = TaskRouter()
        # "量子计算的发展历史" — L1无匹配，L2通过"发展/历史"命中knowledge
        result = router.route("量子计算的发展历史")
        assert result.level == "L2"
        assert result.category == "knowledge"
        assert result.platforms == ["chatglm"]

    def test_route_l3_fallback(self):
        router = TaskRouter()
        result = router.route("今天天气怎么样")
        assert result.level == "L3"

    def test_circuit_breaker_integration(self):
        router = TaskRouter()
        # 模拟多次失败
        for _ in range(3):
            router.record_platform_result("deepseek", False)
        # 应用熔断
        result = RouteResult(level="L1", platforms=["deepseek"], mode="fast",
                            category="code", confidence=1.0)
        result = router.apply_circuit_breaker(result)
        assert "deepseek" not in result.platforms or "doubao" in result.platforms

    def test_circuit_breaker_all_platforms_broken(self):
        router = TaskRouter()
        # 熔断所有平台
        for _ in range(3):
            router.record_platform_result("deepseek", False)
            router.record_platform_result("doubao", False)
            router.record_platform_result("chatglm", False)
        result = RouteResult(level="L1", platforms=["deepseek"], mode="fast",
                            category="code", confidence=1.0)
        result = router.apply_circuit_breaker(result)
        # 所有平台熔断 → 返回空列表
        assert result.platforms == []
        assert result.confidence == 0.0

    def test_feedback_integration(self, tmp_path):
        router = TaskRouter()
        router.feedback_store = FeedbackStore(json_path=tmp_path / "fb.json")
        router.record_feedback("写代码", "deepseek", "code", 0.9, 1000)
        stats = router.feedback_store.get_stats()
        assert stats["total_records"] == 1

    def test_create_blueprint(self):
        router = TaskRouter()
        route_result = RouteResult(
            level="L1", platforms=["deepseek"], mode="fast",
            category="code", confidence=1.0
        )
        bp = router.create_blueprint(route_result, "写函数")
        assert bp.route_result == route_result
        assert bp.query == "写函数"
        assert bp.fallback_platforms == ["doubao"]

    def test_get_router_singleton(self):
        r1 = get_router()
        r2 = get_router()
        assert r1 is r2


class TestPlatformProfiles:
    """平台画像测试"""

    def test_all_profiles_exist(self):
        assert "deepseek" in PLATFORM_PROFILES
        assert "chatglm" in PLATFORM_PROFILES
        assert "doubao" in PLATFORM_PROFILES

    def test_profile_has_required_fields(self):
        for name, profile in PLATFORM_PROFILES.items():
            assert "strengths" in profile
            assert "speed" in profile
            assert "cost" in profile
            assert "description" in profile


class TestL1Rules:
    """L1规则测试"""

    def test_all_rules_have_required_fields(self):
        for i, rule in enumerate(L1_RULES):
            assert "patterns" in rule
            assert "platforms" in rule
            assert "mode" in rule
            assert "category" in rule

    def test_all_patterns_are_valid_regex(self):
        import re
        for i, rule in enumerate(L1_RULES):
            for j, pattern in enumerate(rule["patterns"]):
                try:
                    re.compile(pattern)
                except re.error as e:
                    pytest.fail(f"Rule {i} pattern {j} invalid: {e}")


class TestRouteResult:
    """RouteResult数据结构测试"""

    def test_creation(self):
        r = RouteResult(level="L1", platforms=["deepseek"], mode="fast", category="code")
        assert r.level == "L1"
        assert r.confidence == 1.0

    def test_with_reason(self):
        r = RouteResult(level="L3", platforms=["doubao"], mode="fast",
                       category="general", reason="test")
        assert r.reason == "test"


class TestExecutionBlueprint:
    """ExecutionBlueprint测试"""

    def test_creation(self):
        rr = RouteResult(level="L1", platforms=["deepseek"], mode="fast", category="code")
        bp = ExecutionBlueprint(route_result=rr, query="test")
        assert bp.fallback_platforms == ["doubao"]
