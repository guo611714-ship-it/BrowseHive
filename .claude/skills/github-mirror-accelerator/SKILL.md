---
name: GitHub 镜像加速器
description: 配置 Git 使用镜像加速 GitHub 下载，特别适用于中国区用户和 WSL 环境
version: 2.0.0
tags: [git, github, accelerate, mirror, speed, cdn, proxy, china, download, clone, health-check]
---

# GitHub 镜像加速器 Skill

**改善内容（v2.0）**: 新增镜像健康检查机制、镜像列表外部化、自动故障转移、配置加密支持。

## Skill 职责

自动配置 Git 的 URL 重写规则，使用国内镜像加速 GitHub 下载。支持多镜像站自动健康检查、故障转移和定期刷新。

## 配置外部化

镜像列表存储于 `~/.config/gh-mirror/mirrors.json`：

```json
{
  "mirrors": [
    {
      "id": "ghproxy-cdn",
      "base_url": "https://cdn.gh-proxy.org/https://github.com/",
      "priority": 1,
      "region": "global",
      "health_status": "healthy",
      "last_check": "2025-05-24T10:00:00Z",
      "avg_latency_ms": 120
    },
    {
      "id": "ghproxy-net",
      "base_url": "https://ghproxy.net/https://github.com/",
      "priority": 2,
      "region": "global",
      "health_status": "healthy",
      "last_check": "2025-05-24T10:00:00Z",
      "avg_latency_ms": 250
    },
    {
      "id": "mirrors-cloudflare",
      "base_url": "https://mirror.ghproxy.com/https://github.com/",
      "priority": 3,
      "region": "global",
      "health_status": "degraded",
      "last_check": "2025-05-24T09:30:00Z",
      "avg_latency_ms": 450
    },
    {
      "id": "npmmirror",
      "base_url": "https://github.com.cnpmjs.org/https://github.com/",
      "priority": 4,
      "region": "cn",
      "health_status": "healthy",
      "last_check": "2025-05-24T10:00:00Z",
      "avg_latency_ms": 80
    }
  ],
  "health_check": {
    "interval_hours": 6,
    "timeout_seconds": 5,
    "unhealthy_threshold_ms": 2000,
    "test_endpoints": [
      "https://github.com/git/git",
      "https://github.com/octocat/Hello-World"
    ]
  },
  "fallback": {
    "enabled": true,
    "strategy": "round-robin",
    "max_failures_before_skip": 3
  }
}
```

## 健康检查机制

### 定时任务（TaskFlow）

```bash
# 每 6 小时自动检查镜像健康
/loop 6h /github-mirror-accelerator --health-check-only

# 或创建持久化 TaskFlow
/taskflow create gh-mirror-health "0 */6 * * * /github-mirror-accelerator --health"
```

### 健康检查逻辑

```python
#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime, timedelta

MIRRORS_CFG = Path.home() / ".config" / "gh-mirror" / "mirrors.json"

def check_mirror_health(mirror_url: str, timeout: int = 5) -> dict:
    """测试单个镜像站延迟和可达性
    
    使用 HEAD 请求而非完整下载，减少测试开销。
    """
    test_url = mirror_url.rstrip('/') + "/git/git"
    result = {
        "url": mirror_url,
        "status_code": None,
        "latency_ms": None,
        "ok": False,
        "error": None
    }
    
    try:
        start = time.perf_counter()
        resp = requests.head(test_url, timeout=timeout, allow_redirects=True)
        elapsed = (time.perf_counter() - start) * 1000
        
        result.update({
            "status_code": resp.status_code,
            "latency_ms": round(elapsed, 1),
            "ok": resp.status_code < 400
        })
    except requests.Timeout:
        result["error"] = "timeout"
    except requests.RequestException as e:
        result["error"] = str(e)
    
    return result

def update_mirror_status(results: list[dict]):
    """更新所有镜像站健康状态"""
    with open(MIRRORS_CFG) as f:
        cfg = json.load(f)
    
    for res in results:
        for mirror in cfg["mirrors"]:
            if mirror["base_url"] == res["url"]:
                mirror["health_status"] = "healthy" if res["ok"] else "unhealthy"
                mirror["last_check"] = datetime.utcnow().isoformat() + "Z"
                mirror["avg_latency_ms"] = res["latency_ms"]
    
    with open(MIRRORS_CFG, "w") as f:
        json.dump(cfg, f, indent=2)
```

## 触发场景

当用户遇到以下情况时自动触发：
- `git clone` 速度极慢（KB/s 级别，持续 > 5s）
- `git fetch` 频繁超时或失败
- 终端输出包含 "Failed to connect to github.com" 或 "Connection timed out"
- WSL 或 Linux 环境 RTT > 200ms
- 在中国大陆 traceroute 显示国际出口拥塞

### 自动检测脚本

```bash
# 检测是否需要加速（用户可手动运行）
detect_slow_github() {
  local start=$(date +%s%3N)
  git ls-remote https://github.com/git/git.git &>/dev/null
  local duration=$(( $(date +%s%3N) - start ))
  
  if [ $duration -gt 5000 ]; then
    echo "⚠️  Git 操作耗时 ${duration}ms，建议启用镜像加速"
    echo "运行: /github-mirror-accelerator --auto"
    return 1
  fi
  return 0
}
```

## 执行步骤

### 1. 检测当前配置

```bash
git config --global --get-all url."https://github.com/".insteadOf
```

输出示例：
```
https://cdn.gh-proxy.org/https://github.com/
```

### 2. 列出可用镜像（按速度和优先级排序）

```bash
/github-mirror-accelerator --list-mirrors
```

输出示例：
```
=== 镜像站状态 ===

ID               Prio   Latency   Status   URL
─────────────────────────────────────────────────────────────
ghproxy-cdn      1      120ms     ✅       https://cdn.gh-proxy.org/...
npmmirror        4      80ms      ✅       https://github.com.cnpmjs.org/...
ghproxy-net      2      250ms     ✅       https://ghproxy.net/...
mirrors-cloudflare 3    450ms     ⚠️       https://mirror.ghproxy.com/...
```

### 3. 自动测试并配置最快的镜像

```bash
/github-mirror-accelerator --auto
```

执行流程：
1. 读取 `mirrors.json` 中的镜像列表
2. 并行测试每个镜像的 HEAD 请求延迟（限时 5s）
3. 过滤掉状态为 `unhealthy` 或延迟 > 2000ms 的镜像
4. 按 `priority × latency_ms` 综合评分排序
5. 选择得分最佳的镜像更新 Git 配置

```bash
# 实际执行的命令示例
git config --global url."https://cdn.gh-proxy.org/https://github.com/".insteadOf "https://github.com/"
git config --global url."https://github.com/".pushInsteadOf "git@github.com:"
```

### 4. 验证配置

```bash
# 查看当前配置
git config --global --get url."https://github.com/".insteadOf
# 输出: https://cdn.gh-proxy.org/https://github.com/

# 测试克隆速度
time git clone --depth 1 https://github.com/octocat/Hello-World.git /tmp/test-clone
```

### 5. 故障转移（如果选择的镜像失效）

```bash
# 手动切换到下一个最佳镜像
/github-mirror-accelerator --fallback

# 或自动检测并切换
#（通过 pre-push hook 自动检测速度并重新配置）
```

## 使用示例

### 自动配置（推荐）

```
/github-mirror-accelerator --auto
```

输出：
```
检测到 4 个镜像站:
  [1] cdn.gh-proxy.org    120ms ✅
  [2] npmmirror           80ms  ✅
  [3] ghproxy-net         250ms ✅
  [4] mirror.ghproxy.com  450ms ⚠️

选择最快镜像: npmmirror (80ms)

执行:
  git config --global url."https://github.com.cnpmjs.org/https://github.com/".insteadOf "https://github.com/"

✓ 配置成功！
```

### 仅执行健康检查

```
/github-mirror-accelerator --health
```

输出：
```
健康检查完成 (2025-05-24 10:00 UTC):
  ✅ ghproxy-cdn     120ms
  ✅ npmmirror        80ms
  ✅ ghproxy-net     250ms
  ❌ mirrors-cloudflare 超时
```

### 手动指定镜像

```
/github-mirror-accelerator --mirror cdn.gh-proxy.org
```

### 查看当前配置

```
/github-mirror-accelerator --status
```

输出：
```
当前镜像: npmmirror (github.com.cnpmjs.org)
配置时间: 2025-05-24 09:15:32 UTC
健康状态: ✅ healthy (上次检查: 10 分钟前)
延迟: 80ms (5 分钟平均值)
```

## 取消加速

恢复直连（移除所有 mirror 配置）：

```bash
/github-mirror-accelerator --disable
# 或手动:
git config --global --unset-all url."https://github.com/".insteadOf
```

## 技术细节

### Git Push 配置

镜像加速默认仅影响 `https://github.com/` 的读取（clone/fetch）。推送（push）仍使用 SSH 或原始 URL：

```bash
# 可选：如果推送也慢，可配置 pushInsteadOf
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

### 多 Git 服务支持

通过 `--service` 参数支持其他服务：

```bash
/github-mirror-accelerator --service gitlab --mirror ${GITLAB_MIRROR}
```

当前支持：`github`, `gitlab`, `bitbucket`（后者暂未实现）

### 预提交钩子（可选安装）

自动检测克隆速度并在过慢时提醒：

```bash
# .git/hooks/pre-push
#!/bin/bash
detect_slow_github || /github-mirror-accelerator --auto >&2
```

## 注意事项

- **镜像稳定性**: 镜像站可能随时变更或停止服务。配置了健康检查后可自动排除故障节点。
- **隐私**: 所有流量经镜像站中转，请确认信任该镜像运营商。
- **私有仓库**: 私有仓库通过镜像访问可能存在安全隐患，建议配置 SSH 直连。
- **时效性**: GitHub 更新发布后，镜像可能有 1-60 分钟的延迟（取决于镜像同步策略）。
- **Rate Limit**: 镜像站本身有请求频率限制，避免高频健康检查（建议 ≥ 6h 一次）。

## 故障排除

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| 所有镜像都慢 | 本地网络问题 | 检查 DNS，尝试 `8.8.8.8` |
| 单个镜像失效 | 镜像站宕机 | 运行 `--health` 确认，然后 `--auto` 重选 |
| HTTPS 证书错误 | MITM 或代理干扰 | 检查系统代理设置，禁用 SSL 验证（不推荐） |
| 私有仓库无法推送 | 镜像不支持 push | 配置 SSH 免密登录：`git config --global url."git@github.com:".insteadOf "https://github.com/"` |
| 健康检查Timeout | 防火墙阻断 HEAD 请求 | 改用 GET 请求测试（修改 `check_mirror_health`） |

## 扩展点

- **新镜像添加**: 向 `mirrors.json` 添加条目并提交 PR 到技能仓库
- **自定义健康检查端点**: 使用 `config.health_check.test_endpoints` 配置
- **区域感知**: 使用 `--region cn` 优先选择国内镜像
- **代理集成**: 配合 `clash-for-windows` 或 `v2ray` 使用 `--system-proxy`
