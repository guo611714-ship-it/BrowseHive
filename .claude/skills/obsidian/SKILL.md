---
name: obsidian
description: "Work with Obsidian vaults using the official obsidian CLI: read/search/create/edit notes, tasks, links, properties, plugins."
homepage: https://obsidian.md/cli
metadata: { "openclaw": { "emoji": "💎", "requires": { "bins": ["obsidian"] } } }
---

# Obsidian

Use the official `obsidian` CLI for Obsidian vault work. Vault files are plain Markdown, so direct file edits are still fine when safer/faster.

## Requirements

- Obsidian 1.12.7+ installed.
- Settings -> General -> Command line interface enabled.
- `obsidian` registered on PATH.
- Obsidian app running; the CLI connects to the running app.

Check:

```bash
obsidian version
obsidian help
```

macOS registration creates `/usr/local/bin/obsidian` pointing at the app-bundled CLI. Linux registration copies the binary to `~/.local/bin/obsidian`.

## Vault model

- Notes: `*.md`.
- Config: `.obsidian/`; avoid editing unless asked.
- Canvases: `*.canvas` JSON.
- Attachments: vault-configured folder.
- Multiple vaults are common; pass `vault="<name>"` when ambiguous.

Obsidian desktop tracks vaults here:

- `~/Library/Application Support/obsidian/obsidian.json`

## Command pattern

```bash
obsidian <command> [name=value] [flag]
obsidian vault="Notes" search query="meeting notes" format=json
```

Parameter values with spaces need quotes. Add `--copy` to copy output where useful.

## Common commands

Open/read:

```bash
obsidian open file=Recipe
obsidian open path="Inbox/Idea.md" newtab
obsidian read
obsidian read file=Recipe
```

Search:

```bash
obsidian search query="TODO" matches
obsidian search query="status::active" format=json
obsidian search:open query="project notes"
```

Create/modify:

```bash
obsidian create name="New Note"
obsidian create path="Inbox/Idea.md" content="# Idea"
obsidian append file=Note content="New line"
obsidian prepend file=Note content="After frontmatter"
```

Move/delete:

```bash
obsidian move file=Note to=Archive/
obsidian move path="Inbox/Old.md" to="Projects/New.md"
obsidian delete file=Note
```

Daily/tasks:

```bash
obsidian daily
obsidian daily:read
obsidian daily:append content="- [ ] Review inbox"
obsidian tasks all todo
obsidian task file=Note line=8 done
```

Properties/links:

```bash
obsidian tags all counts
obsidian property:read file=Note name=status
obsidian property:set file=Note name=status value=done
obsidian backlinks file=Note
obsidian unresolved verbose counts
```

Developer/debug:

```bash
obsidian plugin:reload my-plugin
obsidian dev:errors
obsidian dev:screenshot file=shot.png
obsidian eval "app.vault.getFiles().length"
```

## KB Manager Integration (from learn skill)

将知识整理成结构化文件，存入知识库并更新索引。

### 用法

```text
/learn <关键词或主题>
/learn <长文本或文件路径>    ← 内容复杂时自动触发深度分析
```

### Memory + KB Manager 双写流程

**1. 判断内容复杂度**

| 内容类型 | 复杂度 | 动作 |
| --- | --- | --- |
| 一句话概念 | 简单 | Memory only |
| 几段话的解释 | 简单 | Memory only |
| 长篇教程/论文 | 复杂 | Memory + KB Manager |
| 包含代码示例 | 复杂 | Memory + KB Manager |
| 用户给的文件路径 | 复杂 | Memory + KB Manager |
| 多个关联概念 | 复杂 | Memory + KB Manager |

**2. 写入 Memory 知识库（始终执行）**

在 `~/.claude/projects/.../memory/knowledge/<分类>/<slug>.md` 创建文件：

```markdown
---
name: <kebab-case-slug>
description: <一句话描述，包含多个关键词变体>
tags: [标签1, 标签2]
source: "<来源URL或文件路径>"
created: <YYYY-MM-DD>
---

# <标题>

## 核心概念
...

## 关键要点
- ...

## 实际应用
...

## 相关链接
- [[相关知识1]]
- [[相关知识2]]
```

**3. 深度分析（复杂内容时触发）**

当内容复杂时，调用 kb-manager 进行 AI 深度分析：

```bash
python kb-manager.py --vault "AI知识库" analyze-text \
  --title "<标题>" --category "<分类>" --file "<临时文件路径>"
```

> Windows 下 stdin 有编码问题，优先用 `--file` 参数传入内容。

这会：

- 调用 NVIDIA API 分析文档，提取概念、实体、标签
- 生成 Obsidian 兼容的 markdown 页面，存入 `AI知识库/01-Import/`
- 更新 `AI知识库/03-Index/documents.json` 索引

**4. 更新索引**

在 `knowledge/INDEX.md` 对应分类下添加条目。

### 注意事项

- description 字段要写丰富，包含同义词和变体，提高 Recall 召回率
- 每个知识文件控制在 200 行以内
- 相关链接用 `[[]]` 格式，方便未来扩展
- KB Manager 分析是异步的，不影响 Memory 写入速度

## Notes

- `file=<name>` uses Obsidian-style file resolution; `path=<vault-relative.md>` is exact.
- Prefer CLI move/delete/property commands for Obsidian-aware updates.
- Prefer direct Markdown edits for bulk text changes after locating the vault path.
- Do not rely on third-party `obsidian-cli` unless user explicitly asks for it.


## Parallel Fix (并行修复)

当任务涉及多个独立修改时，**不要逐个串行执行**。
调用 `submit_fix_manifest` 工具，由 ParallelFixEngine 并行执行：

```json
{
  "name": "submit_fix_manifest",
  "arguments": {
    "source": "stocktake",
    "data": {
      "skills": {
        "<skill_name>": {"verdict": "Improve", "reason": "<描述>", "path": "<文件路径>"}
      }
    },
    "strategy": "auto",
    "filter_actionable": true
  }
}
```

- 引擎自动处理分片、冲突预测、并行调度
- 等待返回结果后，检查 conflicts 列表
