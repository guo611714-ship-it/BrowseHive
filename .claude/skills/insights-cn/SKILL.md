---
name: insights-cn
description: 中文会话洞察报告生成器（优化版，支持多维度分析）
command: true
---

# Insights CN 生成任务（优化版）

当用户调用 `/insights-cn` 时，执行以下步骤生成符合官方模板的中文洞察报告：

## 执行步骤

### 1. 获取 Lakon Token 统计
```bash
lakon gain
```

### 2. 分析使用数据 (Facets)
- 读取 `~/.claude/usage-data/facets/*.json` 所有文件
- 聚合统计：
  - 总会话数、日期范围
  - 会话类型分布 (iterative_refinement, multi_task, single_task...)
  - 结果分布 (fully_achieved, mostly_achieved, partially_achieved...)
  - 目标类别分布 (bug_fix, configuration, feature_implementation...)
  - 摩擦类型统计 (wrong_approach, buggy_code, misunderstood_request...)
  - Claude帮助程度 (very_helpful, moderately_helpful...)
  - 用户满意度 (likely_satisfied, neutral, likely_dissatisfied...)
  - 提取成功案例摘要 (primary_success, brief_summary)
  - 提取失败案例详情 (friction_detail)

### 3. 读取历史消息统计
- 检查是否有 `insights-history.json` 缓存
- 计算消息总数、行数变化、文件数、天数、日均消息数

### 4. 生成中文报告（按官方模板结构）

```
# Claude Code 中文洞察报告

## 概览
- **总会话数**: X 个会话
- **分析消息数**: X,XXX 条消息
- **涉及文件**: XXX 个
- **代码变更**: +XX,XXX/-X,XXX 行
- **时间范围**: YYYY-MM-DD 至今天
- **日均消息**: XX.X 条/天

## 工作重点（What You Work On）
列出使用数据中按目标类别统计的主要工作类型，TOP 5-8

## 使用模式（How You Use CC）
从 facets 分析用户交互风格：
- 典型模式（自主运行 vs 协作指导）
- 常见干预类型
- 任务规模特征

## 做得好的（Impressive Things You Did）
从 primary_success 字段提取高频成功类型，列出具体案例摘要

## 问题所在（Where Things Go Wrong）
- 主要摩擦类型（wrong_approach, buggy_code 等）
- 高频失败模式
- 典型案例分析

## 值得尝试的功能（Features to Try）
根据摩擦类型推荐 CLAUDE.md 配置和现有功能

## 新兴使用模式（New Usage Patterns）
从会话类型和自主运行模式识别趋势

## 未来方向（On the Horizon）
基于数据提出自动化、并行化、测试驱动等改进方向

## 团队反馈
总结关键建议
```

## 注意事项

- 使用 UTF-8 编码，正确处理中文
- 优先显示数值统计，其次文字描述
- 保持报告在 150 行以内
- 如果 facets 数据缺失，只输出 lakon 统计
- 使用清晰的章节和分隔线增强可读性
