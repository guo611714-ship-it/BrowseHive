---
name: kb-maintenance
description: 知识库定期维护（同步+重建索引+备份+清理）
---

# 知识库维护

## 用法

```text
/kb-maintenance
```

## 功能

一键执行知识库全链路维护：同步、索引重建、备份。

## 执行步骤

### 1. Memory → KB 同步

将 Memory 知识库中的新内容同步到 Obsidian Vault：

```bash
python kb-manager.py --vault "AI知识库" sync-memory-to-kb \
  --memory-dir "C:/Users/lenovo/.claude/projects/d--Users-lenovo-Desktop-claude-workspace/memory"
```

### 2. KB → Memory 索引同步

将 KB Manager 的结构化索引同步回 Memory：

```bash
python kb-manager.py --vault "AI知识库" sync-kb-to-memory \
  --memory-dir "C:/Users/lenovo/.claude/projects/d--Users-lenovo-Desktop-claude-workspace/memory"
```

### 3. 重建 Memory 知识索引

自动扫描 knowledge/ 目录，重建 INDEX.md：

```bash
python kb-manager.py --vault "AI知识库" rebuild-index \
  --memory-dir "C:/Users/lenovo/.claude/projects/d--Users-lenovo-Desktop-claude-workspace/memory"
```

### 4. 自动备份

提交所有变更到 git：

```bash
python kb-manager.py --vault "AI知识库" backup
```

### 5. 报告

输出维护摘要：

- 同步了多少条知识
- 索引有多少条目
- 备份状态

## 注意事项

- 此命令可定期执行（如每周一次）
- 所有操作幂等，重复执行不会产生重复内容
- 不会覆盖手动修改的笔记
