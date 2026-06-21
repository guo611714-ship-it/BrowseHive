---
name: agent-team-launcher
description: "启动 Agent Team — SSE 桥接（常驻内存）+ CLI 直调"
triggers:
  - keyword: "启动 agent"
  - keyword: "启动 team"
  - keyword: "agent team"
  - keyword: "启动智能体"
  - keyword: "launch agent"
  - keyword: "start team"
---

# Agent Team 启动器

## 启动 SSE 桥接服务器

执行命令：`python agent_stream.py --port 8771`

SSE 桥接保持 AgentLoop 常驻内存，对话历史跨请求保持。

### 启动后可用端点

```
POST /chat     {"message":"..."}           → 同步聊天
GET  /stream?message=...                   → SSE 流式
GET  /status                               → 系统状态
GET  /history                              → 对话历史
POST /tool     {"tool":"run_command","args":{"command":"ls"}} → 工具直调
```

### Claude 交互方式

```bash
# 聊天（15-30秒）
curl -X POST http://127.0.0.1:8771/chat -H "Content-Type: application/json" -d '{"message":"你好"}'

# 工具直调（毫秒级）
curl -X POST http://127.0.0.1:8771/tool -H "Content-Type: application/json" -d '{"tool":"run_command","args":{"command":"ls"}}'
```

### CLI 备用（无服务器时）

```bash
python agent_cli.py ask "问题" --timeout 120
python agent_cli.py tool run_command '{"command":"ls"}'
python agent_cli.py status
```

## 团队配置（v2 架构 · 2026-06-01 最终版）

- **7个子代理**：小黄门(轻量只读) / 随堂(阅读文档) / 探事(查访搜索) / 典簿(质量检查) / 内官监(工程执行) / browser_agent(网页操作) / lead(主控)
- **10模型智能路由**：gemma-e2b/e4b, step-3.5/3.7-flash, minimax-m2.7, mistral-nemotron, qwen3-coder, llama-maverick, mistral-large-3, glm-5.1
- **8种编排模式**：串行/并行/Handoff/审批/重规划/迭代精炼/看板/LLM选agent
- **50+工具**：21内置+14浏览器+8编排+3会话+4共享
- **6API Key轮转**：2账号×3Key, 独立限流, 429自动切换

## 工程化状态（492测试 · 综合成熟度4.5/5）

### 测试覆盖
- **492测试全部通过**（29.87秒）
- **29个test文件**覆盖核心模块
- 测试/代码比 **0.65**（超过生产级0.5标准）
- 核心模块100%覆盖：loop/orchestrator/llm_client/parallel/memory

### 质量门禁
- **pre-commit hook**：pytest → mypy → ruff 三重检查，任一失败阻止提交
- **mypy strict**：类型检查（pyproject.toml已配置）
- **ruff lint**：E/F/W/I/B/C4/SIM规则（pyproject.toml已配置）

### 已修复的关键bug
- `_compress_sync` 死锁：`threading.Lock()` → `threading.RLock()`
- `AgentError` 参数名：`detail=` → `details=`
- API客户端重复：3个独立文件 → `api_clients.py` 统一继承
- pre-commit hook：`|| true`（形同虚设）→ pytest 真实卡点

### 新增模块（P2+）
- `agent/feedback.py` — 学习反馈环，模型路由优化
- `agent/orchestration.py` — 插件化编排（Serial/Parallel/Handoff）
- `agent/event_bus.py` — 全局事件总线，发布/订阅
- `agent/dynamic_semaphore.py` — 负载感知动态并发
- `agent/api_client.py` — 通用OpenAI兼容客户端
- `agent/api_clients.py` — 3平台统一wrapper

### 知识服务集成
- `agent/knowledge_service.py` — 统一知识服务：记忆读写 + 结构化KB搜索 + 任务上下文自动注入
- agent loop 自动集成：启动时读取相关记忆，结束时保存工作成果
- 知识服务失败不影响主流程（try/except降级）

## 故障排查

- 依赖缺失：`pip install -r requirements.txt`
- API Key：`model_config.json`（NVIDIA）
- Python 3.10+
- Chrome CDP：端口9222，需用curl+subprocess或websocket-client（Python httpx返回503）
- LLM超时：asyncio.wait_for(60s) 防止无限卡住
- dispatch超时：asyncio.wait_for(300s) 防止无限执行
- 测试运行：`python -m pytest tests/ -q --override-ini=addopts=`


## Parallel Fix (并行修复)

当任务涉及多个独立修改时，**不要逐个串行执行**。
调用 `submit_fix_manifest` 工具，由 ParallelFixEngine 并行执行：

```json
{
  "name": "submit_fix_manifest",
  "arguments": {
    "source": "stocktake",
    "data": {
      "skills": {
        "<skill_name>": {"verdict": "Improve", "reason": "<描述>", "path": "<文件路径>"}
      }
    },
    "strategy": "auto",
    "filter_actionable": true
  }
}
```

- 引擎自动处理分片、冲突预测、并行调度
- 等待返回结果后，检查 conflicts 列表
