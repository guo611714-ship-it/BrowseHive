---
name: always-start-agent-team
description: 所有工作任务默认先启动 Agent Team
metadata: 
  node_type: memory
  type: feedback
  originSessionId: eff738a4-7090-4b1c-9374-545d3be33be3
---

所有工作任务默认先启动 Agent Team，无需用户每次都指定。

**Why:** 用户希望 Agent Team 作为默认工作模式，通过 `agent_stream.py` 的 AgentBridge 常驻桥接，实现持续协作。

**How to apply:** 收到任何需要执行的工作任务时，优先通过 `agent_stream.py` 启动 Agent Team，再分派任务给各角色（lead/coder/researcher/reviewer/reader）。
