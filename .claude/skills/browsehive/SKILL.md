---
name: browsehive
description: "BrowseHive浏览器AI工作流：通过browser-harness操控Chrome，与豆包/DeepSeek/欧亿AI/火山引擎协作。触发词：bh、hive、联网、打开AI平台"
---

# BrowseHive

通过 browser-harness 操控 Chrome CDP，与多 AI 平台协作。支持配置验证、健康检查和错误恢复。

## 触发

用户说 `bh`、`hive`、`联网`、`打开AI平台`、`打开AI工作流` 时启用。

## 配置外部化

平台配置应存储在 `~/.config/browsehive/platforms.json`：

```json
{
  "platforms": {
    "doubao": {
      "url": "https://www.doubao.com/",
      "selectors": {
        "input": "textarea[placeholder*='发送']",
        "submit": "button[type='submit']",
        "response": "[data-message-id]:last-child .content"
      },
      "max_retries": 3
    },
    "deepseek": {
      "url": "https://chat.deepseek.com/",
      "selectors": {
        "input": "textarea",
        "response": ".message-content:last-child"
      },
      "max_retries": 3
    },
    "ouyi": {
      "url": "https://ai.rcouyi.com/home",
      "selectors": {
        "input": ".chat-input",
        "response": ".assistant-message:last-child"
      },
      "max_retries": 2
    },
    "volcengine": {
      "url": "https://exp.volcengine.com/ark",
      "selectors": {
        "input": "textarea",
        "response": ".result:last-child"
      },
      "max_retries": 3
    }
  },
  "timeout": 30,
  "health_check_interval": 300
}
```

### URL 验证

启动时验证所有平台的 URL 格式：
```python
import re
from urllib.parse import urlparse

def validate_url(url: str) -> bool:
    """验证 URL 格式是否有效"""
    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except Exception:
        return False
```

## 工作流

### 1. 检查现有标签页

```bash
echo 'print(list_tabs())' | browser-harness 2>&1 | jq -r '.[]?.url' |
while read -r url; do
  echo "Found tab: $url"
done
```

### 2. 打开缺失的平台

```bash
# 通过 Python 助手
python -m bh_helper open --platform deepseek

# 或直接使用 browser-harness
echo 'new_tab("https://chat.deepseek.com/")' | browser-harness
```

### 3. 发送消息

完整实现示例（[`bh_helper.py`](bh_helper.py)）：

```python
#!/usr/bin/env python3
"""BrowseHive 助手工具"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "browsehive" / "platforms.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def send_message(msg: str, platform: str):
    """发送消息到指定 AI 平台"""
    config = load_config()
    platform_cfg = config["platforms"][platform]
    
    # 验证平台配置
    if not validate_url(platform_cfg["url"]):
        raise ValueError(f"Invalid URL for platform {platform}: {platform_cfg['url']}")
    
    # 查找或打开标签页
    url = platform_cfg["url"]
    # ... 实际实现调用 browser-harness ...
    
def main():
    if sys.argv[1] == "send":
        send_message(sys.argv[2], sys.argv[3])

if __name__ == "__main__":
    main()
```

**关键点：**
- 使用 `type_text()` 发送中文，避免 `js()` 的 surrogate 编码问题
- 每个平台配置独立的选择器和重试次数
- 支持 `--timeout` 参数覆盖默认超时

### 4. 读取响应

```python
def read_response(
    platform: str,
    timeout: int = None,
    poll_interval: float = 1.0
) -> str:
    """轮询读取响应，支持超时控制"""
    config = load_config()
    timeout = timeout or config.get("timeout", 30)
    
    start = time.time()
    last_response_len = 0
    
    while time.time() - start < timeout:
        response = extract_response(platform)
        
        # 检测响应是否已完成（长度不再增长）
        if response and len(response) == last_response_len:
            if not any(word in response.lower() for word in ["thinking", "thinking..."]):
                return response
        last_response_len = len(response or "")
        
        time.sleep(poll_interval)
    
    raise TimeoutError(f"No complete response from {platform} in {timeout}s")
```

## 平台列表

| 平台 | URL | 状态 | 描述 |
|------|-----|------|------|
| 豆包 | `https://www.doubao.com/` | ✅ 稳定 | 字节跳动中文对话模型 |
| DeepSeek | `https://chat.deepseek.com/` | ✅ 稳定 | 深度求索推理模型 |
| 欧亿AI | `https://ai.rcouyi.com/home` | ⚠️ 测试 | 多平台聚合（需验证可用性） |
| 火山引擎 | `https://exp.volcengine.com/ark` | ✅ 稳定 | 字节火山方舟平台 |

## 健康检查

定期运行健康检查（后台任务）：

```python
def health_check():
    """验证所有平台可达性"""
    config = load_config()
    results = {}
    
    for name, pconfig in config["platforms"].items():
        try:
            # 轻量级 HEAD 请求验证
            resp = requests.head(pconfig["url"], timeout=5)
            results[name] = {
                "url": pconfig["url"],
                "status_code": resp.status_code,
                "ok": resp.status_code < 400
            }
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}
    
    return results
```

调度：`loop 5m python -m bh_helper health`（使用 TaskFlow）

## 环境要求

- Chrome 需勾选 `chrome://inspect/#remote-debugging` 的 **"Allow remote debugging"**
- CDP 连接后自动最小化 Chrome 窗口（`minimize_on_ready` 配置）
- `PYTHONIOENCODING=utf-8` 必须设置（避免中文乱码）
- 预装 `jq` 用于 JSON 解析

## 错误处理

| 错误类型 | 处理策略 |
|---------|---------|
| CDP 连接失败 | 重试 3 次，降级到 Playwright MCP |
| 平台 URL 失效 | 记录日志，从配置中移除（标记 disabled） |
| 响应超时 | 根据 `max_retries` 决定是否重试整个对话 |
| Surrogate 编码错误 | 切换为 `type_text()`（默认行为） |
| 选择器失效 | 记录错误，建议用户更新配置文件 |

## 性能优化

- **并发处理**: 同时向 2-3 个平台发送相同请求，比较响应质量
- **标签页复用**: 保持平台标签页常开，避免重复启动成本
- **响应缓存**: 相同问题缓存 5 分钟（LRU 缓存，maxsize=100）

## 扩展新平台

1. 在 `platforms.json` 添加新平台条目
2. 验证并测试选择器（使用 browser-harness 的 `screenshot()`）
3. 更新 `health_check()` 逻辑（如有特殊需求）
4. 文档化平台特性（速率限制、认证方式等）

## 调试

```bash
# 查看当前浏览器状态
echo 'print(list_tabs())' | browser-harness | jq .

# 截图调试
echo 'screenshot("/tmp/tab.png")' | browser-harness

# 手动输入测试
echo 'type_text(0, "Hello")' | browser-harness
echo 'press_key(0, "Enter")' | browser-harness
```

## 取消加速

N/A（此技能不修改系统配置）

## 技术细节

- 优先使用 browser-harness CDP 直接连接（比 Playwright MCP 快 3-5x）
- `type_text()` 而非 `js()` 避免 Windows 下 surrogate pair 编码错误
- 配置文件支持热重载（检测 mtime 变化）
- 所有 I/O 操作必须设置超时，防止阻塞

## 注意事项

- **镜像站可选性**: BrowseHive 不依赖镜像，直接访问目标站点
- **隐私**: 消息通过浏览器界面传输，不经过第三方中转
- **认证**: 如果平台需要登录，需预先在浏览器中完成
- **并发限制**: 避免同时发起太多请求触发反爬（默认 max 3 platforms）
