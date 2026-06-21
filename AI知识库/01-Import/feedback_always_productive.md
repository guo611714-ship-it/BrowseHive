---
name: feedback_always_productive
description: 等待后台代理时必须并行工作，不能空闲等待
metadata: 
  node_type: memory
  type: feedback
  originSessionId: adfa8aea-7c09-45ee-85c5-0d4b3a565090
---

等待后台代理执行时，不能空闲等待，必须并行做不重叠的工作。

**Why:** 用户明确指出"你还是会在agent team干活的时候偷懒"，空闲等待浪费生产力，违背"效费最优"原则。

**How to apply:** 
- 启动后台代理后，立即找不重叠的任务执行
- 可做的工作：更新CLAUDE.md/skill文件、准备记忆、review其他代码、分析下一步
- 绝对不能：重复确认代理状态、空闲输出"等待中"、无意义的进度播报
- 与代理文件冲突的工作不做，其他一切都可以做
