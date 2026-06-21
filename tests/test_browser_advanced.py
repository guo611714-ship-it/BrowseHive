"""浏览器高级工具测试 — exec_js/multi_tab/wait_for/fill_form/upload_file/manage_cookie"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path


class TestExecJs:
    """exec_js_tool 测试"""

    @pytest.mark.asyncio
    async def test_empty_code_returns_error(self):
        from agent.tools.browser.advanced import exec_js_tool
        result = await exec_js_tool("")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_error(self):
        from agent.tools.browser.advanced import exec_js_tool
        result = await exec_js_tool("   ")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_code_too_long(self):
        from agent.tools.browser.advanced import exec_js_tool
        result = await exec_js_tool("x" * 50001)
        assert result.get("code") != 200


class TestMultiTab:
    """multi_tab 测试"""

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from agent.tools.browser.advanced import multi_tab
        result = await multi_tab(action="invalid")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_create_without_url(self):
        from agent.tools.browser.advanced import multi_tab
        result = await multi_tab(action="create", url="")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_list_no_browser(self):
        from agent.tools.browser.advanced import multi_tab
        with patch("agent.tools.browser.advanced.detect_cdp_url", new_callable=AsyncMock, return_value=None):
            result = await multi_tab(action="list")
            assert result.get("code") == 503


class TestWaitFor:
    """wait_for 测试"""

    @pytest.mark.asyncio
    async def test_text_condition_empty(self):
        from agent.tools.browser.advanced import wait_for
        result = await wait_for(condition="text:", value="", timeout=1)
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_url_condition_empty(self):
        from agent.tools.browser.advanced import wait_for
        result = await wait_for(condition="url:", value="", timeout=1)
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_timeout_capped_at_30(self):
        from agent.tools.browser.advanced import wait_for
        with patch("agent.tools.browser.advanced._exec_js", new_callable=AsyncMock,
                   return_value={"code": 200, "data": '{"found":false}'}):
            result = await wait_for(condition="div#test", timeout=999)
            # Should complete quickly since timeout is capped
            assert result.get("code") in (200, 303)


class TestFillForm:
    """fill_form 测试"""

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        from agent.tools.browser.advanced import fill_form
        result = await fill_form(fields="not json")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_empty_fields(self):
        from agent.tools.browser.advanced import fill_form
        result = await fill_form(fields="[]")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_fields_with_string_input(self):
        from agent.tools.browser.advanced import fill_form
        with patch("agent.tools.browser.advanced._exec_js", new_callable=AsyncMock,
                   return_value={"code": 200, "data": '{"ok":true}'}):
            result = await fill_form(fields='[{"selector":"#name","value":"test"}]')
            assert result.get("code") == 200
            assert result["data"]["success"] == 1


class TestManageCookie:
    """manage_cookie 测试"""

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from agent.tools.browser.advanced import manage_cookie
        result = await manage_cookie(action="invalid")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_set_without_name(self):
        from agent.tools.browser.advanced import manage_cookie
        result = await manage_cookie(action="set", name="", value="v")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_delete_without_name(self):
        from agent.tools.browser.advanced import manage_cookie
        result = await manage_cookie(action="delete", name="")
        assert result.get("code") != 200


class TestPageMonitor:
    """page_monitor 测试"""

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from agent.tools.browser.intelligence import page_monitor
        result = await page_monitor(action="invalid")
        assert result.get("code") != 200

    @pytest.mark.asyncio
    async def test_snapshot_no_browser(self):
        from agent.tools.browser.intelligence import page_monitor
        with patch("agent.tools.browser.advanced.detect_cdp_url", new_callable=AsyncMock, return_value=None):
            # snapshot doesn't check cdp_url directly, it calls _exec_js
            with patch("agent.tools.browser.intelligence._exec_js", new_callable=AsyncMock,
                       return_value={"code": 500, "error": "no connection"}):
                result = await page_monitor(action="snapshot")
                assert result.get("code") == 500
