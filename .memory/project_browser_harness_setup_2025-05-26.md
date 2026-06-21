---
name: project_browser_harness_setup_2025-05-26
description: Browser Harness 配置完成：安装、CDP 连接、测试全部通过
metadata:
  type: project
---

## 配置状态

**日期**: 2025-05-26  
**状态**: ✅ 完成

## 安装详情

- **安装方式**: 从 GitHub 克隆仓库 `~/Developer/browser-harness`，使用 `pip install -e .` 可编辑安装
- **版本**: 0.1.0 (git 版本)
- **路径**: `C:\Users\lenovo\Developer\browser-harness`
- **命令行工具**: `browser-harness` (在 PATH 中)

## 运行时配置

### Chrome CDP 连接 (Way 2 - 专用实例)

- **端口**: 9222
- **启动参数**:
  ```
  --remote-debugging-port=9222
  --user-data-dir=%TEMP%\browser-harness-cdp
  --remote-allow-origins=*
  --no-first-run
  --no-default-browser-check
  --disable-background-networking
  --disable-sync
  --disable-translate
  --disable-extensions
  ```
- **自动启动**: 配置脚本自动启动 Chrome 实例
- **PID**: 动态分配

### 环境变量

`.env` 文件（项目根目录）包含：
```bash
# Browser Harness CDP
BU_CDP_URL=http://127.0.0.1:9222
```

**作用**: 告诉 browser-harness daemon 连接到哪个 CDP 端点，避免自动连接到云浏览器。

### 当前状态

```bash
browser-harness --doctor
```

输出：
```
[ok  ] chrome running
[ok  ] daemon alive
[ok  ] active browser connections — 1
```

## 验证测试

✅ **基本连接**: `page_info()` 返回页面信息  
✅ **导航**: `new_tab(url)` 能打开网页  
✅ **截图**: `capture_screenshot()` 保存 PNG (135KB 成功)  
✅ **代码执行**: Python 子进程通信正常  

## BrowseHive 整合

当前 `browser_agent.py` 模块使用 **browser-harness 优先策略**：

1. 检测 `browser-harness --version`
2. 通过 `._detect_cdp_url()` 自动发现 CDP 端口（检查 .cdp_port 文件 + 扫描 9222-9225）
3. 设置 `BU_CDP_URL` 环境变量
4. 使用 `subprocess.run(['browser-harness'], input=code)` 执行

**已修复问题**:
- UTF-8 编码传输 (`.encode('utf-8')`)
- Windows 控制台 surrogate 处理 (`errors='replace'`)
- CDP port 持久化 (`MCP/scripts/.cdp_port`)

## 可选优化

### 1. Domain Skills (社区技能)
```bash
# 启用 per-site 技能
set BH_DOMAIN_SKILLS=1
# 添加到 .env
echo "BH_DOMAIN_SKILLS=1" >> .env
```
作用: 自动加载 `agent-workspace/domain-skills/<site>/` 中的站点特定脚本。

### 2. 云浏览器 (Browser Use Cloud)
```bash
export BROWSER_USE_API_KEY=your_api_key
# 可选: 自动启动云浏览器
export BU_AUTOSPAWN=1
```
获取 API Key: https://cloud.browser-use.com/new-api-key

### 3. Profile Sync (可选)
```bash
curl -fsSL https://browser-use.com/profile.sh | sh
```
用于同步本地 Chrome cookies 到云浏览器。

## 故障排除

### daemon 未启动
```bash
browser-harness --reload  # 重启 daemon
```

### 端口占用
检查占用：
```bash
netstat -ano | findstr :9222
```
杀死进程后重试配置脚本。

### Chrome 升级后需要重新授权
Chrome 144+ 每次 daemon 重启后首次连接会弹出 "Allow remote debugging?" 弹窗，需手动点 Allow。

## 相关文件

- **配置脚本**: `scripts/configure_browser_harness.py`
- **项目 .env**: `.env` (包含 BU_CDP_URL)
- **ai-chat MCP**: `MCP/scripts/ai-chat-mcp.py` (使用 BrowserAgent)
- **BrowseHive**: `.agents/skills\browsehive\config.json` (路由配置)
- **官方文档**: `~/Developer/browser-harness/install.md`, `SKILL.md`

## 使用示例

```bash
# 基础: 页面信息
browser-harness <<< "print(page_info())"

# 导航
browser-harness <<< "new_tab('https://example.com'); wait_for_load(); print(page_info())"

# 截图
browser-harness <<< "capture_screenshot('shot.png'); print('saved')"

# 点击坐标 (x, y)
browser-harness <<< "click_at_xy(100, 200); print('clicked')"

# 输入文字
browser-harness <<< "type_text('Hello World'); press_key('Enter'); print('typed')"

# 执行 JS
browser-harness <<< "result = js('return document.title'); print('title:', result)"
```

更多示例查看 `~/Developer/browser-harness/SKILL.md`。
