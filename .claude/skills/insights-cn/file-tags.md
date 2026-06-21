# Insights-CN 技能文件标签

## insights_cn.py
**功能**: 生成符合官方模板的中文洞察报告
**输入**: lakon 统计 + ~/.claude/usage-data/facets/*.json
**输出**: 11个章节的完整中文报告

### 核心数据源
- **lakon gain**: Token 节省效率（shell/工具调用过滤）
- **facets JSON**: 63个历史会话的详细分析数据
  - session_type: 会话类型分布
  - outcome: 任务完成情况
  - goal_categories: 工作目标分类
  - friction_counts: 摩擦事件统计
  - user_satisfaction_counts: 满意度
  - primary_success: 成功模式标记
  - friction_detail: 失败案例详情

### 报告结构 (11 sections)
1. Token 效率 - lakon 节省统计
2. 会话概览 - 总数、类型、日期范围
3. 核心指标 - 完成率、满意度、帮助程度
4. 工作重点 - 目标类别 TOP 8
5. 使用模式分析 - 交互特征总结
6. 做得好的 - primary_success 高频模式
7. 问题所在 - 摩擦类型+典型案例
8. 值得尝试的功能 - CLAUDE.md 建议
9. 新兴使用模式 - 基于统计的趋势识别
10. 未来方向 - 自动化/并行化/测试驱动建议
11. 团队反馈 - 总结性建议

### 关键函数
- `load_facets_data()`: 加载所有 facets JSON，UTF-8容错
- `aggregate_facets()`: 聚合统计数据为 Counter 对象
- `generate_report()`: 主报告生成逻辑
- 翻译函数: `translate_outcome()`, `translate_session_type()`, `translate_friction()`
- 映射函数: `map_goal_to_work_type()` 将目标类别转为工作类型

### 输出示例
```
## 工作重点 (What You Work On)
🔧 Bug 修复: 23 次 (36.5%)
✨ 功能开发: 13 次 (20.6%)
⚙️ 配置管理: 11 次 (17.5%)
...
```

### 与官方模板对齐
- ✅ What You Work On → 工作重点 (目标类别统计)
- ✅ How You Use CC → 使用模式分析 (会话类型+成功率)
- ✅ Impressive Things → 做得好的 (primary_success 提取)
- ✅ Where Things Go Wrong → 问题所在 (摩擦类型+案例)
- ✅ Features to Try → 值得尝试的功能 (CLAUE.md建议)
- ✅ On the Horizon → 未来方向 (自优化/并行/测试驱动)
