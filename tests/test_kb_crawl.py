"""kb_crawl 模块测试"""

import json
import hashlib
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools.kb_crawl import (
    _ok, _err, _generate_hash, _format_doc, kb_crawl
)


class TestOk:
    def test_default(self):
        result = _ok()
        assert result["code"] == 200
        assert result["msg"] == "success"
        assert result["data"] == {}

    def test_with_data_and_msg(self):
        result = _ok({"key": "val"}, msg="done")
        assert result["code"] == 200
        assert result["msg"] == "done"
        assert result["data"] == {"key": "val"}


class TestErr:
    def test_error_response(self):
        result = _err(500, "fail")
        assert result["code"] == 500
        assert result["msg"] == "fail"
        assert result["data"] == {}


class TestGenerateHash:
    def test_deterministic(self):
        h1 = _generate_hash("https://example.com")
        h2 = _generate_hash("https://example.com")
        assert h1 == h2

    def test_different_urls(self):
        h1 = _generate_hash("https://a.com")
        h2 = _generate_hash("https://b.com")
        assert h1 != h2

    def test_length(self):
        h = _generate_hash("https://test.com")
        assert len(h) == 8


class TestFormatDoc:
    def test_basic_format(self):
        doc = _format_doc("Title", "Some content", "https://example.com", ["tag1"], ["Entity"])
        assert "# Title" in doc
        assert "Some content" in doc
        assert "https://example.com" in doc
        assert "tag1" in doc
        assert "Entity" in doc
        assert "---" in doc

    def test_empty_tags_uses_default(self):
        doc = _format_doc("T", "C", "url", [], [])
        assert "网页内容" in doc

    def test_long_content_truncated_in_summary(self):
        long_content = "x" * 1000
        doc = _format_doc("T", long_content, "url", [], [])
        assert long_content[:500] in doc


class TestKbCrawl:
    @pytest.mark.asyncio
    async def test_empty_content_returns_error(self):
        with patch("agent.tools.browser_tools.get_page_text", return_value={"code": 200, "data": {"content": ""}}):
            result = await kb_crawl("https://example.com")
            assert result["code"] == 422

    @pytest.mark.asyncio
    async def test_page_extract_failure(self):
        with patch("agent.tools.browser_tools.get_page_text", return_value={"code": 500, "msg": "timeout"}):
            result = await kb_crawl("https://example.com")
            assert result["code"] == 500

    @pytest.mark.asyncio
    async def test_successful_crawl(self, tmp_path):
        with patch("agent.tools.kb_crawl._KB_IMPORT_DIR", tmp_path), \
             patch("agent.tools.browser_tools.get_page_text", return_value={"code": 200, "data": {"content": "Hello World"}}):
            result = await kb_crawl("https://example.com/test", category="tech")
            assert result["code"] == 200
            assert result["data"]["title"] == "Hello World"
            assert "tech" in result["data"]["tags"]
            files = list(tmp_path.glob("*.md"))
            assert len(files) == 1
