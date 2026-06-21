---
name: agent-team-launcher
description: 启动 Agent Team — SSE 桥接（常驻内存）+ CLI 直调
triggers:
  - keyword: "启动 agent"
  - keyword: "启动 team"
  - keyword: "启动团队"
  - keyword: "启动智能体"
  - keyword: "launch agent"
  - keyword: "start team"
  - keyword: "agent team"
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

## 团队配置

- 6 人：lead, coder, researcher, reviewer, reader, xiaohuangmen
- LLM：nvidia/minimax-m2.7
- 模式：ask_before_edit

## 故障排查

- 依赖缺失：`pip install -r requirements.txt`
- API Key：`model_config.json`（NVIDIA）
- Python 3.9+
