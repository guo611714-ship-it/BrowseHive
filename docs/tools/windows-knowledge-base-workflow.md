# Windows AI知识库工作流

## 概述

在Windows环境下，我们采用**Claude API + Python自动化 + Markdown文件 + Obsidian**的替代方案，实现与macOS上Hermes+LLM Wiki+Obsidian相同的功能。

## 架构对比

| 组件 | macOS方案 | Windows方案 |
|------|----------|-------------|
| 自动化引擎 | Hermes (AppleScript) | `kb-manager.py` (Python + Claude API) |
| 知识处理 | LLM Wiki (GUI应用) | Claude API直接处理 |
| 存储格式 | LLM Wiki Wiki文件夹 | 本地Markdown文件 |
| 浏览工具 | Obsidian | Obsidian (相同) |

## 核心工具

### 1. kb-manager.py - 知识库管理器

Python脚本，提供以下功能：

```bash
# 导入文档到知识库
python kb-manager.py import "path/to/document.pdf" --category "技术文档"

# 查询知识库
python kb-manager.py query "Claude Code如何使用技能?"

# 列出所有文档
python kb-manager.py list

# 生成知识图谱数据
python kb-manager.py graph

# 创建双向链接
python kb-manager.py link "source.md" "target.md" --relation "参考"
```

### 2. Claude API

直接调用Claude API处理文档：
- 提取关键实体和概念
- 生成结构化摘要
- 建立文档间关联
- 检测知识矛盾

### 3. Obsidian Vault

标准的Obsidian保险库，存储所有Markdown文件：
- 原生支持双向链接 `[[链接]]`
- Graph View知识图谱
- 全文搜索
- 插件生态

## 目录结构

```
knowledge-base/
├── vault/                    # Obsidian Vault (Markdown文件)
│   ├── 01-Import/           # 自动导入的文档
│   │   ├── doc-title-abc123.md
│   │   └── ...
│   ├── 02-Notes/            # 手动笔记
│   │   └── ...
│   ├── 03-Index/            # 自动生成索引
│   │   ├── concepts.json    # 概念索引
│   │   ├── entities.json    # 实体索引
│   │   └── graph.json       # 知识图谱数据
│   └── .obsidian/           # Obsidian配置（可选）
├── processed/               # 处理过的原始文档缓存
├── embeddings/              # 向量嵌入缓存（用于RAG）
├── logs/                    # 操作日志
└── config.json              # 配置文件和API密钥
```

## 工作流程

### 导入新文档

1. 用户放置文档到 `import/` 文件夹或直接调用命令
2. `kb-manager.py` 读取文档内容
3. 调用Claude API分析文档，提取：
   - 关键概念（作为双向链接）
   - 实体（人名、技术名、项目名）
   - 相关已有文档
4. 生成Markdown文件保存到 `vault/01-Import/`
5. 更新索引和知识图谱
6. Obsidian自动识别新文件

### 查询知识库

1. 用户使用 `kb-manager.py query "问题"`
2. 脚本：
   - 可选：使用向量搜索查找相关文档
   - 将相关文档内容作为上下文发送给Claude
   - Claude基于知识库内容回答
   - 返回回答并标注来源
3. 结果输出到控制台或保存为Markdown

### 知识浏览 (Obsidian)

- 打开 `vault/` 文件夹作为Obsidian Vault
- 使用Graph View (`Ctrl/Cmd + G`) 查看知识网络
- 点击任意双向链接跳转
- 使用搜索查找内容

## 安装与配置

### 1. 环境准备

```bash
# 安装Python依赖
pip install anthropic pypdf2 pillow python-docx markdown

# 安装Obsidian (免费)
# 从 https://obsidian.md 下载安装
```

### 2. 配置Claude API

```bash
# 设置环境变量（推荐）
set ANTHROPIC_API_KEY=your-api-key-here

# 或创建配置文件
kb-manager.py config --set api-key=your-api-key
```

### 3. 初始化知识库

```bash
# 创建新的知识库
python kb-manager.py init "D:/path/to/my/vault"

# 或使用现有文件夹
python kb-manager.py init --existing "D:/path/to/existing/vault"
```

## Markdown文件格式

知识库中的每个文档采用标准Obsidian格式：

```markdown
---
title: 文档标题
created: 2025-05-17
source: file:///path/to/source.pdf
tags: [技术文档, AI, Claude]
entities:
  - Claude Code
  - Obsidian
  - 双向链接
related:
  - 双向链接概念
  - AI工具比较
---

# 文档标题

## 摘要

Claude Code是Anthropic开发的AI编程助手...

## 核心概念

### [[双向链接]]

Obsidian的核心功能，允许笔记之间相互引用...

### [[Claude Code]]

AI编程助手，支持多种技能...

## 参考链接

- [[Obsidian]] - 笔记软件
- [[AI工具]] - 相关工具比较

---

**来源**: 文档来源说明
**处理时间**: 2025-05-17 14:30:00
```

## 与macOS方案的区别

| 特性 | macOS (Hermes+LLM Wiki) | Windows (本方案) |
|------|------------------------|------------------|
| 界面自动化 | AppleScript控制GUI | 无界面，纯API调用 |
| LLM处理 | LLM Wiki应用内置 | Claude API直接调用 |
| 离线支持 | LLM Wiki可能支持 | 需要API密钥 |
| 成本 | LLM Wiki免费 | Claude API按使用计费 |
| 可定制性 | 限于LLM Wiki功能 | 完全开源可修改 |
| 跨平台 | 仅macOS | Windows/macOS/Linux |

## 优势

- **完全本地控制**: 所有文件都在本地
- **Obsidian原生兼容**: 无需转换
- **无GUI依赖**: 脚本方式易于集成和自动化
- **跨平台**: Python脚本可在任何系统运行
- **成本透明**: 仅Claude API费用，无其他成本

## 下一步

1. 创建 `kb-manager.py` 实现核心功能
2. 添加文档导入、查询、索引功能
3. 集成向量数据库用于语义搜索（可选）
4. 创建Obsidian插件或配置优化
5. 编写详细的使用文档