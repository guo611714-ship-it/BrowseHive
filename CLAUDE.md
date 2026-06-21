<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **AI-** (24608 symbols, 55249 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/AI-/context` | Codebase overview, check index freshness |
| `gitnexus://repo/AI-/clusters` | All functional areas |
| `gitnexus://repo/AI-/processes` | All execution flows |
| `gitnexus://repo/AI-/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

## Agent Team 知识服务（2026-06-01）

### 双层知识架构
- **结构化知识库**：kb_*.py 12个模块，知识爬取/存储/搜索/缓存/同步
- **项目记忆层**：`~/.claude/projects/<project>/memory/`，MEMORY.md索引+记忆文件

### 统一接口
- `agent/knowledge_service.py` — KnowledgeService类
  - `read_memory(keyword, limit)` — 读取项目记忆
  - `write_memory(name, content)` — 写入项目记忆
  - `search_kb(query, limit)` — 搜索结构化知识库
  - `get_context_for_task(task)` — 为任务获取上下文（自动组合memory+KB）
  - `save_task_result(task_id, result)` — 保存任务结果到记忆

### Agent Loop集成
- process_message开头：自动读取相关记忆作为上下文
- process_message结尾：自动保存工作成果到记忆
- 知识服务失败不影响主流程（try/except降级）
