# Claude + LLM Wiki + Obsidian AI知识库体系

## 概述

基于Hermes+LLM Wiki+Obsidian原版工作流，适配Windows + Claude Code环境的AI知识库体系。

## 架构

```
用户指令
    ↓
Claude Code（自动化引擎）
    ↓
LLM Wiki（知识处理引擎）
    ↓
Wiki文件夹（Markdown页面）
    ↓
Obsidian（展示层 - 双向链接 + 知识图谱）
    ↓
用户（提问探索）
```

## 三工具分工

| 工具 | 角色 | 功能 |
| --- | --- | --- |
| **Claude Code** | 自动化执行引擎 | 接收指令，文件操作，知识库管理 |
| **LLM Wiki** | 知识处理引擎 | 文档处理，增量Wiki构建 |
| **Obsidian** | 笔记展示层 | 双向链接，知识网络可视化 |

## 路径配置

```text
知识库根目录: 项目/AI知识库/AI知识库/
├── wiki/                    # LLM Wiki生成的页面
├── raw/sources/             # 原始文档
│   └── Import/              # 待导入文档
├── .obsidian/               # Obsidian配置
└── .llm-wiki/               # LLM Wiki配置
```

## 快捷命令

| 命令 | 描述 | 示例 |
|------|------|------|
| `/kb-import <路径>` | 导入文档 | `/kb-import ./doc.pdf` |
| `/kb-search <关键词>` | 搜索知识库 | `/kb-search 电机控制` |
| `/kb-browse` | 浏览结构 | `/kb-browse` |
| `/kb-sync` | 同步状态 | `/kb-sync` |

## 核心规则

### 规则一：导入知识库
当你说"导入知识库"、"写入知识库"时，Claude会：
1. 验证文件
2. 复制到 `raw/sources/Import/`
3. 提示在LLM Wiki中导入

### 规则二：检索知识库
当你说"结合知识库"、"查一下知识库"时，Claude会：
1. 搜索Wiki页面
2. 搜索原始文档
3. 整合信息回答

### 规则三：日常对话不污染
日常对话（如问天气）不会读取知识库，保证检索精准。

## 使用流程

### 1. 导入新文档
```bash
# 方式一：使用快捷命令
/kb-import C:\path\to\document.pdf

# 方式二：手动复制
copy document.pdf 项目\AI知识库\AI知识库\raw\sources\Import\
```

然后在LLM Wiki中：
1. 打开项目
2. 右键文件区 → Import
3. 选择刚复制的文件

### 2. 生成Wiki页面
在LLM Wiki对话框中提问：
- "总结这篇文档的核心内容"
- "提取关键概念和实体"
- "创建知识图谱"

AI会在右侧预览区生成结构化Wiki页面，自动保存到 `wiki/` 目录。

### 3. 在Obsidian中浏览
1. 打开Obsidian
2. 打开Vault：`项目/AI知识库/AI知识库/`
3. 使用双向链接浏览知识网络
4. 按 `Ctrl+G` 打开知识图谱

### 4. Claude中检索
在Claude Code中：
```
结合知识库，介绍一下变频器的工作原理
```

Claude会搜索知识库并整合回答。

## 与原版工作流的差异

| 原版(Hermes) | 本版(Claude Code) |
|--------------|-------------------|
| macOS专用 | Windows跨平台 |
| AppleScript自动化 | Bash/文件操作自动化 |
| Hermes对话界面 | Claude Code终端 |
| 需要辅助访问权限 | 无需特殊权限 |

## 文件说明

- `scripts/kb/kb-manager.sh` - Linux/Mac管理脚本
- `scripts/kb/kb-import.bat` - Windows导入脚本
- `.claude/skills/kb-*.md` - Claude快捷命令定义
- `CLAUDE.md` - 知识库配置说明
