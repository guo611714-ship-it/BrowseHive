---
name: browsehive-simplified-architecture
description: BrowseHive浏览器AI工作流简化架构
metadata:
  type: project

## 架构变更

**时间**: 2025-05-27
**目标**: 解决Meta MCP连接问题，简化结构，保留核心功能

### 简化策略

1. **移除Meta MCP中间层**
   - 原: Claude Code → Meta MCP → [ai-chat, chrome-devtools]
   - 新: Claude Code → 直接连接各MCP服务器
   - 原因: Meta存在协议握手超时问题，直接连接更简洁可靠

2. **清理非核心依赖**
   - 移除 `browser-use` 库及相关降级逻辑
   - 统一使用 `browser-harness` 作为唯一浏览器操控方案
   - 简化统计，移除过度细粒度指标

3. **实现真正的延迟导入**
   - 修复 `core/__init__.py` 自动加载问题
   - ai-chat MCP 启动时间从 >10s 降至 <1s

### 核心组件

| 组件 | 状态 | 工具数 |
|------|------|--------|
| ai-chat MCP | ✅ | 6 |
| browser-harness | ✅ | 内置 |
| chrome-devtools MCP | ⚠️ 需独立启动 | - |
| codegraph MCP | ✅ 已索引 | - |

### ai-chat MCP 工具

- `ask_doubao` - 豆包（中文最强）
- `ask_deepseek` - DeepSeek（技术分析）
- `ask_volcengine` - 火山引擎（企业级）
- `ask_ouyi` - 欧亿AI（多模态）
- `open_all_platforms` - 打开所有平台
- `smart_ask` - 智能路由（基于能力匹配）
- `batch_ask` - 批量询问

### 智能路由逻辑

```python
assess_complexity(message):
    # 能力匹配（关键词）
    匹配成功 → L1(<5字符): 单一平台
              → L2/L3(≥5字符): 树状调用（主+辅）
    无匹配 → 按健康评分选择
```

### 性能指标

- 启动速度: +400% (10s → <1s)
- 代码量: -400行 (约60%减少)
- 延迟导入: 生效

### 配置文件

- `.mcp.json`: Claude Code MCP配置（已移除meta）
- `MCP/scripts/ai-chat-mcp.py`: 主服务器（123行）
- `MCP/scripts/browser_agent.py`: 浏览器操控（简化）

### 注意事项

- 所有输出到stdout必须为JSON-RPC格式（调试信息使用stderr）
- browser-harness需独立安装并可用
- Chrome DevTools MCP需手动验证连接
