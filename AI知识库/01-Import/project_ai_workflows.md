---
name: ai-workflows-overview
description: 本项目所有AI工作流的全景概述——Agent Team、AI-Chat MCP、AIRouter、浏览器自动化
metadata: 
  node_type: memory
  type: project
  originSessionId: 82245c34-79ab-470f-b47c-9ee243d1bf45
---

# AI 工作流全景概述

本项目包含 **三大 AI 工作流** 和 **若干辅助子系统**，形成完整的多模型、多智能体协作生态。

---

## 一、Agent Team（多智能体协作系统）

**入口**: `agent.py` → `agent/` 包

### 架构
- **主循环**: `agent/loop.py` — CLI 交互 + 工具调度
- **工具执行器**: `agent/runner.py` — 支持并发工具调用
- **LLM 抽象层**: `agent/llm_client.py` — 统一接口，支持 DeepSeek/Anthropic/OpenAI(NVIDIA)
- **模型编排器**: `agent/model_orchestrator.py` — 双模型路由（主模型复杂决策，次模型轻量任务）
- **三层记忆**: `agent/memory.py` — 工作记忆 + 情景记忆(每日.md) + 长期记忆(MEMORY.md)
- **上下文组装**: `agent/context.py` — System Prompt 动态构建

### 5 人 Team 配置
| 队友 | 角色 | 身份模板 | 工具权限 |
|------|------|---------|---------|
| lead | 领导 | identity.md | 全部 |
| coder | 工程师 | neiguan_yingzao | 文件+Shell |
| researcher | 研究员 | dongchang_tanshi | Web+搜索 |
| reviewer | 审查员 | shangbao_dianbu | 文件+Grep |
| reader | 阅读员 | sili_suitang | 文件+Web+技能 |

### 5 类子代理派遣
- `xiaohuangmen` — 轻量只读
- `sili_suitang` — 阅读文档
- `dongchang_tanshi` — 查访搜索
- `shangbao_dianbu` — 质量检查
- `neiguan_yingzao` — 工程执行

### 工具集 (`agent/tools/`)
- Shell: `run_command`
- 文件: `read_file`, `write_file`, `edit_file`, `glob`, `grep`
- Web: `web_fetch`
- 搜索: `search` (MCP)
- 技能: `load_skill`, `list_skills`
- 任务: `update_todos`（跨回合存活）
- 子代理: `dispatch_subagent`（并发派遣）
- 团队: `spawn`, `list`, `send`, `read`, `broadcast`

---

## 二、AI-Chat MCP（浏览器 AI 集成）

**入口**: `MCP/scripts/ai-chat-mcp.py`

### 4 大 AI 平台
| 平台 | 优势 | 接入方式 |
|------|------|---------|
| 豆包 (Doubao) | 中文最强、联网搜索、深度思考 | API + 浏览器 |
| DeepSeek | 推理/代码、开源免费 | API |
| 火山引擎 | 企业级、智能路由 | API |
| 欧亿AI | 绘图(DALL-E)、思维导图、写作 | 浏览器自动化 |

### MCP 工具
- `ask_doubao` / `ask_deepseek` / `ask_volcengine` / `ask_ouyi` — 单平台对话
- `smart_ask` — 智能路由（根据任务自动选平台）
- `batch_ask` — 多平台并行
- `open_all_platforms` — 批量打开浏览器

### 浏览器自动化层
- `MCP/scripts/browser_agent.py` — browser-harness / browser-use / Playwright 三级降级
- CDP 直连 Chrome，页面池复用，会话持久化

### 性能优化
- 响应缓存（TTL 5min, LRU）
- 请求合并（并发相同请求共享）
- 自适应限流（根据错误率/负载动态调整）
- 动态超时（基于 P90）

---

## 三、AIRouter（统一 API 路由器）

**文件**: `ai_router.py` + 各平台客户端

### 平台客户端
| 文件 | 平台 |
|------|------|
| `deepseek_client.py` | DeepSeek |
| `doubao_client.py` | 豆包 |
| `volcengine_client.py` | 火山引擎 |
| `anthropic_client.py` | Claude (Anthropic) |
| `ouyi_api.py` | 欧亿AI |

### 路由逻辑
- `AIRouter.chat(platform, message)` — 按平台名直接调用
- `get_available_platforms()` — 检测已配置 API Key 的平台
- 全局单例 `get_router()`

---

## 四、辅助子系统

### 知识增强
- `knowledge-enrichment/claude_enricher.py` — Claude 知识丰富化
- `knowledge-enrichment/searxng-integration/searxng_collector.py` — SearXNG 搜索采集

### 技能系统
- `skills/clawhub/` — 技能库搜寻
- `skills/summarize/` — 内容总结
- `skills/weather/` — 天气查询
- `skills/AT/` — Agent Team 工作流（原 agent-team-launcher，已合并）

### MCP 元服务器
- `MCP/scripts/meta-mcp-server.py` — MCP 服务器的服务器
- `MCP/scripts/meta_mcp_client.py` — 元 MCP 客户端
- `MCP/scripts/self-optimization-loop.py` — 自优化循环
- `MCP/scripts/mcp-test-optimize-loop.py` — MCP 测试优化循环

### Windows 服务部署
- `install_service.ps1` / `setup_service.ps1` — 服务安装
- `start_agent.bat` / `start_agent_team.bat` — 启动脚本

---

## 五、调度系统决策规则（重要）

项目有 **两套独立调度系统**，不可合并，需按场景选择：

### SubagentDispatcher — 即时派遣
- **调用：** `await dispatch_subagent(agent_type, task, ...)`
- **机制：** 直接函数调用，纯内存，同步返回结果
- **适用：** 短命任务、一次性查询、快速确认、探索性搜索、并行探测
- **特征：** 无状态、无磁盘 I/O、支持多轮工具调用
- **子代理类型：** xiaohuangmen(轻量只读)、sili_suitang(阅读文档)、dongchang_tanshi(查访搜索)、shangbao_dianbu(质量检查)、neiguan_yingzao(工程执行)

### TeamStore + MessageBus — 持久化协作
- **调用：** `spawn_teammate()` → `send_message()` → `read_inbox()`
- **机制：** 文件持久化（`.team/` 目录），消息队列
- **适用：** 长期队友、跨会话恢复、消息协作、检查点恢复、多 agent 会议
- **特征：** 有状态、支持 shutdown、游标追踪、重启可恢复

### 决策流程
```
需要结果立即可用？ → YES → SubagentDispatcher
需要跨会话持久？ → YES → TeamStore + MessageBus
需要多 agent 消息协作？ → YES → TeamStore + MessageBus
其他短任务 → SubagentDispatcher
```
**一句话：** 即时任务用 dispatcher，长期协作用 team。

---

## 六、数据流全景

```
用户输入
  ↓
[Agent Team 主循环] ←→ [LLMClient] ←→ DeepSeek / Anthropic / OpenAI
  ↓                                                    ↑
[工具调用] → [AIRouter] → 各平台 API 客户端 ──────────┘
  ↓
[AI-Chat MCP] → [browser_agent] → Chrome CDP → 豆包/欧亿/火山引擎
  ↓
[记忆系统] → 工作记忆 / 情景记忆 / 长期记忆
```

---

## 七、路径 C 进度（渐进式统一）

**目标：** 将 Agent Team 和 Browser AI 渐进式统一为一套系统

| 步骤 | 状态 | 内容 |
|------|------|------|
| 1. 工具集成 | ✅ 完成 | `agent/tools/browser_tools.py` 桥接 Browser AI 4 大平台 |
| 2. 共享层抽取 | ✅ 完成 | `shared/` 限流器 + 重试管理器，已集成到 llm_client.py |
| 3. 统一调度 | ⏳ 待做 | 合并 SubagentDispatcher 和 TeamStore 消息总线 |

**已创建的桥接工具：** ask_doubao, ask_deepseek_browser, ask_volcengine, ask_ouyi, smart_ask, browser_status

**已抽取的共享模块：** RateLimiter (shared/__init__.py), RetryManager (shared/retry.py)

---

## 八、已知限制

1. **浏览器依赖** — AI-Chat MCP 需要 Chrome 已登录目标平台
2. **双模型路由** — 主/次模型需在 `model_config.json` 中配置
3. **Windows 兼容** — PM2 不支持 Windows，使用启动文件夹/计划任务替代
