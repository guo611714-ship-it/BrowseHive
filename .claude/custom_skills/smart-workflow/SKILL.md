---
name: smart-workflow
description: Automatically analyze tasks, discover relevant skills, and execute intelligent workflows with optional web search. Use when user says "smartstart", "auto mode", "intelligent mode", or requests automated task execution.
---

# 智能工作流系统

自动化的任务处理工作流，智能决定何时调用技能、何时联网搜索，最大化 Claude Code 的效率。

## Quick Start

```bash
用户: /smartstart
Claude: 正在执行智能工作流...
       → 分析任务需求
       → 调用 find-skills 发现相关能力
       → 如有需要调用 searXNG 搜索
       → 推荐并执行最佳工作流
```

## Workflows

### 1. 标准智能工作流

**触发**: 用户输入包含 "smartstart"、"auto"、"intelligent"、"自动"、"智能工作流"

**步骤**:

1. **任务分析** - 使用 `Agent` 或直接分析：
   - 识别任务类型（开发、研究、写作、调试等）
   - 提取关键词和概念
   - 判断是否需要最新信息（决定是否联网搜索）

2. **技能发现** - 调用 `find-skills`：
   ```
   /find-skills 或使用 find-skills skill
   搜索与任务相关的技能
   ```

3. **决策** - 基于发现：
   - 如果有相关 skill → 推荐使用
   - 如果需要最新信息 → 调用 `ai-search` 或 `searXNG`
   - 如果是代码任务 → 可能需要 `react`、`python-design-patterns` 等

4. **执行** - 按照最优路径完成任务

5. **反馈** - 记录本次工作流到分析服务器

### 2. 纯搜索模式

**触发**: 用户输入包含 "ai-search"、"联网搜索"、"search"

**步骤**:

1. 提取搜索关键词
2. 调用 `searXNG` 或 `WebSearch`
3. 整理搜索结果
4. 提供详尽答案

### 3. 工作环境分析

**触发**: 用户输入 "workon"、"分析环境"、"recommend"

**步骤**:

1. 使用 `Glob`、`Grep`、`Read` 扫描当前目录
2. 识别项目类型（React、Python、Node.js 等）
3. 列出相关文件结构
4. 推荐适合的技能和工作流

## Advanced Features

### 集成分析服务器

智能工作流自动调用本地分析服务器（`http://localhost:8765`）：

```javascript
// 记录工作流元数据
POST /analyze
{
  "type": "workflow_execution",
  "data": {
    "task": "用户任务描述",
    "skills_used": ["skill1", "skill2"],
    "search_performed": true/false,
    "duration_seconds": 123,
    "tokens_estimated": 4567
  }
}
```

### 自动化决策规则

| 条件 | 动作 |
|------|------|
| 包含 "latest"、"2025"、"current" | 启用搜索 |
| 关键词匹配 `bug`、`error`、`fix` | 调用 `review` 技能 |
| 关键词匹配 `deploy`、`publish` | 调用 `deploy-to-vercel` |
| 关键词匹配 `security`、`vulnerability` | 调用 `security-review` |
| 文件扩展名 `.py` | 考虑 `python-design-patterns` |
| 文件扩展名 `.jsx`、`.tsx` | 考虑 `react` |

### 性能优化

- 缓存技能发现结果（1小时内有效）
- 并行调用多个搜索源
- 使用分析服务器记录历史决策

## Implementation Template

在 Claude Code 会话中，当识别到智能工作流请求时：

```bash
# 1. 分析任务
echo "🔍 分析任务需求..."

# 2. 发现技能
/use find-skills  # 或直接调用

# 3. 如有需要搜索
/use ai-search

# 4. 推荐并执行
echo "✅ 推荐工作流已完成"
```

## Configuration

默认配置（无需修改）：

```json
{
  "workflow": {
    "auto_search_keywords": ["latest", "current", "news", "2025", "2026"],
    "always_search_types": ["news", "trends", "comparison"],
    "skill_cache_ttl": 3600,
    "analytics_enabled": true,
    "analytics_endpoint": "http://localhost:8765/analyze"
  }
}
```

## Examples

### Example 1: 开发任务
```
用户: /smartstart 请帮我创建一个 React 组件
Claude: 智能工作流...
       → 发现技能: react, react-best-practices
       → 不需要搜索（稳定技术）
       → 推荐: 使用 React skill 创建组件
```

### Example 2: 研究任务
```
用户: /auto 最新的 AI 视频生成工具有哪些？
Claude: 智能工作流...
       → 检测到 "最新" → 启用搜索
       → 调用 ai-search 查询 2025 年工具
       → 返回: Veo, Seedance, etc.
```

### Example 3: 安全检查
```
用户: /intelligent 请检查这个 API 的安全性
Claude: 智能工作流...
       → 关键词 "安全" → 调用 security-review
       → 执行完整安全审计
```

## Troubleshooting

**问题**: 智能工作流没有调用技能
**解决**: 确保 `find-skills` skill 已安装并可用

**问题**: 搜索没有启用
**解决**: 检查任务是否包含触发关键词（latest, current, 2025等）

**问题**: 分析服务器连接失败
**解决**: 服务器会在 Claude 启动时自动启动，或手动运行 `start_analytics_server.sh`

---

*该 skill 会自动适应你的使用模式，频繁使用的路径会被优先推荐。*
