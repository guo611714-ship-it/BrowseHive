---
name: kb-search
description: 统一检索知识库（Memory + KB Manager + AI回答）
---

# 统一知识库检索

## 用法

```text
/kb-search <问题或关键词>
```

## 功能

同时搜索 Memory 知识库和 KB Manager，合并结果，AI 生成回答。

## 执行步骤

1. 调用 `kb-manager.py unified-search` 搜索两个知识库
2. 按相关度排序，AI 重排序
3. 基于检索结果生成回答，附带来源标注

## 搜索范围

- **Memory 知识库**：`~/.claude/memory/knowledge/` 下的所有 markdown 文件
- **KB Manager**：`AI知识库/01-Import/` 下的结构化文档

## 示例

```text
/kb-search 变频器工作原理
/kb-search Python异步编程最佳实践
/kb-search LoRA微调的适用场景
```

