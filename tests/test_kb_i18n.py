"""i18n module tests"""

import importlib
import os
from pathlib import Path
from unittest.mock import patch

import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from i18n import I18n, get_i18n, t


@pytest.fixture(autouse=True)
def reset_i18n():
    """Reset global _i18n singleton before each test."""
    import i18n as i18n_mod
    i18n_mod._i18n = None
    yield
    i18n_mod._i18n = None


class TestTFunction:
    def test_t_returns_translated_text(self):
        """t() returns the translated string for known keys."""
        result = t("init.success")
        assert result == "知识库已初始化"

    def test_t_with_params(self):
        """t() supports variable substitution."""
        result = t("query.found", count=5)
        assert "5" in result

    def test_t_with_path_param(self):
        """t() handles path parameter substitution."""
        result = t("error.file_not_found", path="/some/file.md")
        assert "/some/file.md" in result

    def test_t_with_format_param(self):
        """t() handles format parameter substitution."""
        result = t("error.unsupported_format", format=".xlsx")
        assert ".xlsx" in result

    def test_missing_key_returns_key(self):
        """Missing translation key returns the key itself."""
        result = t("nonexistent.key.12345")
        assert result == "nonexistent.key.12345"


class TestI18nClass:
    def test_i18n_zh_default(self):
        """Default language is zh."""
        i = I18n("zh")
        assert i.lang == "zh"
        assert i.t("init.success") == "知识库已初始化"

    def test_i18n_en(self):
        """English translations work."""
        i = I18n("en")
        assert i.lang == "en"
        assert i.t("init.success") == "Knowledge base initialized"

    def test_i18n_en_with_params(self):
        """English translations support params."""
        i = I18n("en")
        result = i.t("query.found", count=3)
        assert "3" in result


class TestLangDetection:
    def test_lang_detection_from_env(self):
        """Language detected from KB_LANG env var."""
        with patch.dict(os.environ, {"KB_LANG": "en"}):
            i = I18n()
            assert i.lang == "en"

    def test_lang_detection_zh_from_lang_var(self):
        """Language detected from LANG env var (zh prefix)."""
        with patch.dict(os.environ, {"KB_LANG": "", "LANG": "zh_CN.UTF-8"}, clear=False):
            i = I18n()
            assert i.lang == "zh"

    def test_lang_detection_fallback_zh(self):
        """Default fallback is zh when no env var set."""
        with patch.dict(os.environ, {"KB_LANG": "", "LANG": "en_US.UTF-8"}, clear=False):
            i = I18n()
            assert i.lang == "zh"


class TestOverrideLang:
    def test_override_lang_parameter(self):
        """Explicit lang parameter overrides detection."""
        with patch.dict(os.environ, {"KB_LANG": "zh"}):
            i = I18n("en")
            assert i.lang == "en"
            assert i.t("init.success") == "Knowledge base initialized"

    def test_get_i18n_with_lang(self):
        """get_i18n(lang) creates instance with specified language."""
        i = get_i18n("en")
        assert i.lang == "en"

    def test_get_i18n_singleton(self):
        """get_i18n returns same instance for same lang."""
        i1 = get_i18n("zh")
        i2 = get_i18n("zh")
        assert i1 is i2

    def test_get_i18n_recreates_for_different_lang(self):
        """get_i18n creates new instance when lang changes."""
        i1 = get_i18n("zh")
        i2 = get_i18n("en")
        assert i1 is not i2
        assert i2.lang == "en"
