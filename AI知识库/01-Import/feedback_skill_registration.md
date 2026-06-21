---
name: skill-registration-rule
description: 安装skill后必须注册到skills-index.json，否则命令不可用
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7194df5c-9a78-4cbb-a2a2-939de8925a0e
---

安装任何 skill 后，必须将其注册到 `.claude/skills-index.json`，否则 `/命令` 无法使用。

**Why:** skills-index.json 是 Claude Code 加载 skill 的唯一入口。只创建 `.claude/skills/xxx.md` 文件但不注册，命令不会被识别。之前 learn、kb-import、kb-search、kb-browse 四个 skill 都因此无法使用。

**How to apply:**
1. 创建 skill 文件 `.claude/skills/xxx.md`
2. 读取 `.claude/skills-index.json`
3. 添加条目：`{"name": "xxx", "description": "...", "tags": [...], "capabilities": [], "entrypoint": "", "source": ".claude/skills/xxx.md"}`
4. 写回 skills-index.json
5. 提示用户重启会话生效
