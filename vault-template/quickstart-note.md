---
title: 欢迎使用AI知识库
created: 2025-05-17
tags: [meta, getting-started]
entities: [Claude, LLM Wiki, Obsidian]
category: meta
---

# 欢迎使用AI知识库

这是一个由Claude + LLM Wiki + Obsidian构建的智能知识库。

## 🚀 快速开始

### 1. 查看示例文档

本vault已经包含了一些示例文档，您可以:

- 点击左侧文件列表中的文档打开
- 按 `Ctrl+G` 查看知识图谱
- 使用 `Ctrl+P` 快速搜索

### 2. 添加新文档

```
方式A (推荐):
1. 将PDF/DOCX/MD文件复制到 MyWiki/Import/ 文件夹
2. LLM Wiki会自动处理并生成Wiki页面
3. 页面会自动出现在vault中

方式B (手动):
1. 在Obsidian中创建新笔记
2. 使用 `[[双链]]` 关联其他概念
3. 添加 #标签 进行分类
```

### 3. 使用双向链接

在任意笔记中输入:

```
[[Claude]] - 跳转到Claude相关页面
[[AI工具]] - 跳转到AI工具比较
```

如果页面不存在，点击蓝色链接会创建新页面。

### 4. 探索知识图谱

- 按 `Ctrl+G` 打开Graph View
- 节点=笔记，连线=双向链接
- 越大/越黄色的节点 = 链接越多 = 核心概念
- 孤立节点 = 需要更多关联

## 📚 核心概念

### Claude
Anthropic开发的AI助手，本知识库的"大脑"。

### LLM Wiki
本地知识库应用，自动从文档提取结构化信息。

### Obsidian
Markdown笔记工具，提供双向链接和知识图谱。

## 🎯 推荐工作流

```
1. 收集资料 → 2. LLM Wiki导入 → 3. Obsidian浏览 → 4. 知识创造
```

### 每日使用

1. **收集**: 将新的PDF/MD/DOCX放入 `Import/` 文件夹
2. **处理**: LLM Wiki自动分析并生成Wiki
3. **浏览**: 在Obsidian中查看新页面，探索关联
4. **笔记**: 在 `02-Articles/` 或 `daily/` 创建自己的笔记
5. **整理**: 使用标签和双链建立联系

### 周维护

- 运行 `wiki-sync.py --sync` 同步最新内容
- 检查 `01-Inbox/` 中的新文档，整理到合适位置
- 清理空文件和无关联的孤立笔记

## ⚡ 热键速查

| 热键 | 功能 |
|------|------|
| `Ctrl+P` | 快速打开笔记 |
| `Ctrl+G` | 打开知识图谱 |
| `Ctrl+F` | 搜索 |
| `Ctrl+H` | 切换侧边栏 |
| `Ctrl+E` | 快速编辑 |
| `Ctrl+O` | 打开文件 |
| `Ctrl+S` | 保存 |
| `Ctrl+Shift+T` | 重新打开关闭的标签 |
| `Ctrl+,` | 设置 |

## 🔗 标签约定

建议使用以下标签:

- `#meta` - 元数据/说明文档
- `#reference` - 参考资料
- `#project` - 项目相关
- `#daily` - 每日笔记
- `#person` - 人物
- `#tool` - 工具
- `#concept` - 概念
- `#todo` - 待办事项

## 💡 提示

- **定期备份** - 整个vault文件夹就是您的知识资产
- **善用双链** - 这是构建知识网络的核心
- **不要过度组织** - 先写再整理，避免完美主义
- **保持简洁** - 每个笔记一个核心概念
- **关联现有内容** - 新笔记尽量链接到已有笔记

## 🆘 帮助与资源

- **Obsidian文档**: https://docs.obsidian.md
- **LLM Wiki**: https://github.com/nasui/LLM_wiki
- **双向链接教程**: 查看 `[[双向链接]]` 页面
- **本vault设置**: 查看 `SETUP-GUIDE.md`

---

**开始探索您的知识库吧！**