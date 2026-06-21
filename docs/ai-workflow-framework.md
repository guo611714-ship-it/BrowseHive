# AI Workflow System Framework

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户接入层                                    │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│ agent_cli.py │ agent_api.py │agent_stream.py│ agent_query.py       │
│   CLI入口     │  API入口     │ SSE桥接(默认) │   查询入口            │
└──────┬───────┴──────┬───────┴──────┬───────┴───────────┬───────────┘
       │              │              │                   │
       └──────────────┴──────┬───────┴───────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Agent Team 核心引擎                               │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│  loop.py     │  runner.py   │ context.py   │   memory.py          │
│  主循环       │  工具执行器   │ 上下文组装    │  三层记忆             │
├──────────────┴──────────────┼──────────────┴───────────────────────┤
│  model_orchestrator.py      │  team_store.py                       │
│  双模型路由                  │  状态持久化                           │
├─────────────┬───────────────┼──────────────┬───────────────────────┤
│ llm_client.py│tool_defs.py  │registry.py   │  subagents/           │
│ LLM抽象层    │ 工具注册      │ 子代理注册    │  子代理管理            │
└──────┬──────┴──────┬────────┴──────────────┴───────────┬───────────┘
       │             │                                    │
       ▼             ▼                                    ▼
┌──────────────┐ ┌──────────────┐              ┌─────────────────────┐
│   5人Team    │ │   工具集      │              │    子代理派遣         │
├──────────────┤ ├──────────────┤              ├─────────────────────┤
│ lead  (全部) │ │ Shell        │              │ xiaohuangmen (只读)  │
│ coder (文件) │ │ File         │              │ sili_suitang (阅读)  │
│ resrch(Web)  │ │ Web          │              │ dongchang_ (搜索)    │
│ review(Grep) │ │ Search       │              │ shangbao_ (质检)     │
│ reader(Web)  │ │ Skills       │              │ neiguan_ (工程)      │
│              │ │ Todo         │              └─────────────────────┘
│              │ │ Team         │
└──────────────┘ └──────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AIRouter 统一路由层                                │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│deepseek_     │doubao_       │volcengine_   │anthropic_  │ouyi_     │
│client.py     │client.py     │client.py     │client.py   │api.py    │
│ DeepSeek     │ 豆包          │ 火山引擎      │ Claude     │ 欧亿AI   │
└──────┬───────┴──────┬───────┴──────┬───────┴───────────┴───────────┘
       │              │              │
       ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AI-Chat MCP 浏览器集成层                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │chat_engine.py│  │config.py     │  │ monitor.py               │   │
│  │ChatEngine    │  │Config(热更新) │  │ 监控+限流                │   │
│  │缓存+请求合并  │  │              │  │                          │   │
│  └──────┬──────┘  └──────────────┘  └──────────────────────────┘   │
│         ▼                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │cache_manager│  │platforms.py  │  │ browser_agent.py         │   │
│  │LRU+TTL缓存  │  │平台定义       │  │ 三级降级:                 │   │
│  └─────────────┘  └──────────────┘  │ 1. browser-harness (CDP) │   │
│                                      │ 2. browser-use (AI)      │   │
│  ┌──────────────────────────────┐   │ 3. Playwright            │   │
│  │ MCP Tools:                   │   └────────────┬─────────────┘   │
│  │ ask_doubao / ask_deepseek    │                │                  │
│  │ ask_volcengine / ask_ouyi    │                ▼                  │
│  │ smart_ask / batch_ask        │   ┌──────────────────────────┐   │
│  │ open_all_platforms           │   │ Chrome CDP → 浏览器平台   │   │
│  └──────────────────────────────┘   └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    辅助子系统                                         │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│meta-mcp-     │self-         │mcp-test-     │ Windows Service       │
│server.py     │optimization  │optimize-loop │ install_service.ps1   │
│MCP元服务器    │-loop.py      │.py           │ start_agent.bat       │
└──────────────┴──────────────┴──────────────┴───────────────────────┘
```

## 2. Module Dependencies

```
agent_stream.py ──────┐
agent_api.py ─────────┤
agent_cli.py ─────────┼──→ agent/loop.py ──→ agent/llm_client.py
agent_query.py ───────┘         │                  │
                                │                  ▼
                                │         ┌────────────────┐
                                │         │  LLM Providers │
                                │         ├────────────────┤
                                │         │ NVIDIA API     │
                                │         │ DeepSeek API   │
                                │         │ Anthropic API  │
                                │         └────────────────┘
                                ▼
                       agent/runner.py
                                │
                   ┌────────────┼────────────┐
                   ▼            ▼            ▼
            agent/tools/  agent/memory.py  agent/team_store.py
                   │                         │
                   ▼                         ▼
            AIRouter ──────────────→ AI-Chat MCP Core
                   │                         │
                   ▼                         ▼
         platform clients          browser_agent.py
                                           │
                                           ▼
                                    Chrome CDP
```

## 3. Data Flow

```
用户输入
  │
  ▼
[Agent Team 主循环] ←──→ [LLMClient] ←──→ DeepSeek / Anthropic / NVIDIA
  │                                                    ▲
  │                                                    │
  ├──→ [工具调用] ──→ [AIRouter] ──→ 各平台 API ───────┘
  │
  ├──→ [AI-Chat MCP] ──→ [chat_engine] ──→ [cache_manager]
  │                         │
  │                         ▼
  │                   [browser_agent] ──→ Chrome CDP ──→ 豆包/欧亿/火山
  │
  └──→ [记忆系统]
         ├── 工作记忆（当前会话）
         ├── 情景记忆（每日.md文件）
         └── 长期记忆（MEMORY.md）
```

## 4. Deployment Architecture

```
┌─────────────────────────────────────────────────┐
│              Windows 11 本机                      │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │  Agent SSE Bridge (port 8771)            │   │
│  │  python agent_stream.py                  │   │
│  └──────────────┬──────────────────────────┘   │
│                 │                               │
│  ┌──────────────┴──────────────────────────┐   │
│  │  Claude Code (当前会话)                    │   │
│  │  - CodeGraph MCP Server                  │   │
│  │  - AI-Chat MCP Server                    │   │
│  │  - Chrome DevTools MCP                   │   │
│  └──────────────┬──────────────────────────┘   │
│                 │                               │
│  ┌──────────────┴──────────────────────────┐   │
│  │  Chrome Browser (已登录各平台)             │   │
│  │  - 豆包 Web UI                            │   │
│  │  - 欧亿 AI Web UI                         │   │
│  │  - 火山引擎 Web UI                         │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │  Cloud APIs                              │   │
│  │  - NVIDIA API (minimax-m2.7)             │   │
│  │  - DeepSeek API                          │   │
│  │  - Anthropic API (Claude)                │   │
│  │  - 豆包/火山 API                          │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  启动方式:                                      │
│  - start_agent.bat (手动)                       │
│  - install_service.ps1 (Windows 服务)           │
│  - 计划任务 (定时启动)                           │
└─────────────────────────────────────────────────┘
```

## 5. Tech Stack

| 层级 | 技术 | 用途 |
|------|------|------|
| **语言** | Python 3.11 | 全栈 |
| **LLM 接入** | NVIDIA API, DeepSeek API, Anthropic SDK | 多模型支持 |
| **浏览器自动化** | Chrome CDP, Playwright, browser-harness | 浏览器 AI 集成 |
| **通信** | SSE (Server-Sent Events) | 实时流式通信 |
| **MCP** | Model Context Protocol | Claude Code 工具集成 |
| **缓存** | 内存 LRU + TTL | 响应缓存优化 |
| **存储** | JSON 文件 + SQLite | 状态持久化 |
| **部署** | Windows 服务 / 计划任务 | 生产部署 |

## 6. Core Design Patterns

### 双模型路由 (Model Orchestrator)
```
用户请求 ──→ 复杂度评估
                │
        ┌───────┴───────┐
        ▼               ▼
   复杂任务          轻量任务
   主模型            次模型
   (Opus 4.7)       (minimax-m2.7)
```

### 三级降级 (Browser Agent)
```
请求 ──→ browser-harness (CDP直接控制)
           │ 失败
           ▼
         browser-use (AI驱动)
           │ 失败
           ▼
         Playwright (自动化框架)
```

### 请求合并 (Chat Engine)
```
相同请求 A ──┐
             ├──→ 合并为单次请求 ──→ 平台API ──→ 广播结果
相同请求 B ──┘
```

### 自适应限流 (Monitor)
```
错误率监控 ──→ 动态调整请求间隔
负载监控   ──→ 动态调整并发数
P90延迟    ──→ 动态调整超时时间
```

### 三层记忆 (Memory System)
```
工作记忆 (Working Memory)
  └─ 当前会话上下文，随对话推进动态裁剪

情景记忆 (Episodic Memory)
  └─ 按日期存储的 .md 文件，记录每日工作

长期记忆 (Long-term Memory)
  └─ MEMORY.md 索引 + 独立记忆文件
```

---

*Generated: 2026-05-29 | Source: AI Workflow System Codebase*
