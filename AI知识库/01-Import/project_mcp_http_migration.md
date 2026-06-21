---
name: mcp-http-migration
description: 5个MCP从stdio迁移到Streamable HTTP，改造方案、踩坑经验、代码审查15个发现修复
metadata:
  type: project
---

## MCP Streamable HTTP 迁移（已完成）

### 迁移结果
| MCP | 语言 | 改造方式 | 端口 |
|-----|------|----------|------|
| ai-chat | Python | FastMCP 原生 HTTP | 8090 |
| codegraph | TypeScript | 源码 + HttpAdapter | 8091 |
| context7 | TypeScript | 原生 --transport http | 8092 |
| github | Go | 源码内置 HTTP，Go 1.26 编译 | 8093 |
| chrome-devtools | TypeScript | 源码改造 + stateless mode | 8094 |

### 关键经验
1. 代理桥接在 Windows 不可靠，应走原生改造
2. codegraph daemon 模式优先于 HTTP
3. chrome-devtools ClearcutLogger 单例，用 stateless 模式
4. github Go 依赖链需 Go 1.25+
5. Windows shell:true 必弹 CMD 窗口

### 代码审查修复（15个）
3 Critical + 4 High + 8 Medium/Low 全部修复

### 维护
- 统一启动器: MCP/start-all-mcp-http.js
- 计划任务: MCP-HTTP-All
- Codegraph PRAGMA: auto_vacuum=FULL
