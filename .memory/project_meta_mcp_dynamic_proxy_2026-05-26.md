---
name: meta-mcp-dynamic-proxy
description: Meta MCP 实现为动态工具代理，自动发现并注册子 MCP 工具
metadata:
  type: project

# Meta MCP 动态代理架构

## 变更概述

将 Meta MCP Server 从静态工具封装重构为**动态工具代理**，自动发现 ai-chat、browser-use、chrome-devtools 等子 MCP 的所有工具并实时注册。

## 核心改进

1. **动态发现机制**
   - `MetaManager.refresh_tool_map()` 扫描所有已启动的子 MCP 服务器
   - 构建 `tool_name -> server_name` 映射，自动处理命名冲突
   - 支持工具别名（添加 `server_name_toolname` 前缀避免重复）

2. **自动注册**
   - 在 `server_lifespan` 启动阶段调用 `register_dynamic_tools(server)`
   - 使用 FastMCP 的 `Tool` API 为每个发现的工具创建包装器
   - 包装器自动参数校验（使用原始工具的 inputSchema）

3. **透明路由**
   - `call_any_tool()` 根据工具名自动路由到正确子服务器
   - 支持带前缀和不带前缀的工具名

## 影响范围

- **BrowseHive Agent 职责迁移**: 不再需要手动封装每个工具，Meta MCP 自动具备全部子服务器能力
- **.mcp.json**: 用户只需配置 `meta` 服务器，由它管理子服务器
- **Claude Desktop 配置**: 从多个 MCP 入口简化为单一 Meta MCP 入口

## 文件变更

- `MCP/scripts/meta-mcp-server.py`: 完全重写，删除所有硬编码工具
- `.mcp.json`: 新增 `"meta"` 服务器配置
- `browsehive_agent.py`: 修复 cdp_port 未定义 bug，添加 BU_CDP_URL 支持
- `unified_agent_cli.py`: 标记 BrowseHive Agent 为 deprecated

## 使用示例

```json
// .mcp.json
{
  "mcpServers": {
    "meta": {
      "command": "python",
      "args": ["MCP/scripts/meta-mcp-server.py"]
    }
  }
}
```

Claude Desktop 连接 meta 后，可直接调用：
- `ask_doubao(message)` (原 ai-chat 工具)
- `smart_ask(message)` (智能路由)
- `batch_ask(message, platforms="doubao,deepseek")` (多平台)
- `health_check()` (健康检查)
- …以及所有其他工具

## 状态

✅ 核心功能完成  
⏳ 文档更新进行中（README、SKILL.md）
⏳ Unified Agent CLI 后续可迁移至直接使用 Meta MCP
