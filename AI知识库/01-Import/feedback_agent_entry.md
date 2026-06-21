---
name: agent-team-entry-preference
description: 启动 Agent Team 时优先使用 agent_stream.py（AgentBridge 常驻桥接）
metadata: 
  node_type: memory
  type: feedback
  originSessionId: eff738a4-7090-4b1c-9374-545d3be33be3
---

启动 Agent Team 时，优先使用 `agent_stream.py` 中的 `AgentBridge` 类。

**Why:** 用户明确指定，AgentBridge 提供线程安全的常驻桥接和 SSE 流式通信，适合作为默认入口。

**How to apply:** 当用户要求"打开 Agent Team"或启动 Agent 服务时，从 `agent_stream.py` 入口启动，而非 `agent_api.py` 或 `agent_cli.py`。
