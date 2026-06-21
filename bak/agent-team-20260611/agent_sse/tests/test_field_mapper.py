# agent_sse/tests/test_field_mapper.py
"""字段映射转换器测试"""

import pytest
from agent_sse.adapters.field_mapper import FieldMapper


def test_chat_request_mapping():
    """测试对话请求字段映射"""
    old_request = {"message": "hello", "user_id": "123"}
    new_request = FieldMapper.map_chat_request(old_request)
    assert new_request["prompt"] == "hello"
    assert new_request["session_id"] == "123"


def test_chat_request_missing_fields():
    """测试对话请求缺失字段"""
    old_request = {}
    new_request = FieldMapper.map_chat_request(old_request)
    assert new_request["prompt"] == ""
    assert new_request["session_id"] == ""


def test_chat_response_mapping():
    """测试对话响应字段映射"""
    hermes_response = {"response": "hi", "stop_reason": "stop"}
    old_response = FieldMapper.map_chat_response(hermes_response)
    assert old_response["content"] == "hi"
    assert old_response["finish_reason"] == "stop"


def test_chat_response_with_usage():
    """测试对话响应带用量信息"""
    hermes_response = {
        "response": "hi",
        "stop_reason": "stop",
        "usage": {"input_tokens": 10, "output_tokens": 20}
    }
    old_response = FieldMapper.map_chat_response(hermes_response)
    assert old_response["usage"]["input_tokens"] == 10


def test_tool_request_mapping():
    """测试工具调用请求字段映射"""
    old_request = {"tool": "read_file", "args": {"path": "/tmp"}}
    new_request = FieldMapper.map_tool_request(old_request)
    assert new_request["tool_name"] == "read_file"
    assert new_request["parameters"]["path"] == "/tmp"


def test_tool_response_mapping():
    """测试工具调用响应字段映射"""
    hermes_response = {"status": "success", "output": "content"}
    old_response = FieldMapper.map_tool_response(hermes_response)
    assert old_response["result"] == "content"
    assert old_response["code"] == 0


def test_tool_response_error():
    """测试工具调用错误响应"""
    hermes_response = {"status": "error", "error": {"message": "file not found"}}
    old_response = FieldMapper.map_tool_response(hermes_response)
    assert old_response["code"] == 1
    assert old_response["error"] == "file not found"


def test_sse_chunk_mapping():
    """测试 SSE 流式字段映射"""
    hermes_chunk = {"delta": "hello"}
    old_chunk = FieldMapper.map_sse_chunk(hermes_chunk)
    assert old_chunk["content"] == "hello"


def test_sse_chunk_with_tool_calls():
    """测试 SSE 流式带工具调用"""
    hermes_chunk = {
        "delta": "",
        "tool_calls": [{"id": "123", "name": "test", "arguments": {}}]
    }
    old_chunk = FieldMapper.map_sse_chunk(hermes_chunk)
    assert old_chunk["tool_calls"][0]["name"] == "test"


def test_sse_chunk_empty():
    """测试 SSE 流式空值"""
    hermes_chunk = {}
    old_chunk = FieldMapper.map_sse_chunk(hermes_chunk)
    assert old_chunk["content"] == ""


def test_sse_error_format():
    """测试 SSE 错误格式"""
    error_str = FieldMapper.map_sse_error("test error", 500)
    assert "test error" in error_str
    assert "500" in error_str
    assert error_str.startswith("data: ")
