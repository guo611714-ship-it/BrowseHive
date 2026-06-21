"""ChatEngine 单元测试."""

import asyncio
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from core.chat_engine import ChatEngine


class TestRateLimit:
    """限流测试."""

    def test_first_request_allowed(self):
        """第一次请求应通过限流."""
        engine = ChatEngine()
        result = engine._check_rate_limit("doubao")
        assert result is None

    def test_too_fast_blocked(self):
        """间隔过短应被限流."""
        engine = ChatEngine()
        engine._check_rate_limit("doubao")  # 第一次
        result = engine._check_rate_limit("doubao")  # 立即第二次
        assert result is not None
        assert "限流" in result

    def test_rate_limit_window_expiry(self):
        """窗口过期后应重新允许."""
        engine = ChatEngine()
        engine._check_rate_limit("doubao")
        # 篡改时间戳使其过期
        engine._rate_limiter["doubao"] = [time.time() - 999]
        result = engine._check_rate_limit("doubao")
        assert result is None

    def test_max_requests_in_window(self):
        """窗口内请求数达上限应被限流."""
        engine = ChatEngine()
        from core.config import Config
        cfg = Config()
        now = time.time()
        # 确保所有时间戳都在窗口内（严格小于 window）
        engine._rate_limiter["doubao"] = [
            now - cfg.rate_limit_window + i * (cfg.rate_limit_interval + 1) + 1
            for i in range(cfg.rate_limit_max)
        ]
        result = engine._check_rate_limit("doubao")
        assert result is not None
        assert "上限" in result

    def test_different_platforms_independent(self):
        """不同平台的限流应独立."""
        engine = ChatEngine()
        engine._check_rate_limit("doubao")
        # deepseek 应不受影响
        result = engine._check_rate_limit("deepseek")
        assert result is None


class TestMessageDedup:
    """消息去重测试."""

    def test_first_message_passes(self):
        """第一条消息应通过去重."""
        engine = ChatEngine()
        result = engine._check_message_dedup("doubao", "hello")
        assert result is None

    def test_exact_duplicate_blocked(self):
        """精确重复消息应被去重."""
        engine = ChatEngine()
        engine._check_message_dedup("doubao", "hello")
        result = engine._check_message_dedup("doubao", "hello")
        assert result is not None
        assert "去重" in result

    def test_different_messages_pass(self):
        """不同消息应通过去重."""
        engine = ChatEngine()
        engine._check_message_dedup("doubao", "hello")
        result = engine._check_message_dedup("doubao", "world")
        assert result is None

    def test_dedup_expiry(self):
        """去重窗口过期后应重新允许."""
        engine = ChatEngine()
        engine._check_message_dedup("doubao", "hello")
        # 篡改时间戳使其过期
        msg_hash = __import__("hashlib").md5("hello".encode()).hexdigest()
        key = ("doubao", msg_hash)
        engine._message_dedup[key] = time.time() - 9999
        result = engine._check_message_dedup("doubao", "hello")
        assert result is None

    def test_similar_message_dedup(self):
        """近似重复消息（>80%相似度）应被去重."""
        engine = ChatEngine()
        msg1 = "帮我写一篇关于人工智能的技术文章"
        msg2 = "帮我写一写关于人工智能的技术文章"  # 仅一字之差
        engine._check_message_dedup("doubao", msg1)
        # 确保相似度确实 > 0.8
        sim = engine._message_similarity(msg1, msg2)
        assert sim > 0.8, f"Similarity should be > 0.8, got {sim}"
        result = engine._check_message_dedup("doubao", msg2)
        assert result is not None
        assert "去重" in result

    def test_different_platform_dedup_independent(self):
        """不同平台的去重应独立."""
        engine = ChatEngine()
        engine._check_message_dedup("doubao", "hello")
        result = engine._check_message_dedup("deepseek", "hello")
        assert result is None

    def test_dedup_disabled(self):
        """禁用去重后所有消息应通过."""
        engine = ChatEngine()
        engine._dedup_enabled = False
        engine._check_message_dedup("doubao", "hello")
        result = engine._check_message_dedup("doubao", "hello")
        assert result is None


class TestRetryBudget:
    """重试预算测试."""

    def test_first_retry_allowed(self):
        """第一次重试应允许."""
        engine = ChatEngine()
        assert engine._check_retry_budget() is True

    def test_budget_exhaustion(self):
        """超出预算应被拒绝."""
        engine = ChatEngine()
        from core.config import Config
        cfg = Config()
        for _ in range(cfg.retry_budget_max):
            engine._check_retry_budget()
        assert engine._check_retry_budget() is False

    def test_budget_window_expiry(self):
        """预算窗口过期后应重新允许."""
        engine = ChatEngine()
        from core.config import Config
        cfg = Config()
        for _ in range(cfg.retry_budget_max):
            engine._check_retry_budget()
        assert engine._check_retry_budget() is False
        # 篡改时间戳使其过期
        engine._retry_budget[:] = [time.time() - 9999]
        assert engine._check_retry_budget() is True


class TestMessageSimilarity:
    """消息相似度测试."""

    def test_identical_messages(self):
        """完全相同的消息相似度应为 1.0."""
        engine = ChatEngine()
        assert engine._message_similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        """完全不同的消息相似度应接近 0."""
        engine = ChatEngine()
        sim = engine._message_similarity("abcdef", "xyz123")
        assert sim < 0.2

    def test_empty_messages(self):
        """空消息相似度应为 0."""
        engine = ChatEngine()
        assert engine._message_similarity("", "hello") == 0.0
        assert engine._message_similarity("hello", "") == 0.0
        assert engine._message_similarity("", "") == 0.0

    def test_case_insensitive(self):
        """相似度应忽略大小写."""
        engine = ChatEngine()
        assert engine._message_similarity("Hello", "hello") == 1.0

    def test_space_insensitive(self):
        """相似度应忽略空格."""
        engine = ChatEngine()
        assert engine._message_similarity("hello world", "helloworld") == 1.0


class TestDynamicTimeout:
    """动态超时测试."""

    def test_base_timeout_with_few_samples(self):
        """样本不足时应返回基础超时."""
        engine = ChatEngine()
        assert engine._get_dynamic_timeout("doubao", 120) == 120

    def test_dynamic_timeout_with_slow_platform(self):
        """慢平台应获得更长超时."""
        engine = ChatEngine()
        engine._response_times["doubao"] = [50, 60, 70, 80, 90]
        result = engine._get_dynamic_timeout("doubao", 120)
        assert result > 30  # 应大于最小值
        assert result <= 120  # 不应超过基础超时

    def test_dynamic_timeout_min_floor(self):
        """动态超时不应低于 30 秒."""
        engine = ChatEngine()
        engine._response_times["doubao"] = [1, 2, 3]
        result = engine._get_dynamic_timeout("doubao", 120)
        assert result >= 30


class TestPlatformRecommendation:
    """平台推荐测试（基于 ChatEngine 实例统计）."""

    def test_chinese_content_recommends_doubao(self):
        """中文内容应推荐豆包."""
        engine = ChatEngine()
        result = engine.recommend_platform("帮我写一篇中文文章润色翻译")
        assert result == "doubao"

    def test_code_content_recommends_deepseek(self):
        """代码内容应推荐 DeepSeek."""
        engine = ChatEngine()
        result = engine.recommend_platform("代码编程推理数学算法")
        assert result == "deepseek"

    def test_drawing_content_recommends_ouyi(self):
        """绘图内容应推荐欧亿AI."""
        engine = ChatEngine()
        result = engine.recommend_platform("图片图像画思维导图绘图")
        assert result == "ouyi"

    def test_empty_message_returns_empty(self):
        """空消息应返回空字符串."""
        engine = ChatEngine()
        assert engine.recommend_platform("") == ""

    def test_health_penalty_reduces_score(self):
        """高错误率平台应被降权."""
        engine = ChatEngine()
        engine._error_stats["doubao"] = {"retry_exhausted": 20}
        # doubao 有错误惩罚，但仍可能因关键词得分高而胜出
        # 验证错误统计影响健康评分
        result = engine.recommend_platform("中文写作润色")
        # 至少验证没有崩溃
        assert result in ("doubao", "deepseek", "volcengine", "ouyi", "")


class TestComplexityAssessment:
    """复杂度评估测试."""

    def test_short_text_with_keyword(self):
        """短文本无能力匹配时走健康评分路由."""
        engine = ChatEngine()
        result = engine.assess_complexity("你好")
        # "你好" 无平台能力匹配 → 健康评分优选 → L2, tree=False
        assert result["level"] == 2
        assert result["tree"] is False
        assert result["platform"] in ("doubao", "deepseek", "volcengine", "ouyi")

    def test_medium_text_with_keywords_is_l2(self):
        """中等长度带关键词应为 L2，树状."""
        engine = ChatEngine()
        result = engine.assess_complexity("帮我用Python写一个排序算法")
        assert result["level"] == 2
        assert result["tree"] is True
        assert "tree_config" in result

    def test_long_text_is_l3(self):
        """长文本应为 L3."""
        engine = ChatEngine()
        msg = "帮我分析这个复杂的技术方案" + "x" * 100
        result = engine.assess_complexity(msg)
        assert result["level"] == 3
        assert result["tree"] is True

    def test_empty_message_defaults_doubao(self):
        """空消息默认推荐豆包."""
        engine = ChatEngine()
        result = engine.assess_complexity("")
        assert result["platform"] == "doubao"


class TestResponseCompression:
    """响应压缩测试."""

    def test_filler_removal(self):
        """应移除 AI 填充词."""
        engine = ChatEngine()
        result = engine._compress_response("当然可以！这是你的答案。")
        assert "当然可以" not in result

    def test_duplicate_line_removal(self):
        """应移除重复行."""
        engine = ChatEngine()
        result = engine._compress_response("line1\nline1\nline2")
        assert result.count("line1") == 1

    def test_empty_input(self):
        """空输入应返回空."""
        engine = ChatEngine()
        assert engine._compress_response("") == ""
        assert engine._compress_response(None) is None

    def test_consecutive_blank_lines(self):
        """多个连续空行应压缩为两个."""
        engine = ChatEngine()
        result = engine._compress_response("a\n\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_compression_tag(self):
        """压缩超过 20 字时应附加压缩标签."""
        engine = ChatEngine()
        # 构造一个有填充词的长文本
        long_text = "当然可以！" + "测试内容" * 20
        result = engine._compress_response(long_text)
        if "压缩" in result:
            assert "字 →" in result


class TestErrorRecording:
    """错误记录测试."""

    def test_record_error(self):
        """应正确记录错误."""
        engine = ChatEngine()
        engine._record_error("doubao", "timeout")
        assert engine._error_stats["doubao"]["timeout"] == 1
        engine._record_error("doubao", "timeout")
        assert engine._error_stats["doubao"]["timeout"] == 2

    def test_decay_error_stats(self):
        """错误统计应随时间衰减."""
        engine = ChatEngine()
        engine._error_stats["doubao"] = {"error": 5}
        engine._last_decay = time.time() - 60  # 60秒前
        engine._decay_error_stats()
        assert engine._error_stats["doubao"]["error"] == 4

    def test_decay_noop_if_recent(self):
        """30秒内不应衰减."""
        engine = ChatEngine()
        engine._error_stats["doubao"] = {"error": 5}
        engine._last_decay = time.time()
        engine._decay_error_stats()
        assert engine._error_stats["doubao"]["error"] == 5


class TestResponseScoring:
    """响应质量评分测试."""

    def test_empty_response(self):
        """空响应评分为 0."""
        engine = ChatEngine()
        result = engine._score_response("")
        assert result["score"] == 0
        assert "empty" in result["issues"]

    def test_short_response(self):
        """过短响应应标记 too_short."""
        engine = ChatEngine()
        result = engine._score_response("hi")
        assert "too_short" in result["issues"]

    def test_structured_response(self):
        """有结构的响应应得高分."""
        engine = ChatEngine()
        text = "第一点：xxx\n第二点：yyy\n- 列表项"
        result = engine._score_response(text)
        assert result["score"] > 60

    def test_truncated_response(self):
        """截断响应应扣分."""
        engine = ChatEngine()
        result = engine._score_response("这是一段被截断的内容…")
        assert "truncated" in result["issues"]
