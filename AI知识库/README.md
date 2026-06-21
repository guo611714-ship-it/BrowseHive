# AI知识库 — 双轨知识管理系统

轻量级本地知识库，Memory + Obsidian Vault 双轨并行，NVIDIA API 免费深度分析。

## 架构

```
Track 1: Memory知识库     → Claude 直接 recall，零成本日常积累
Track 2: KB Manager       → NVIDIA AI 深度分析，结构化存储
5个 Skill                 → /learn /kb-search /kb-browse /kb-maintenance /kb-batch-import
```

## 快速开始

```bash
cd AI知识库
python kb-manager.py          # 显示帮助
python kb-manager.py init     # 初始化目录
```

## 命令

| 命令 | 用途 | 示例 |
|------|------|------|
| `init` | 初始化目录 | `python kb-manager.py init` |
| `list` | 列出所有文档 | `python kb-manager.py list` |
| `analyze-text` | AI深度分析 | `python kb-manager.py analyze-text --title "标题" --category ai --file doc.md`（也可用 `--text "text"` 代替 `--file`） |
| `unified-search` | 双轨搜索 | `python kb-manager.py unified-search "问题"` |
| `batch-import` | 批量导入 | `python kb-manager.py batch-import ./docs --category programming [--memory-dir D]`（加 `--to-memory` 同步到 Memory） |
| `sync-memory-to-kb` | Memory→KB | `python kb-manager.py sync-memory-to-kb --memory-dir ~/.claude/.../memory` |
| `sync-kb-to-memory` | KB→Memory | `python kb-manager.py sync-kb-to-memory --memory-dir ~/.claude/.../memory` |
| `rebuild-index` | 重建索引 | `python kb-manager.py rebuild-index --memory-dir ~/.claude/.../memory` |
| `backup` | Git备份 | `python kb-manager.py backup` |

## 配置

1. 复制 `.env.example` 为 `.env`，填入 NVIDIA API Key（免费）
2. 编辑 `config.json` 调整模型和参数

## 测试

```bash
pip install pytest pytest-cov
python -m pytest tests/test_kb_manager.py -v    # 27个单元测试（9s）
python -m pytest tests/test_e2e.py -v            # 7个端到端测试（~160s，需API key）
```

## 目录结构

```
AI知识库/
├── kb-manager.py          核心CLI（398行，9命令）
├── config.json            配置
├── .env                   API密钥（不入库）
├── tests/                 34个测试
├── 01-Import/             导入的文档
├── 02-Notes/              笔记
├── 03-Index/              索引
├── kb_backup.py           Git备份守护进程
└── kb_sync.py             文件同步守护进程
```

## 依赖

- Python 3.10+
- openai（NVIDIA API兼容）
- pytest, pytest-cov（测试）
