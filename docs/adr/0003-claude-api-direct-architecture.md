# ADR 003: Claude API Direct Architecture

## Status

Accepted

## Context

Original research (Hermes + LLM Wiki on macOS) discovered a dependency on AppleScript automation, which is not available on Windows. We needed to decide how to implement the knowledge processing layer in a cross-platform way.

**Options considered:**

1. **Electron app wrapper** - Build a custom Electron app that replicates LLM Wiki functionality
2. **Single-tenant web app** - Run a local web server with UI
3. **Direct Claude API** - Use Python scripts to call Claude directly, no GUI
4. **Continue with LLM Wiki** - Run LLM Wiki in Windows via WSL/macOS VM

## Decision

We choose **Direct Claude API** architecture:

- No GUI application layer
- Python scripts (`kb-manager.py`) handle all operations
- Claude API provides all intelligence
- Obsidian remains the sole presentation layer

**Rationale:**

1. **Simplicity**: Removes the LLM Wiki dependency entirely
2. **Cross-platform**: Python + Claude API works everywhere
3. **Transparency**: All code is visible and modifiable
4. **Automation-friendly**: CLI interface integrates with any workflow
5. **Cost-effective**: No additional software licensing

## Architecture

```
┌─────────────────┐
│   User Files    │  (.pdf, .docx, .md, .txt)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│         kb-manager.py (Python)              │
│  • Text extraction                          │
│  • Claude API calls                         │
│  • Markdown generation                      │
│  • Index maintenance                        │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│            Claude API (anthropic.com)      │
│  • Document analysis                        │
│  • Entity/concept extraction                │
│  • Semantic understanding                   │
└────────┬────────────────────────────────────┘
         │
         ┌───────────────────────────────────┐
         │  Output → files                  │
         ▼                                  ▼
┌──────────────────┐              ┌──────────────────┐
│   vault/         │              │   03-Index/      │
│   01-Import/     │──────────────│   • documents    │
│   • .md files    │   Also create │   • concepts     │
│   • Extracted    │   graph.json  │   • entities     │
│     entities     │              │   • graph.json   │
└──────────────────┘              └──────────────────┘
                                           │
                                           ▼
                                     Obsidian renders
```

## Document Processing Flow

1. **Input**: User provides file path
2. **Extraction**: Script extracts raw text from file
3. **Analysis**: Claude API analyzes content and returns structured JSON
4. **Generation**: Script generates Obsidian-compatible Markdown with:
   - YAML frontmatter (title, tags, entities, source)
   - Summary section
   - Concepts list (as `[[wikilinks]]`)
   - Original content excerpt
   - Suggested links
5. **Indexing**: Update `documents.json`, `concepts.json`, `entities.json`
6. **Graphing**: Generate `graph.json` for visualization

## File Format Design

### Frontmatter Schema

```yaml
---
title: string
created: ISO 8601 date
source: file:// URI
hash: SHA-256 (first 16 chars)
tags: [string array]
entities: [string array]
category: "技术文档" | "笔记" | "参考" | "其他"
---
```

### Graph JSON Schema

```json
{
  "nodes": [
    { "id": "path/to/doc.md", "label": "Title", "type": "document" },
    { "id": "concept:Name", "label": "Name", "type": "concept" },
    { "id": "entity:Name", "label": "Name", "type": "entity" }
  ],
  "edges": [
    { "source": "concept:AI", "target": "doc.md", "type": "relates_to" },
    { "source": "entity:Claude", "target": "doc.md", "type": "mentioned_in" }
  ]
}
```

## Consequences

### Positive

- **Platform agnostic**: Works on Windows, macOS, Linux
- **No GUI dependencies**: Scripts are headless
- **Easier testing**: CLI can be unit tested
- **Lower barrier to entry**: No need to install multiple GUI apps
- **Easier troubleshooting**: Logs and errors go to console

### Negative

- **No visual feedback during processing**: Unlike LLM Wiki's live preview
- **API costs**: Claude API usage vs. potentially free LLM Wiki
- **Requires API key**: Extra step for users
- **No built-in chat interface**: Queries are separate from browsing
- **Less beginner-friendly**: CLI vs. GUI

## Alternatives Considered

### Electron App
- Rejected: Significant development effort, platform-specific packaging complexity

### Local Web Server
- Rejected: Adds unnecessary HTTP server layer, deployment complexity

### LLM Wiki under WSL
- Rejected: Complex Windows setup, still depends on X11 for GUI

## Future Considerations

1. **Optional Web UI**: Could add a simple web interface on top of the Python scripts
2. **Vector Database**: Add semantic search with embeddings
3. **Batch Operations**: Multi-file import with progress tracking
4. **Sync**: Optional cloud sync for multi-device usage

## Implementation Notes

- All Claude API calls are single-message completions (no streaming needed)
- Index files are JSON for easy parsing
- File hashing prevents duplicate imports
- All paths are stored relative to vault root for portability

---

**Related:**
- [Windows Knowledge Base Workflow](./windows-knowledge-base-workflow.md)
- [0001-local-markdown-issue-tracker.md](./0001-local-markdown-issue-tracker.md)
- [0002-comprehensive-skill-library.md](./0002-comprehensive-skill-library.md)