---
name: kb-batch-import
description: Batch import all files from a folder into the knowledge base with AI analysis
---

# KB Batch Import

## Usage

```text
/kb-batch-import <folder_path>
/kb-batch-import <folder_path> --to-memory
/kb-batch-import <folder_path> --category AI
```

## Function

Batch import all supported files (.md, .txt, .pdf, .docx, .doc) from a folder into the Obsidian Vault. Each file gets AI-powered analysis: auto-classify, auto-tag, auto-link, structured breakdown.

## Execution

### 单文件模式（默认）

Run the following command in the project directory:

```bash
python kb-manager.py --vault "AI知识库" batch-import "<folder_path>" [--to-memory] [--category <category>]
```

### 并行模式（多文件）

当导入文件数量 ≥ 5 时，可调用 `submit_fix_manifest` 并行执行：

```json
{
  "name": "submit_fix_manifest",
  "arguments": {
    "source": "stocktake",
    "data": {
      "skills": {
        "file1.md": {"verdict": "Improve", "reason": "Import to KB", "path": "/path/to/file1.md"},
        "file2.md": {"verdict": "Improve", "reason": "Import to KB", "path": "/path/to/file2.md"}
      }
    },
    "strategy": "parallel",
    "filter_actionable": true
  }
}
```

- `strategy: "parallel"` — 所有文件并行导入（无依赖）
- 每个文件作为一个 FixItem
- 引擎自动处理并发控制和结果汇总

### Parameters

- `<folder_path>`: Path to the folder to import (required)
- `--to-memory`: Also write to Memory knowledge base (optional)
- `--category <category>`: Default category if folder has no subdirectories (optional, default: other)

## Examples

```text
/kb-batch-import D:/docs/ai-papers
/kb-batch-import D:/docs/tutorials --to-memory
/kb-batch-import D:/docs/programming --category programming
```

## Notes

- Supported formats: .md, .txt, .pdf, .docx, .doc
- Content deduplication via hash check
- Rate limited: 1 second between files
- Subfolder names are used as category if present
