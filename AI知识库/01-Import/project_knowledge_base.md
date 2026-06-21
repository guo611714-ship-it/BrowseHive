---
name: knowledge-base-system
description: 双轨知识库系统v2——Memory知识库+KB Manager+Obsidian，9个命令，NVIDIA API免费，5个skill，376行单文件
metadata: 
  node_type: memory
  type: project
  originSessionId: 7194df5c-9a78-4cbb-a2a2-939de8925a0e
---

# 双轨知识库系统

## 架构

```
Memory 知识库（轻量索引）          KB Manager（结构化深度分析）
~/.claude/memory/knowledge/        AI知识库/ (Obsidian Vault)
├── INDEX.md <- 分类索引            ├── 01-Import/ <- AI分析后的文档
├── ai/                            ├── 02-Notes/
├── programming/                   ├── 03-Index/documents.json
├── domain/                        ├── wiki/
├── tools/                         ├── raw/sources/
└── references/                    └── config.json
```

## 分工

- **Memory**：日常积累，Recall 直接命中，零成本，我直接写 markdown
- **KB Manager**：文档批量导入+AI深度分析，NVIDIA API 免费无限制

## API 配置

```
服务: NVIDIA API (OpenAI 兼容)
地址: https://integrate.api.nvidia.com/v1
模型: stepfun-ai/step-3.7-flash
配置: AI知识库/config.json
费用: 免费无限制
```

## kb-manager.py 9 个命令（v2 重建，376行单文件）

| 命令 | 用途 |
|------|------|
| `init` | 初始化知识库目录 |
| `analyze-text --title --category --file` | AI深度分析文本（供 /learn 双写） |
| `unified-search <question>` | 统一检索 Memory + KB |
| `sync-memory-to-kb --memory-dir` | Memory -> KB 同步 |
| `sync-kb-to-memory --memory-dir` | KB -> Memory 索引同步 |
| `rebuild-index --memory-dir` | 重建 Memory INDEX.md |
| `backup` | git 自动备份 |
| `batch-import <folder> [--to-memory] [--category]` | 批量导入（去重+分类） |
| `list` | 列出所有文档 |

## Skill 命令（5个，注册在 skills-index.json）

| 命令 | 用途 |
|------|------|
| `/learn <主题>` | 简单->Memory only，复杂->Memory + KB Manager 双写 |
| `/kb-search <问题>` | 统一检索（Memory + KB + AI回答） |
| `/kb-browse` | 浏览知识库结构 |
| `/kb-maintenance` | 一键维护（同步+重建索引+备份） |
| `/kb-batch-import <文件夹>` | 批量导入文件夹到 Obsidian Vault |

## 增强功能（已实现）

- **自动去重**：内容哈希检查，重复跳过
- **自动分类打标**：AI 自动选类别（AI/编程/领域/工具/参考）+ 生成标签
- **自动双向链接**：分析时传入已有索引，AI 匹配 `[[]]` 链接
- **结构化拆解**：核心观点->解释->代码->场景->误区
- **知识补全**：自动生成缺失概念提示
- **AI 重排序**：query 结果用 AI 重新排序
- **统一检索**：Memory + KB 混合召回
- **批量导入**：文件夹级别导入，支持同时写入 Memory

## 代码重构（已完成）

- `_generate_markdown()` 消除重复（analyze_text 复用）
- `_extract_title()` 提取（3处统一）
- `_content_hash()` 提取（3处统一）
- `_get_model()` 提取（3处硬编码统一）
- `_load_index()` 统一（4处手动加载统一）

## MCP 配置

| MCP | 状态 | 用途 |
|-----|------|------|
| filesystem | 启用 | 文件系统操作 |
| fetch | 启用 | HTTP 请求 |
| search (searxng) | 启用 | 搜索引擎（端口 8889） |
| codegraph | 启用 | 代码知识图谱 |

## 代码审查

- 经过 3 轮 code-review，共修复 13 个 bug
- Python 文件禁止使用 emoji，用 [OK] [ERR] [WARN] 等纯文本符号替代
- skills-index.json 中文描述已改为英文（避免编码损坏）
- 冗余清理：删除 3 个重复 skill（kb-import、kb-sync、wiki-import）

## 关键路径

- kb-manager.py: `d:\Users\lenovo\Desktop\claude workspace\AI知识库\kb-manager.py`（v2重建，376行单文件）
- Obsidian Vault: `d:\Users\lenovo\Desktop\claude workspace\AI知识库`
- Memory 知识库: `C:\Users\lenovo\.claude\projects\d--Users-lenovo-Desktop-claude-workspace\memory\knowledge`
- skills-index.json: `d:\Users\lenovo\Desktop\claude workspace\.claude\skills-index.json`

**Why:** 用户需要一套本地化的 AI 知识管理系统，支持日常积累和批量导入，API 免费无限制。

**How to apply:**
- 学东西用 `/learn`，简单写 Memory，复杂双写
- 搜问题用 `/kb-search`（统一检索）
- 批量导入用 `/kb-batch-import <folder>`
- 定期跑 `/kb-maintenance` 做同步+备份
- 安装新 skill 后必须注册到 skills-index.json [[skill-registration-rule]]
- Python 文件禁止 emoji [[no-emoji-in-python]]
