# Agent Team v2 生产级架构

> 架构重构完成于 2026-05-31，P0-P2共11项全部验证通过。

## 架构总览

Agent Team 是一个多模型、多子代理的智能协作系统，通过 dispatch 调度引擎实现任务并行执行、质量审查和自动修复的完整闭环。

## 核心组件

### 10 模型智能路由

| 模型 | 速度 | 用途 |
|------|------|------|
| gemma-e2b | 极快 | score 1 极轻量任务 |
| gemma-e4b | 快 | score 1 轻量任务 |
| step-3.5-flash | 快 | 轻量任务 |
| step-3.7-flash | 350tok/s | 子代理默认 / SWE-bench 74.4% |
| minimax-m2.7 | 中 | Agent Teams 原生 / Toolathon 46% |
| mistral-nemotron | 中 | HumanEval 92.68 / 质量检查 |
| qwen3-coder | 中 | 代码专用 / 200K 上下文 |
| llama-maverick | 快 | 1M 上下文 / 多模态 |
| mistral-large-3 | 慢 | 675B / 原生 function calling |
| glm-5.1 | 慢 | 754B / 长链推理 |

路由规则：score 1-5 由任务复杂度决定，auto_benchmark 按综合得分(成功率x0.7+速度x0.3)自动回写路由表。

### 7 个子代理

| 子代理 | 模型 | 职责 | 工具数 |
|--------|------|------|--------|
| 小黄门 | step-3.7-flash | 轻量只读查询 | 4 |
| 随堂 | step-3.7-flash | 阅读文档 | 6 |
| 探事 | step-3.7-flash | 查访搜索 | 11 |
| 典簿 | mistral-nemotron | 质量检查 | 3 |
| 内官监 | minimax-m2.7 | 工程执行 | 10 |
| 浏览器操作员 | step-3.7-flash | 网页操作(CDP) | 17 |
| lead | — | 主控调度 | — |

### 8 种编排模式

1. **串行** — 任务链式执行
2. **并行** — 多任务同时执行
3. **Handoff** — 代理间交接
4. **审批** — 人工审核节点
5. **重规划** — 动态调整执行计划
6. **迭代精炼** — 多轮优化直到达标
7. **看板** — 进度可视化管理
8. **LLM选agent** — 由模型动态选择最佳代理

### 工具体系 (50+)

- 21 内置工具（文件/Shell/Git/搜索等）
- 14 浏览器工具（CDP操作/截图/AI分析）
- 8 编排工具（dispatch/approval/handoff等）
- 3 会话工具（记忆/上下文/状态）
- 4 共享工具（知识库/文档/API）

## Dispatch 调度系统

dispatch_tools.py 从单文件(1371行)拆分为5文件包：

| 文件 | 行数 | 职责 |
|------|------|------|
| parallel.py | 1136 | SubagentDispatcher核心 + 并行派遣 + 进度跟踪 |
| approval.py | 177 | 审批流程 + 共享上下文 + KB查询 |
| handoff.py | 22 | 代理交接 |
| refine.py | 76 | 迭代精炼 + 仪表盘 |
| __init__.py | 110 | 包导出 |

入口文件 dispatch_tools.py(80行) 保持向后兼容，re-export 所有公共符号。

## 容错与高可用

### API Key 轮转
- 2 账号 x 3 Key = 6 Key 池
- 独立限流 + 429 自动切换 + Retry-After 遵守
- 5xx 错误自动标记 Key 不可用

### 超时保护
- LLM 调用: asyncio.wait_for(60s)
- dispatch 执行: asyncio.wait_for(300s)

### 模型 Fallback
- 502 错误时: step-3.7 -> nemotron -> minimax 自动切换
- 浏览器 AI: chat_engine + CDP 双层 fallback

### 健康状态持久化
- .team/health.json 自动读写
- 模型成功率/速度实时追踪

## 架构重构记录 (2026-05-31)

### P0 — 立即修复 (3/3)
1. auto_benchmark 结果回写路由表
2. ContextAssembler 模板缓存(mtime校验)
3. score_complexity 去 async(纯CPU同步化)

### P1 — 短期优化 (5/5)
4. browser_status 重复定义清理
5. 健康状态持久化(.team/health.json)
6. dispatch_tools.py 拆分为5文件包
7. memory/versions 清理(保留最新10个快照)
8. loop.py __all__ 工具注册白名单

## 关键文件索引

| 文件 | 用途 |
|------|------|
| agent/tools/dispatch_tools.py | 向后兼容入口(80行) |
| agent/tools/dispatch/parallel.py | 并行派遣核心(1136行) |
| agent/model_orchestrator.py | 10模型路由+健康持久化 |
| agent/context.py | 模板缓存+SOUL.md缓存 |
| agent/memory.py | 三层记忆+版本快照清理 |
| agent/loop.py | __all__注册+compress_context |

## 相关文档

- [[Agent Team 浏览器AI 整合方案]] — 浏览器AI作为标准工具资源池的整合方案
- [[minimax-m27]] — Agent Teams原生模型详情
