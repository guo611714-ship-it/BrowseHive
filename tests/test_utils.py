"""agent/utils.py 测试"""

import pytest
from agent.utils import (
    _ok, _err, _warn, _parse_retry_after, _error_response,
    short_hash, load_json_file,
)


class TestOk:
    def test_basic(self):
        result = _ok("data")
        assert result["code"] == 200
        assert result["msg"] == "success"
        assert result["data"] == "data"

    def test_custom_msg(self):
        result = _ok("data", msg="custom")
        assert result["msg"] == "custom"

    def test_none_data(self):
        result = _ok()
        assert result["data"] == {} or result["data"] is None  # Both acceptable


class TestErr:
    def test_basic(self):
        result = _err(404, "not found")
        assert result["code"] == 404
        assert result["msg"] == "not found"


class TestWarn:
    def test_basic(self):
        result = _warn("warning message")
        assert result["msg"] == "warning message"


class TestParseRetryAfter:
    def test_valid_header(self):
        assert _parse_retry_after({"retry-after": "30"}) == 30.0

    def test_missing_header(self):
        assert _parse_retry_after({}) == 30.0

    def test_invalid_header(self):
        assert _parse_retry_after({"retry-after": "abc"}) == 30.0

    def test_custom_default(self):
        assert _parse_retry_after({}, default=60.0) == 60.0


class TestErrorResponse:
    def test_basic(self):
        result = _error_response("error occurred")
        assert result["content"] == "error occurred"
        assert result["status_code"] == -1

    def test_custom_status(self):
        result = _error_response("error", status_code=500)
        assert result["status_code"] == 500


class TestShortHash:
    def test_deterministic(self):
        h1 = short_hash("hello world")
        h2 = short_hash("hello world")
        assert h1 == h2

    def test_length(self):
        h = short_hash("test")
        assert len(h) == 8

    def test_different_inputs(self):
        assert short_hash("abc") != short_hash("xyz")


class TestLoadJsonFile:
    def test_nonexistent_file(self, tmp_path):
        result = load_json_file(tmp_path / "nonexistent.json")
        assert result == {}

    def test_valid_json(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}')
        result = load_json_file(f)
        assert result == {"key": "value"}

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json")
        result = load_json_file(f)
        assert result == {}

    def test_custom_default(self, tmp_path):
        result = load_json_file(tmp_path / "nonexistent.json", default=[])
        assert result == []
