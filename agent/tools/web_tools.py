"""Web 抓取工具"""

import re
import ipaddress
import requests
from typing import Dict, Any
from .tool_registry import tool

# SSRF 防护：内网地址黑名单
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
]
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "169.254.169.254"}


def _validate_url(url: str) -> str:
    """校验URL安全性，防止SSRF攻击"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    # 仅允许 http/https
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的协议: {parsed.scheme}，仅允许 http/https")
    hostname = parsed.hostname or ""
    # 检查黑名单主机
    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"禁止访问: {hostname}")
    # 检查内网IP
    try:
        ip = ipaddress.ip_address(hostname)
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                raise ValueError(f"禁止访问内网地址: {hostname}")
    except ValueError as e:
        if "禁止" in str(e):
            raise
        # hostname不是IP，继续检查
        pass
    return url


@tool("web_fetch", "抓取网页内容")
def web_fetch(url: str, method: str = "GET", headers: Dict[str, str] = None,
              data: str = None, timeout: int = 10) -> Dict[str, Any]:
    """
    抓取网页内容

    :param url: 目标 URL
    :param method: HTTP 方法
    :param headers: 请求头
    :param data: 请求体（POST 用）
    :param timeout: 超时时间
    """
    try:
        _validate_url(url)
        response = requests.request(
            method=method,
            url=url,
            headers=headers or {},
            data=data,
            timeout=timeout
        )

        # 限制内容大小
        content = response.text
        if len(content) > 100000:
            content = content[:100000] + "\n... (truncated)"

        return {
            "status": response.status_code,
            "content": content,
            "headers": dict(response.headers),
            "url": response.url
        }
    except requests.RequestException as e:
        return {"error": str(e)}
