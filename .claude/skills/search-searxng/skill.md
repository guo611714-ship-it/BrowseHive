---
name: search-searxng
description: "Search web via local searxng (Baidu/Bing/Sogou/Google)."
user_invocable: true
---

# SearXNG Web Search

Search Chinese web via local Docker searxng at `http://localhost:8889`.

## Search

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lenovo\.claude\scripts\searxng-search.ps1" -Query "QUERY" -Language "zh-CN" -Categories "general"
```

## Search Strategy

| 场景 | 工具 |
|------|------|
| 中文问题/国内资源 | searxng (Baidu/Bing/Sogou, zh-CN) |
| 英文问题/国外资源 | searxng (Google/Bing, en-US) |
| 技术文档/StackOverflow | searxng (Google/Bing, en-US) |

## Parameters

| Parameter | Default | Options |
|-----------|---------|---------|
| Query | (required) | any search term |
| Language | zh-CN | zh-CN, en-US, etc. |
| Categories | general | general, images, news, science, it |

## Rules

1. 中文用 zh-CN，英文用 en-US 作为 Language 参数
2. 结果简洁展示：标题、URL、摘要

> **注意**: 脚本路径依赖 Windows PowerShell，仅在 Windows 环境可用。
