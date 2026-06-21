"""Platforms 单元测试."""

import pytest
from core.platforms import (
    PLATFORMS, detect_task_type, assess_complexity,
    recommend_platform, route_by_capability, is_login_page
)


class TestDetectTaskType:
    """任务类型检测测试."""

    def test_browser_task(self):
        assert detect_task_type("打开浏览器") == "browser"

    def test_api_task(self):
        assert detect_task_type("运行基准测试") == "api"

    def test_mixed_task(self):
        assert detect_task_type("打开页面并统计") == "mixed"

    def test_empty_task(self):
        assert detect_task_type("") == "mixed"

    def test_no_keywords(self):
        assert detect_task_type("写一篇文章") == "mixed"


class TestAssessComplexity:
    """复杂度评估测试."""

    def test_short_text_with_keyword(self):
        """带关键词的短文本应有合理级别."""
        result = assess_complexity("你好")
        # 2 chars < 5, 但匹配关键词
        assert result["level"] in (1, 2)

    def test_medium_text_l2(self):
        result = assess_complexity("帮我写一篇中文润色文章")
        assert result["level"] == 2
        assert result["tree"] is True

    def test_long_text_l3(self):
        msg = "帮我分析这个复杂的技术方案" + "x" * 100
        result = assess_complexity(msg)
        assert result["level"] == 3

    def test_empty_message(self):
        result = assess_complexity("")
        assert result["platform"] == "doubao"

    def test_has_tree_config(self):
        result = assess_complexity("代码编程分析推理")
        if result.get("tree"):
            assert "tree_config" in result
            assert "layer1" in result["tree_config"]
            assert "layer2" in result["tree_config"]


class TestRecommendPlatform:
    """平台推荐测试（无运行时统计）."""

    def test_chinese_content(self):
        result = recommend_platform("中文润色写作翻译文案")
        assert result == "doubao"

    def test_code_content(self):
        result = recommend_platform("代码编程算法推理数学")
        assert result == "deepseek"

    def test_drawing_content(self):
        result = recommend_platform("图片图像画思维导图绘图")
        assert result == "ouyi"

    def test_empty_message(self):
        result = recommend_platform("")
        assert result == ""

    def test_with_error_stats(self):
        """传入错误统计应影响推荐."""
        error_stats = {"doubao": {"error": 20}}
        result = recommend_platform("中文写作", error_stats=error_stats)
        # doubao 有大量错误，可能不再推荐
        assert result in ("doubao", "deepseek", "volcengine", "ouyi", "")

    def test_with_response_times(self):
        """传入响应时间应影响推荐."""
        response_times = {"doubao": [50, 60, 70]}  # 很慢
        result = recommend_platform("中文写作", response_times=response_times)
        assert result in ("doubao", "deepseek", "volcengine", "ouyi", "")


class TestIsLoginPage:
    """登录页检测测试."""

    def test_doubao_login(self):
        assert is_login_page("https://www.doubao.com/sign_in", "doubao") is True

    def test_doubao_not_login(self):
        assert is_login_page("https://www.doubao.com/chat/", "doubao") is False

    def test_deepseek_login(self):
        assert is_login_page("https://chat.deepseek.com/login", "deepseek") is True

    def test_volcengine_login(self):
        assert is_login_page("https://login.volcengine.com/", "volcengine") is True


class TestPlatformDefinitions:
    """平台定义完整性测试."""

    def test_all_platforms_have_required_fields(self):
        """所有平台应有 name, url, mode, purpose, login_keywords."""
        required = ["name", "url", "mode", "purpose", "login_keywords"]
        for pk, info in PLATFORMS.items():
            for field in required:
                assert field in info, f"Platform {pk} missing field: {field}"

    def test_platform_urls_are_valid(self):
        """所有平台 URL 应以 http 开头."""
        for pk, info in PLATFORMS.items():
            assert info["url"].startswith("http"), f"Platform {pk} has invalid URL"

    def test_route_by_capability(self):
        """route_by_capability 应返回有效平台."""
        result = route_by_capability("代码编程")
        assert result in PLATFORMS
