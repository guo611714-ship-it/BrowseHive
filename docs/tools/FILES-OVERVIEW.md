# Windows AI知识库 - 文件总览

本文档列出所有文件及其用途，帮助您快速了解系统结构。

## 📂 根目录文件

| 文件 | 用途 |
|------|------|
| `kb-manager.py` | **核心脚本** - 知识库管理CLI工具（主程序） |
| `win-start.bat` | **启动脚本** - Windows快速启动菜单 |
| `requirements.txt` | Python依赖列表（anthropic等） |
| `CONTEXT.md` | 领域词汇表 - 项目的术语解释 |
| `CLAUDE.md` | Claude Agent配置 |
| `skills-lock.json` | Claude Code技能库配置 |
| `.gitignore` | Git忽略规则 |
| `README-Windows-KB.md` | 完整使用指南 |

## 📁 知识库目录结构

### vault/ (Obsidian Vault)

```
vault/
├── 01-Import/         # AI导入的文档（Markdown）
├── 02-Notes/          # 您的个人笔记
│   ├── daily/
│   ├── projects/
│   └── learnings/
├── 03-Index/          # 自动索引（勿修改）
│   ├── documents.json # 文档索引
│   ├── concepts.json  # 概念索引
│   └── graph.json     # 知识图谱数据
└── .obsidian/         # Obsidian配置（可选）
```

### vault-template/ (模板)

```
vault-template/
└── README.md  - vault使用说明，复制到vault目录
```

## 📁 文档目录

### docs/

```
docs/
├── adr/                    # 架构决策记录
│   ├── 0001-local-markdown-issue-tracker.md
│   ├── 0002-comprehensive-skill-library.md
│   └── 0003-claude-api-direct-architecture.md
├── agents/                 # Agent专用文档
│   ├── domain.md          # 领域文档布局规范
│   ├── issue-tracker.md   # Issue跟踪规范
│   └── triage-labels.md   # 标签系统
└── tools/                  # 工具链文档
    ├── windows-knowledge-base-workflow.md
    ├── hermes-obsidian-llmwiki-workflow.md
    └── FILES-OVERVIEW.md   (本文件)
```

## 📁 其他目录

| 目录 | 用途 |
|------|------|
| `.agents/skills/` | Claude Code技能库（31个技能） |
| `.claude/` | Claude Code配置和缓存 |
| `.scratch/` | 问题跟踪（Local Markdown） |
| `tmp/` | 临时文件 |

## 🔑 配置文件

### vault/config.json

创建后位置：`vault/config.json`

```json
{
  "anthropic_api_key": "your-key",
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 4096,
  "vault_name": "我的知识库"
}
```

## 🎯 核心工作流文件流

### 导入文档流程

```
您的PDF/DOCX/MD文件
    ↓
kb-manager.py import
    ↓
读取内容 → Claude API分析 → 生成YAML+Markdown
    ↓
vault/01-Import/YYYY-MM-DD-title-hash.md
    ↓
vault/03-Index/documents.json (更新)
vault/03-Index/concepts.json (更新)
vault/03-Index/graph.json (更新)
    ↓
Obsidian自动识别并显示
```

### 查询流程

```
kb-manager.py query "Claude Code是什么?"
    ↓
读取 vault/03-Index/documents.json
    ↓
关键词匹配 → 找到相关文档
    ↓
读取文档前2000字
    ↓
Claude API生成回答（带来源标注）
    ↓
控制台输出
```

## 📊 文件大小参考

| 文件/目录 | 典型大小 |
|----------|---------|
| kb-manager.py | ~15 KB |
| 单个导入文档 | 5-50 KB (Markdown格式) |
| documents.json | 1-10 KB (每文档~200B) |
| graph.json | 与文档数和关联度相关 |
| vault/ (100文档) | ~5-10 MB |
| .agents/skills/ | ~50 MB |

## 🔄 版本控制建议

如果使用Git，建议：

```gitignore
# 已包含在.gitignore中
vault/config.json        # API密钥（敏感）
vault/03-Index/          # 自动生成，可从头重建
processed/               # 原始文件缓存
logs/                    # 运行日志

# 应该提交
vault/01-Import/         # 知识库内容
vault/02-Notes/          # 个人笔记
vault/.obsidian/         # Obsidian配置（可选）
```

## 🆕 新建知识库步骤

1. `mkdir my-vault && cd my-vault`
2. `python kb-manager.py init`
3. `python kb-manager.py config --set api-key YOUR_KEY`
4. `copy ..\vault-template\README.md .\README.md` (可选)
5. 在Obsidian中打开 `my-vault/` 文件夹

## 📝 相关文档导航

| 任务 | 文档 |
|------|------|
| 首次安装 | [README-Windows-KB.md](README-Windows-KB.md) |
| 理解架构 | [docs/tools/windows-knowledge-base-workflow.md](docs/tools/windows-knowledge-base-workflow.md) |
| 对比macOS方案 | [docs/tools/hermes-obsidian-llmwiki-workflow.md](docs/tools/hermes-obsidian-llmwiki-workflow.md) |
| 查看术语 | [CONTEXT.md](CONTEXT.md) |
| 贡献开发 | [docs/agents/domain.md](docs/agents/domain.md) |

---

**提示**: 本文档是"活文件"，添加新功能时请同步更新。