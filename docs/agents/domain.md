# Domain Documentation Layout

## Type: Single-Context

This repository uses a **single-context** domain documentation layout.

## Structure

```
repository root/
├── CONTEXT.md              # Domain glossary (required)
├── docs/
│   └── adr/                # Architecture Decision Records (optional but recommended)
│       ├── 0001-initial-architecture.md
│       └── 0002-database-choice.md
└── ... (source code)
```

## Files

### CONTEXT.md

The domain glossary defines key terms used in the codebase. This file is essential for agents to understand the project's ubiquitous language.

**Format**:

```markdown
# Domain Glossary

## [Term 1]

Definition in plain language. Example usage in the codebase.

## [Term 2]

Another definition with examples.

## ...

```

**Example**:

```markdown
## Order

A customer's request for products or services. Has status: `pending`, `paid`, `shipped`, `cancelled`.

Examples:
- `src/orders/order.ts` - Order entity
- `src/orders/create-order.ts` - Order creation handler
```

### docs/adr/ (Architecture Decision Records)

ADRs document important architectural decisions, trade-offs, and context.

**Naming**: Numbered with leading zeros for sortability: `0001-`, `0002-`, etc.

**Template** (from https://adr.github.io/):

```markdown
# ADR 001: Use PostgreSQL for Primary Database

## Status

Accepted

## Context

We need to choose a primary database for the application. Options considered: PostgreSQL, MySQL, MongoDB.

## Decision

We will use PostgreSQL with TypeORM.

## Consequences

### Positive
- Strong ACID guarantees
- Excellent JSON support
- Rich ecosystem

### Negative
- Slightly steeper learning curve than MySQL
- Requires more careful schema migrations
```

## Usage by Skills

These skills **read** from these files:

- `/grill-with-docs` - Updates `CONTEXT.md` inline during design sessions; creates ADRs for hard-to-reverse decisions
- `/diagnose` - Uses domain terms to understand code; checks ADRs for prior decisions that may relate to bug
- `/improve-codebase-architecture` - Uses `CONTEXT.md` vocabulary for naming; respects ADRs to avoid re-litigating settled decisions
- `/zoom-out` - References `CONTEXT.md` to explain modules using proper domain language

## Best Practices

1. **Keep CONTEXT.md updated** - When new domain terms emerge during development, add them immediately
2. **Write ADRs sparingly** - Only when all three hold:
   - Hard to reverse (significant cost to change later)
   - Surprising without context (future readers will wonder "why?")
   - Result of a real trade-off (genuine alternatives considered)
3. **Use codebase vocabulary** - Match the actual naming in the code, not idealizations
4. **Link to code** - In CONTEXT.md, include file references so agents can locate implementations
5. **Version ADRs** - If a decision is reversed, create a new ADR and mark the old one as "superseded"

## Notes for New Repositories

If this repository is new and has no domain documentation yet:

1. Start with an empty `CONTEXT.md` (will grow as you build)
2. Create `docs/adr/` directory now (even if empty)
3. Create your first ADR: `docs/adr/0001-initial-technology-choices.md`
4. The `/grill-with-docs` skill will help populate `CONTEXT.md` as you design features

## Multi-Context Alternative

If this repository is a **monorepo** with distinct bounded contexts (e.g., separate frontend/backend with different domain models), use **Multi-context** layout instead:

```
repository root/
├── CONTEXT-MAP.md            # Maps context names to their CONTEXT.md locations
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/
│   ├── billing/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/
│   └── ...
```

See `CONTEXT-MAP.md` format in the multi-context documentation.