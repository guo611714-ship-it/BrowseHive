# BrowseHive MCP 工作流调用指南

## 快速开始

### 方式 1: 通过 Meta MCP Server（推荐）

Meta MCP Server 将所有工作流封装成统一入口，通过 `.mcp.json` 自动管理子 MCP 生命周期。

**配置已就绪**:
```json
{
  "mcpServers": {
    "browsehive-meta": {
      "command": "python",
      "args": ["MCP/scripts/meta-mcp-server.py"],
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

**Claude Code 自动连接后，直接使用自然语言**:

- "用 DeepSeek 分析这个文件" → 调用 `ask` 工具
- "处理这个 PDF 并生成报告" → 调用 `process_pdf`
- "打开所有 AI 平台" → 调用 `open_all_platforms`
- "检查登录状态" → 调用 `check_login`
- "刷新会话" → 调用 `refresh_sessions`
- "保存快照" → 调用 `save_snapshot`

**工具列表**:
- `ask(message, platform="auto")` - AI 对话（auto/doubao/deepseek/volcengine/ouyi）
- `process_pdf(pdf_path, query)` - PDF 提取+分析
- `open_all_platforms()` - 批量打开平台
- `check_login()` - 检查登录状态
- `refresh_sessions(platforms="")` - 刷新会话
- `save_snapshot(path="")` / `restore_snapshot(path="")` - 快照管理

**资源查看**:
- `config://platforms` - 查看平台配置
- `status://servers` - 查看子 MCP 状态

---

### 方式 2: 通过 Unified Agent CLI

独立 CLI 工具，集成 Smart Skill Orchestrator + BrowseHive。

**启动**:
```bash
# 列出所有可用技能（255+）
python .agents/skills/browsehive/unified_agent_cli.py --list

# 智能路由自动选择技能
python .agents/skills/browsehive/unified_agent_cli.py "分析股票代码AAPL"

# 强制使用 BrowseHive 浏览器工作流
python .agents/skills/browsehive/unified_agent_cli.py "打开豆包搜索最新AI资讯" --browsehive

# 指定特定技能
python .agents/skills/browsehive/unified_agent_cli.py "画一只猫" --skill ai-image-generation

# 详细输出
python .agents/skills/browsehive/unified_agent_cli.py "写一篇Python优化文章" --verbose --json
```

---

### 方式 3: 直接调用 BrowseHive Agent (Python API)

```python
import sys
sys.path.insert(0, 'MCP/scripts')
from browsehive_agent import BrowseHiveAgent

# 创建实例（自动启动）
agent = BrowseHiveAgent(auto_start=True)

# 单平台对话
result = await agent.chat("解释量子计算", platform="deepseek")

# 多平台协作
result = await agent.chat_multi("写一篇关于AI的文章", platforms=["doubao", "deepseek"])

# PDF 处理
result = await agent.process_pdf("document.pdf", query="提取关键信息")

# 获取统计
stats = agent.get_stats()
```

---

## 工作流内部架构

```
Claude Code / 用户请求
    ↓
BrowseHive Meta MCP (统一入口)
    ↓ MCP 协议 (stdio)
├─→ ai-chat MCP (智能路由、对话、PDF)
├─→ browser-use MCP (浏览器操作)
└─→ chrome-devtools MCP (CDP 连接)
    ↓
Chrome 浏览器（保持登录状态）
    ↓
豆包 / DeepSeek / 火山引擎 / 欧亿AI
```

---

## 关键文件位置

| 文件 | 用途 |
|------|------|
| `MCP/scripts/meta-mcp-server.py` | Meta MCP 服务器（统一入口） |
| `.mcp.json` | MCP 服务器配置（新增 browsehive-meta） |
| `.agents/skills/browsehive/browsehive_agent.py` | BrowseHive Python API |
| `.agents/skills/browsehive/unified_agent_cli.py` | 统一 CLI |
| `.agents/skills/smart-skill-orchestrator/orchestrate.py` | 智能路由（255+ 技能） |
| `MCP/scripts/ai-chat-mcp.py` | AI-Chat MCP（核心） |

---

## 故障排除

- **Meta MCP 无法启动**: 检查 Python 路径和 meta-mcp-server.py 是否存在
- **子 MCP 连接失败**: 确保 `.mcp.json` 中配置的 MCP 服务器已安装（browser-use, chrome-devtools, ai-chat）
- **Chrome 启动失败**: 检查是否已有 Chrome 在 9223 端口运行，或手动启动：`browser-harness daemon`
- **编码错误**: 所有脚本已设置 `PYTHONIOENCODING=utf-8`

---

## 性能优化

- **响应缓存**: ai-chat MCP 默认 5 分钟 TTL
- **请求合并**: 相同并发请求自动共享结果
- **自适应限流**: 基于错误率和响应时间动态调整
- **CDP 端口持久化**: `.cdp_port` 文件保存端口信息，避免重复检测

---

最后更新: 2026-05-25
