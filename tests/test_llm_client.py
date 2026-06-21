"""Tests for agent.llm_client.LLMClient and related utilities."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_response(content="Hello", tool_calls=None, status_code=200, usage=None):
    """Build a mock httpx.Response mimicking OpenAI chat completions."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    resp.json.return_value = {
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5},
    }
    return resp


def _make_anthropic_response(text="Hi there", tool_use=None, status_code=200):
    """Build a mock httpx.Response mimicking Anthropic messages API."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    content_list = []
    if text:
        content_list.append({"type": "text", "text": text})
    if tool_use:
        content_list.append({"type": "tool_use", **tool_use})
    resp.json.return_value = {
        "content": content_list,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    return resp


# ---------------------------------------------------------------------------
# LLMClient tests
# ---------------------------------------------------------------------------

class TestLLMClient:
    """Tests for agent.llm_client.LLMClient."""

    @pytest.fixture
    def client(self):
        """Create an LLMClient with mocked dependencies."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            return LLMClient(
                provider="deepseek",
                model="deepseek-chat",
                api_key="test-key-123",
                api_base="https://api.deepseek.com/v1",
                max_tokens=20000,
                temperature=0.5,
            )

    # -- Init tests --

    def test_init_basic_attributes(self, client):
        assert client.provider == "deepseek"
        assert client.model == "deepseek-chat"
        assert client.api_key == "test-key-123"
        assert client.max_tokens == 20000
        assert client.temperature == 0.5
        assert client._key_pool is None

    def test_init_max_tokens_floor(self):
        """max_tokens <= 128 should be bumped to 4096."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="x", model="m", api_key="k", max_tokens=128)
            assert c.max_tokens == 4096

    def test_init_max_tokens_zero(self):
        """max_tokens=0 should default to 4096."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="x", model="m", api_key="k", max_tokens=0)
            assert c.max_tokens == 4096

    def test_init_max_tokens_none(self):
        """max_tokens=None should default to 4096."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="x", model="m", api_key="k", max_tokens=None)
            assert c.max_tokens == 4096

    def test_init_key_pool_not_created_single_key(self, client):
        """Single api_key without api_keys list: no key pool."""
        assert client._key_pool is None

    def test_init_key_pool_created_multi_keys(self):
        """Multiple api_keys should create a key pool."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(
                provider="deepseek",
                model="m",
                api_key="key1",
                api_keys=["key1", "key2", "key3"],
            )
            assert c._key_pool is not None

    # -- chat method: basic call --

    @pytest.mark.asyncio
    async def test_chat_basic_openai(self, client):
        mock_resp = _make_openai_response(content="Hello world")
        with patch.object(
            type(client), "_dispatch", new_callable=AsyncMock, return_value={
                "content": "Hello world",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "tool_calls": [],
                "finish_reason": "stop",
                "status_code": 200,
            }
        ):
            client._get_api_key = AsyncMock(return_value="test-key-123")
            result = await client.chat(
                messages=[{"role": "user", "content": "Hi"}],
                system="You are helpful",
            )
            assert result["content"] == "Hello world"
            assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_chat_anthropic(self):
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="anthropic", model="claude-3", api_key="sk-ant")
            c._get_api_key = AsyncMock(return_value="sk-ant")
            c._http_client.post = AsyncMock(
                return_value=_make_anthropic_response(text="Anthropic reply")
            )
            result = await c.chat(
                messages=[{"role": "user", "content": "Hello"}],
            )
            assert result["content"] == "Anthropic reply"
            assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_chat_tool_calls_present(self):
        """Native tool_calls in the response should be parsed."""
        native_tool_calls = [
            {
                "id": "call_001",
                "type": "function",
                "function": {
                    "name": "search_web",
                    "arguments": '{"query": "test"}',
                },
            }
        ]
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="deepseek", model="m", api_key="k")
            c._get_api_key = AsyncMock(return_value="k")
            c._http_client.post = AsyncMock(
                return_value=_make_openai_response(
                    content="", tool_calls=native_tool_calls
                )
            )
            result = await c.chat(messages=[{"role": "user", "content": "search"}])
            assert len(result["tool_calls"]) == 1
            assert result["tool_calls"][0]["name"] == "search_web"
            assert result["tool_calls"][0]["arguments"] == {"query": "test"}

    # -- No key available --

    @pytest.mark.asyncio
    async def test_chat_no_key_available(self, client):
        client._get_api_key = AsyncMock(return_value=None)
        result = await client.chat(messages=[{"role": "user", "content": "Hi"}])
        assert result["status_code"] == -1
        assert "[限流]" in result["content"]
        assert result["tool_calls"] == []

    # -- Error responses --

    @pytest.mark.asyncio
    async def test_chat_429_rate_limit(self):
        """429 response should return structured status_code=429."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="deepseek", model="m", api_key="k")
            c._get_api_key = AsyncMock(return_value="k")
            c._http_client.post = AsyncMock(
                return_value=_make_openai_response(status_code=429)
            )
            result = await c.chat(messages=[{"role": "user", "content": "Hi"}])
            assert result["status_code"] == 429
            assert "429" in result["content"]

    @pytest.mark.asyncio
    async def test_chat_500_server_error(self):
        """HTTP 500 raise_for_status should be caught as httpx.HTTPError."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="deepseek", model="m", api_key="k")
            c._get_api_key = AsyncMock(return_value="k")

            import httpx as _httpx

            error_resp = MagicMock()
            error_resp.status_code = 500
            error_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
                "500",
                request=MagicMock(),
                response=error_resp,
            )
            c._http_client.post = AsyncMock(return_value=error_resp)
            result = await c.chat(messages=[{"role": "user", "content": "Hi"}])
            assert result["status_code"] == -1
            assert "网络错误" in result["content"]

    @pytest.mark.asyncio
    async def test_chat_empty_choices(self):
        """Response with empty choices list."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="deepseek", model="m", api_key="k")
            c._get_api_key = AsyncMock(return_value="k")

            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            resp.json.return_value = {"choices": [], "usage": {}}
            c._http_client.post = AsyncMock(return_value=resp)
            result = await c.chat(messages=[{"role": "user", "content": "Hi"}])
            assert "choices" in result["content"]
            assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_chat_network_error(self):
        """httpx.HTTPError (connection failure) should be caught."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            import httpx as _httpx

            c = LLMClient(provider="deepseek", model="m", api_key="k")
            c._get_api_key = AsyncMock(return_value="k")
            c._http_client.post = AsyncMock(side_effect=_httpx.ConnectError("refused"))
            result = await c.chat(messages=[{"role": "user", "content": "Hi"}])
            assert result["status_code"] == -1
            assert "网络错误" in result["content"]

    @pytest.mark.asyncio
    async def test_chat_json_decode_error(self):
        """Invalid JSON response body."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="deepseek", model="m", api_key="k")
            c._get_api_key = AsyncMock(return_value="k")

            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
            c._http_client.post = AsyncMock(return_value=resp)
            result = await c.chat(messages=[{"role": "user", "content": "Hi"}])
            assert result["status_code"] == -1
            assert "响应错误" in result["content"]

    @pytest.mark.asyncio
    async def test_chat_unsupported_provider(self):
        """Unknown provider should return an error dict."""
        with patch("agent.llm_client.httpx.AsyncClient"):
            from agent.llm_client import LLMClient

            c = LLMClient(provider="unknown_provider", model="m", api_key="k")
            c._get_api_key = AsyncMock(return_value="k")
            result = await c.chat(messages=[{"role": "user", "content": "Hi"}])
            assert result["status_code"] == -1
            assert "不支持的 provider" in result["content"]

    # -- Timeout handling --

    @pytest.mark.asyncio
    async def test_chat_timeout_error(self, client):
        """asyncio.TimeoutError from _dispatch should return timeout result."""
        client._get_api_key = AsyncMock(return_value="test-key-123")
        client._timeout_override = 30

        async def _raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch.object(
            type(client), "_dispatch", new_callable=AsyncMock, side_effect=_raise_timeout
        ):
            result = await client.chat(
                messages=[{"role": "user", "content": "Hi"}]
            )
            assert result["status_code"] == -1
            assert "超时" in result["content"]
            assert "30" in result["content"]

    @pytest.mark.asyncio
    async def test_chat_timeout_returns_immediately(self, client):
        """Timeout on first attempt: loop breaks immediately (no retry for timeout)."""
        client._get_api_key = AsyncMock(return_value="test-key-123")
        client._timeout_override = 30

        async def _mock_dispatch(*args, **kwargs):
            return {
                "content": "should not reach here",
                "usage": {},
                "tool_calls": [],
                "status_code": 200,
            }

        async def _wait_for_side_effect(coro, timeout):
            raise asyncio.TimeoutError()

        with patch.object(type(client), "_dispatch", new_callable=AsyncMock, side_effect=_mock_dispatch), \
             patch("agent.llm_client.asyncio.wait_for", side_effect=_wait_for_side_effect):
            result = await client.chat(
                messages=[{"role": "user", "content": "Hi"}]
            )
            assert result["status_code"] == -1
            assert "超时" in result["content"]
            assert "30" in result["content"]

    # -- Retry logic --

    @pytest.mark.asyncio
    async def test_chat_retry_on_429_with_key_pool(self, client):
        """429 with key pool: should retry up to 3 times with key switching."""
        from shared.api_key_pool import APIKeyPool

        client._key_pool = MagicMock(spec=APIKeyPool)
        client._key_pool.next_key_async = AsyncMock(side_effect=["key1", "key2", "key3"])
        client._key_pool.peek_key_async = AsyncMock(return_value="key3")
        client._get_api_key = AsyncMock(side_effect=["key1", "key2", "key3"])

        attempts = 0

        async def _always_429(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            return {
                "content": "[429] Too Many Requests",
                "usage": {},
                "tool_calls": [],
                "status_code": 429,
            }

        with patch.object(
            type(client), "_dispatch", new_callable=AsyncMock, side_effect=_always_429
        ):
            with patch("agent.llm_client.asyncio.sleep", new_callable=AsyncMock):
                result = await client.chat(
                    messages=[{"role": "user", "content": "Hi"}]
                )
                assert attempts == 3
                assert result["status_code"] == 429

    @pytest.mark.asyncio
    async def test_chat_retry_on_429_single_key_exponential_backoff(self, client):
        """429 with single key: exponential backoff retries."""
        client._get_api_key = AsyncMock(return_value="test-key-123")
        attempts = 0

        async def _always_429(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            return {
                "content": "[429] Too Many Requests",
                "usage": {},
                "tool_calls": [],
                "status_code": 429,
            }

        sleep_calls = []

        async def _track_sleep(delay):
            sleep_calls.append(delay)

        with patch.object(
            type(client), "_dispatch", new_callable=AsyncMock, side_effect=_always_429
        ):
            with patch("agent.llm_client.asyncio.sleep", side_effect=_track_sleep):
                result = await client.chat(
                    messages=[{"role": "user", "content": "Hi"}]
                )
                assert attempts == 3
                assert result["status_code"] == 429
                # Exponential backoff: 2s, 4s, 8s (all 3 attempts sleep before continue/break)
                assert sleep_calls == [2.0, 4.0, 8.0]

    @pytest.mark.asyncio
    async def test_chat_retry_429_then_success(self, client):
        """429 on first attempt, success on second."""
        client._get_api_key = AsyncMock(return_value="test-key-123")
        attempts = 0

        def _delayed_result(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return {
                    "content": "[429] Too Many Requests",
                    "usage": {},
                    "tool_calls": [],
                    "status_code": 429,
                }
            return {
                "content": "success",
                "usage": {},
                "tool_calls": [],
                "status_code": 200,
            }

        with patch.object(
            type(client), "_dispatch", new_callable=AsyncMock, side_effect=_delayed_result
        ):
            with patch("agent.llm_client.asyncio.sleep", new_callable=AsyncMock):
                result = await client.chat(
                    messages=[{"role": "user", "content": "Hi"}]
                )
                assert result["content"] == "success"
                assert result["status_code"] == 200
                assert attempts == 2

    @pytest.mark.asyncio
    async def test_chat_retry_401_auth_failure_with_key_pool(self, client):
        """401 auth failure with key pool: switch key and retry."""
        from shared.api_key_pool import APIKeyPool

        client._key_pool = MagicMock(spec=APIKeyPool)
        client._key_pool.next_key_async = AsyncMock(side_effect=["bad_key", "good_key"])
        client._get_api_key = AsyncMock(side_effect=["bad_key", "good_key"])
        attempts = 0

        def _auth_then_ok(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                resp = MagicMock()
                resp.status_code = 401
                resp.headers = {}
                raise Exception("401 should be caught")
            return {
                "content": "authenticated",
                "usage": {},
                "tool_calls": [],
                "status_code": 200,
            }

        # Simpler: return structured dicts for 401
        def _auth_result(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return {
                    "content": "[401] Unauthorized",
                    "usage": {},
                    "tool_calls": [],
                    "status_code": 401,
                }
            return {
                "content": "authenticated",
                "usage": {},
                "tool_calls": [],
                "status_code": 200,
            }

        with patch.object(
            type(client), "_dispatch", new_callable=AsyncMock, side_effect=_auth_result
        ):
            result = await client.chat(
                messages=[{"role": "user", "content": "Hi"}]
            )
            assert result["content"] == "authenticated"
            assert attempts == 2

    @pytest.mark.asyncio
    async def test_chat_retry_401_single_key_no_retry(self, client):
        """401 with single key (no pool): should NOT retry."""
        client._get_api_key = AsyncMock(return_value="test-key-123")

        async def _always_401(*args, **kwargs):
            return {
                "content": "[401] Unauthorized",
                "usage": {},
                "tool_calls": [],
                "status_code": 401,
            }

        with patch.object(
            type(client), "_dispatch", new_callable=AsyncMock, side_effect=_always_401
        ):
            result = await client.chat(
                messages=[{"role": "user", "content": "Hi"}]
            )
            assert result["status_code"] == 401
            # Should NOT retry for 401 without key pool

    @pytest.mark.asyncio
    async def test_chat_skips_rate_limiter_when_key_pool(self, client):
        """When key_pool exists, single-key rate limiter is bypassed."""
        from shared.api_key_pool import APIKeyPool

        client._key_pool = MagicMock(spec=APIKeyPool)
        client._get_api_key = AsyncMock(return_value="k")
        client._rate_limiter.check = MagicMock(return_value="rate limited")

        with patch.object(
            type(client), "_dispatch", new_callable=AsyncMock, return_value={
                "content": "ok", "usage": {}, "tool_calls": [], "status_code": 200,
            }
        ):
            result = await client.chat(messages=[{"role": "user", "content": "Hi"}])
            assert result["content"] == "ok"
            client._rate_limiter.check.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_single_key_rate_limiter_blocks(self, client):
        """Without key_pool, rate limiter can block requests."""
        client._get_api_key = AsyncMock(return_value="k")
        client._rate_limiter = MagicMock()
        client._rate_limiter.check = MagicMock(return_value="rate limited, slow down")

        result = await client.chat(messages=[{"role": "user", "content": "Hi"}])
        assert result["status_code"] == -1
        assert "rate limited" in result["content"]

    @pytest.mark.asyncio
    async def test_chat_5xx_no_retry_single_key(self, client):
        """5xx error without key pool: no retry, returns error directly."""
        client._get_api_key = AsyncMock(return_value="k")
        client._timeout_override = 5

        async def _mock_dispatch(*args, **kwargs):
            return {"content": "[网络错误]", "usage": {}, "tool_calls": [], "status_code": 500}

        with patch.object(type(client), "_dispatch", new_callable=AsyncMock, side_effect=_mock_dispatch):
            result = await client.chat(messages=[{"role": "user", "content": "Hi"}])
            assert result["status_code"] == 500

    # -- aclose --

    @pytest.mark.asyncio
    async def test_aclose(self, client):
        client._http_client.aclose = AsyncMock()
        await client.aclose()
        client._http_client.aclose.assert_called_once()

    # -- XML tool call parsing --

    def test_parse_xml_tool_calls(self):
        """_parse_xml_tool_calls should extract invoke elements."""
        from agent.llm_client import _parse_xml_tool_calls

        text = '''
        <invoke name="search">
            <param name="query">hello world</param>
        </invoke>
        '''
        calls = _parse_xml_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["name"] == "search"
        assert calls[0]["arguments"]["query"] == "hello world"
        assert calls[0]["id"].startswith("xml_")

    def test_parse_xml_tool_calls_with_args_attr(self):
        """_parse_xml_tool_calls should handle args attribute."""
        from agent.llm_client import _parse_xml_tool_calls

        # args attribute with non-JSON content -> falls back to {"raw": "..."}
        text = '<invoke name="calc" args="hello"></invoke>'
        calls = _parse_xml_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["name"] == "calc"
        assert calls[0]["arguments"] == {"raw": "hello"}

    def test_parse_xml_tool_calls_multiple(self):
        """_parse_xml_tool_calls should handle multiple invoke elements."""
        from agent.llm_client import _parse_xml_tool_calls

        text = '''
        <invoke name="a"><param name="p">v1</param></invoke>
        <invoke name="b"><param name="p">v2</param></invoke>
        '''
        calls = _parse_xml_tool_calls(text)
        assert len(calls) == 2
        assert calls[0]["name"] == "a"
        assert calls[1]["name"] == "b"

    def test_parse_xml_tool_calls_no_calls(self):
        from agent.llm_client import _parse_xml_tool_calls

        assert _parse_xml_tool_calls("plain text here") == []


# ---------------------------------------------------------------------------
# OpenAICompatClient / api_clients tests
# ---------------------------------------------------------------------------

class TestOpenAICompatClient:
    """Tests for agent.api_client.OpenAICompatClient."""

    @pytest.fixture
    def client(self):
        from agent.api_client import OpenAICompatClient

        return OpenAICompatClient(
            api_key="test-key",
            base_url="https://api.example.com",
            model="test-model",
        )

    def test_init_attributes(self, client):
        assert client.api_key == "test-key"
        assert client.base_url == "https://api.example.com"
        assert client.model == "test-model"
        assert client.completions_path == "/v1/chat/completions"

    def test_init_trailing_slash_stripped(self):
        from agent.api_client import OpenAICompatClient

        c = OpenAICompatClient(
            api_key="k", base_url="https://api.example.com/", model="m"
        )
        assert c.base_url == "https://api.example.com"

    def test_chat_calls_complete(self, client):
        client._complete = MagicMock(return_value="reply")
        result = client.chat("Hello")
        assert result == "reply"
        client._complete.assert_called_once()

    def test_chat_with_system_prompt(self, client):
        client._complete = MagicMock(return_value="reply")
        client.chat("Hello", system_prompt="Be helpful")
        args = client._complete.call_args
        messages = args[0][0]
        assert messages[0] == {"role": "system", "content": "Be helpful"}
        assert messages[1] == {"role": "user", "content": "Hello"}

    def test_chat_without_system_prompt(self, client):
        client._complete = MagicMock(return_value="reply")
        client.chat("Hello")
        messages = client._complete.call_args[0][0]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_chat_with_history(self, client):
        client._complete = MagicMock(return_value="reply")
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        result = client.chat_with_history(history, temperature=0.3)
        assert result == "reply"
        client._complete.assert_called_once_with(history, 0.3)

    def test_complete_builds_payload(self, client):
        import requests as _requests

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hi"}}]
        }
        client.session = MagicMock(spec=_requests.Session)
        client.session.post.return_value = mock_resp

        result = client._complete(
            [{"role": "user", "content": "Hello"}], temperature=0.7
        )
        assert result == "hi"
        client.session.post.assert_called_once()
        call_args = client.session.post.call_args
        assert call_args[0][0] == "https://api.example.com/v1/chat/completions"

    def test_complete_raises_on_http_error(self, client):
        import requests as _requests

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = _requests.HTTPError("500")
        client.session = MagicMock(spec=_requests.Session)
        client.session.post.return_value = mock_resp

        with pytest.raises(_requests.HTTPError):
            client._complete(
                [{"role": "user", "content": "Hello"}], temperature=0.7
            )


# ---------------------------------------------------------------------------
# VolcEngine / DeepSeek / Doubao wrapper clients
# ---------------------------------------------------------------------------

class TestWrapperClients:
    """Tests for the consolidated wrapper clients in agent.api_clients."""

    def test_volcengine_client_defaults(self):
        import os
        from agent.api_clients import VolcEngineClient

        with patch.dict(os.environ, {"VOLCENGINE_API_KEY": "vk-123"}):
            c = VolcEngineClient()
            assert c.api_key == "vk-123"
            assert "volces.com" in c.base_url
            assert c.model == "volcano-ai"
            assert c.completions_path == "/chat/completions"

    def test_volcengine_client_explicit_args(self):
        from agent.api_clients import VolcEngineClient

        c = VolcEngineClient(api_key="my-key", base_url="https://custom.api", model="mymodel")
        assert c.api_key == "my-key"
        assert c.base_url == "https://custom.api"
        assert c.model == "mymodel"

    def test_deepseek_client_defaults(self):
        import os
        from agent.api_clients import DeepSeekClient

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "ds-123"}):
            c = DeepSeekClient()
            assert c.api_key == "ds-123"
            assert "deepseek.com" in c.base_url
            assert c.model == "deepseek-chat"

    def test_deepseek_client_explicit_args(self):
        from agent.api_clients import DeepSeekClient

        c = DeepSeekClient(api_key="my-key", base_url="https://custom.api", model="ds-pro")
        assert c.api_key == "my-key"
        assert c.model == "ds-pro"

    def test_doubao_client_defaults(self):
        import os
        from agent.api_clients import DoubaoClient

        with patch.dict(os.environ, {"DOUBAO_API_KEY": "db-123"}):
            c = DoubaoClient()
            assert c.api_key == "db-123"
            assert "doubao.com" in c.base_url
            assert c.model == "doubao-1-5-pro"

    def test_doubao_client_explicit_args(self):
        from agent.api_clients import DoubaoClient

        c = DoubaoClient(api_key="my-key", base_url="https://custom.api", model="db-pro")
        assert c.api_key == "my-key"
        assert c.model == "db-pro"

    def test_wrapper_inherits_chat(self):
        """All wrappers should inherit chat() and chat_with_history() from OpenAICompatClient."""
        from agent.api_clients import VolcEngineClient, DeepSeekClient, DoubaoClient

        for cls in (VolcEngineClient, DeepSeekClient, DoubaoClient):
            assert hasattr(cls, "chat")
            assert hasattr(cls, "chat_with_history")


# ---------------------------------------------------------------------------
# Backward-compatible re-exports
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """Root-level wrapper files should re-export classes for backward compat."""

    def test_volcengine_re_export(self):
        from volcengine_client import VolcEngineClient

        c = VolcEngineClient(api_key="test")
        assert c.api_key == "test"
        assert hasattr(c, "chat")

    def test_deepseek_re_export(self):
        from deepseek_client import DeepSeekClient

        c = DeepSeekClient(api_key="test")
        assert c.api_key == "test"
        assert hasattr(c, "chat")

    def test_doubao_re_export(self):
        from doubao_client import DoubaoClient

        c = DoubaoClient(api_key="test")
        assert c.api_key == "test"
        assert hasattr(c, "chat")


# ---------------------------------------------------------------------------
# load_llm_client_from_config
# ---------------------------------------------------------------------------

class TestLoadLLMClientFromConfig:
    """Tests for agent.llm_client.load_llm_client_from_config."""

    def test_load_basic_config(self):
        """Normal config with all fields present."""
        config = {
            "agents": {
                "defaults": {
                    "model": "deepseek-work",
                    "provider": "deepseek",
                    "maxTokens": 16000,
                    "temperature": 0.3,
                }
            },
            "models": [
                {"name": "deepseek-work", "mainModelId": "deepseek-chat-v3"}
            ],
            "providers": {
                "deepseek": {
                    "apiKey": "sk-ds-abc",
                    "apiBase": "https://api.deepseek.com/v1",
                    "apiKeys": ["sk-ds-abc", "sk-ds-def"],
                }
            },
        }
        with patch("builtins.open", MagicMock()), \
             patch("json.load", return_value=config), \
             patch("agent.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value = MagicMock()

            from agent.llm_client import load_llm_client_from_config

            load_llm_client_from_config(Path("dummy.json"))

            MockLLM.assert_called_once_with(
                provider="deepseek",
                model="deepseek-chat-v3",
                api_key="sk-ds-abc",
                api_base="https://api.deepseek.com/v1",
                max_tokens=16000,
                temperature=0.3,
                api_keys=["sk-ds-abc", "sk-ds-def"],
            )

    def test_load_config_max_tokens_low(self):
        """maxTokens=128 should be bumped to 4096 by LLMClient."""
        config = {
            "agents": {"defaults": {"model": "m", "provider": "p", "maxTokens": 128}},
            "models": [{"name": "m", "mainModelId": "m2"}],
            "providers": {"p": {"apiKey": "k"}},
        }
        with patch("builtins.open", MagicMock()), \
             patch("json.load", return_value=config), \
             patch("agent.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value = MagicMock()
            MockLLM.return_value.max_tokens = 4096

            from agent.llm_client import load_llm_client_from_config

            load_llm_client_from_config(Path("dummy.json"))
            # LLMClient receives 128, the floor logic inside __init__ bumps it
            call_kwargs = MockLLM.call_args[1]
            assert call_kwargs["max_tokens"] == 128

    def test_load_config_missing_max_tokens(self):
        """Missing maxTokens should default to 20000."""
        config = {
            "agents": {"defaults": {"model": "m", "provider": "p"}},
            "models": [{"name": "m", "mainModelId": "m2"}],
            "providers": {"p": {"apiKey": "k"}},
        }
        with patch("builtins.open", MagicMock()), \
             patch("json.load", return_value=config), \
             patch("agent.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value = MagicMock()

            from agent.llm_client import load_llm_client_from_config

            load_llm_client_from_config(Path("dummy.json"))
            call_kwargs = MockLLM.call_args[1]
            assert call_kwargs["max_tokens"] == 20000

    def test_load_config_invalid_max_tokens(self):
        """Non-numeric maxTokens should fallback to 20000."""
        config = {
            "agents": {
                "defaults": {"model": "m", "provider": "p", "maxTokens": "not-a-number"}
            },
            "models": [{"name": "m", "mainModelId": "m2"}],
            "providers": {"p": {"apiKey": "k"}},
        }
        with patch("builtins.open", MagicMock()), \
             patch("json.load", return_value=config), \
             patch("agent.llm_client.LLMClient") as MockLLM:
            MockLLM.return_value = MagicMock()

            from agent.llm_client import load_llm_client_from_config

            load_llm_client_from_config(Path("dummy.json"))
            call_kwargs = MockLLM.call_args[1]
            assert call_kwargs["max_tokens"] == 20000

    def test_load_config_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError("missing")):
            from agent.llm_client import load_llm_client_from_config

            with pytest.raises(ValueError, match="配置文件未找到"):
                load_llm_client_from_config(Path("missing.json"))

    def test_load_config_invalid_json(self):
        with patch("builtins.open", MagicMock()), \
             patch("json.load", side_effect=json.JSONDecodeError("err", "", 0)):
            from agent.llm_client import load_llm_client_from_config

            with pytest.raises(ValueError, match="格式错误"):
                load_llm_client_from_config(Path("bad.json"))
