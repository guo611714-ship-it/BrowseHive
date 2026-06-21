---
name: summarize
description: URL、文件、文本内容总结
triggers:
  - keyword: "summarize"
  - keyword: "总结"
  - keyword: "摘要"
---

# 内容总结器

## 功能
- 抓取 URL 并总结内容
- 读取文件并提取摘要
- 总结长文本

## 使用
```
load_skill summarize "https://example.com/article"
```

## 输出
提供结构化摘要：
- 主题
- 关键点（3-5条）
- 结论
- 字数统计
