"""Web 抓取工具"""

import requests
from typing import Dict, Any


def web_fetch(url: str, method: str = "GET", headers: Dict[str, str] = None,
              data: str = None, timeout: int = 10) -> Dict[str, Any]:
    """
    抓取网页内容

    Args:
        url: 目标 URL
        method: HTTP 方法
        headers: 请求头
        data: 请求体（POST 用）
        timeout: 超时时间

    Returns:
        {"status": 200, "content": "...", "headers": {...}}
    """
    try:
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
