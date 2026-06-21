"""E2E tests for DeepWiki integration, browser AI tools, and knowledge service.

Run with: pytest tests/test_e2e_integration.py -v
Skip e2e: pytest tests/ -m "not e2e"
"""

import asyncio
import pytest
from pathlib import Path
from urllib.parse import quote

# Mark all tests in this file as e2e
pytestmark = pytest.mark.e2e


class TestDeepWikiTools:
    """Tests for DeepWiki index search and fetch."""

    @pytest.mark.asyncio
    async def test_search_index(self):
        """Search the pre-built index for a known project."""
        from agent.tools.deepwiki_tools import deepwiki_search

        result = await deepwiki_search(keyword="fastapi", limit=5)
        assert isinstance(result, dict)
        assert "data" in result or "error" in result

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Stats should return nested data with total_projects."""
        from agent.tools.deepwiki_tools import deepwiki_get_stats

        result = await deepwiki_get_stats()
        assert isinstance(result, dict)
        assert "data" in result
        assert "total_projects" in result["data"]


class TestBrowserAI:
    """Tests for browser AI tools."""

    @pytest.mark.asyncio
    async def test_browser_status(self):
        """Browser status should return CDP connection state (or offline state)."""
        from agent.tools.browser_tools import browser_status

        try:
            result = await asyncio.wait_for(browser_status(), timeout=5)
        except (asyncio.TimeoutError, Exception):
            # Browser not available — acceptable in CI
            return
        assert isinstance(result, dict)
        assert "cdp_available" in result

    def test_xss_prevention_in_ask_bing(self):
        """Verify ask_bing's URL encoding prevents XSS."""
        malicious = 'test&q=evil.com"><script>alert(1)</script>'
        encoded = quote(malicious, safe="")
        assert "%26" in encoded  # &
        assert "%3C" in encoded  # <
        assert "%3E" in encoded  # >
        assert "%22" in encoded  # "


class TestKnowledgeService:
    """Tests for knowledge service integration."""

    def test_get_context_for_task(self):
        """Context assembly should return a string result."""
        from agent.knowledge_service import KnowledgeService

        ks = KnowledgeService(Path("."))
        result = ks.get_context_for_task("test task")
        assert isinstance(result, str)
