# ADR 002: Comprehensive Skill Library Architecture

## Status

Accepted

## Context

This AI knowledge base project serves as a comprehensive repository of Claude Code skills for diverse development workflows. We needed to determine:

1. How to organize skills for discoverability and maintainability
2. Where to store skill definitions and their configuration
3. How to handle skill dependencies and external sources
4. How agents should interact with this knowledge base

## Decision

We adopted a **three-layer architecture**:

### Layer 1: Skill Sources (External GitHub Repositories)

Skills are sourced from various authoritative GitHub repositories, each specializing in a domain:

- `inference-sh-skills/skills` - AI generation skills (images, videos, avatars)
- `cloudflare/skills` - Agents SDK and Cloudflare Workers skills
- `vercel-labs/agent-skills` - React, Vercel, composition patterns
- `claude-office-skills/skills` - Office automation (Excel, PDF, OCR, Word)
- `alinaqi/claude-bootstrap` - LLM patterns and AI models reference
- Other specialized sources for niche domains

**Rationale:** Leverage existing community-maintained skills rather than building from scratch. Each source has expertise in its domain.

### Layer 2: Local Skill Lock File

`.agents/skills/skills-lock.json` declares all enabled skills with:

- `source`: GitHub repository identifier
- `sourceType`: Always "github" (could support other sources in future)
- `skillPath`: Path within the source repository to `SKILL.md`
- `computedHash`: Integrity verification for skill content

**Rationale:** Explicit declaration allows:
- Precise control over which skills are available
- Version pinning through hashes
- Easy auditing of skill sources

### Layer 3: Domain Documentation Layout

The project follows **single-context** domain documentation:

- `CONTEXT.md` - Domain glossary defining key terms (Skill, ADR, Triage Label, etc.)
- `docs/adr/` - Architecture Decision Records (including this file)
- `docs/agents/` - Agent-specific documentation (issue tracker, triage labels, domain layout)

## Directory Structure

```
.ai-knowledge-base/
├── .agents/
│   └── skills/                    # Skill library root
│       ├── skills-lock.json       # Skill declarations
│       ├── agent-tools/           # Individual skill directories
│       ├── agents-sdk/
│       ├── ai-avatar-video/
│       └── ... (25+ more skills)
├── docs/
│   ├── adr/                       # Architecture Decision Records
│   │   ├── 0001-local-markdown-issue-tracker.md
│   │   └── 0002-comprehensive-skill-library.md
│   └── agents/                    # Agent documentation
│       ├── domain.md
│       ├── issue-tracker.md
│       └── triage-labels.md
├── CONTEXT.md                     # Domain glossary (single source of truth)
├── CLAUDE.md                      # Agent configuration (root)
├── .scratch/                      # Local issue storage (empty initially)
└── 项目/
    └── AI知识库/
        └── Hermes_Obsidian_LLM wkii_构建AI知识库_BV16hZFB5ERM_笔记(1.md
```

## Consequences

### Positive

- **Discoverability**: Clear directory structure makes skills easy to locate
- **Maintainability**: External sources can be updated independently
- **Extensibility**: New skills can be added by updating `skills-lock.json`
- **Documentation**: ADRs and CONTEXT.md provide context for future maintainers
- **Agent-friendly**: Single-context layout optimized for Claude Code agents

### Negative

- **Manual updates**: Adding/removing skills requires editing `skills-lock.json`
- **No version ranges**: Pinned hashes require manual updates for skill upgrades
- **Limited discovery**: No automated way to browse available skills (requires reading lock file)
- **Duplication**: `docs/agents/` mirrors some content that also exists in `.agents/`

## Next Steps

1. Document skill addition/removal process in `docs/agents/skill-management.md`
2. Consider creating a `/skill-registry` agent command to list available skills
3. Evaluate need for skill categories/tags in `skills-lock.json`
4. Populate `CONTEXT.md` with comprehensive domain terms

---

**Related ADRs:**
- [0001-local-markdown-issue-tracker.md](./0001-local-markdown-issue-tracker.md)