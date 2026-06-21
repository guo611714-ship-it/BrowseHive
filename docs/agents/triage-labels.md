# Triage Label Vocabulary

This repository uses the **standard five-role system** for issue classification.

## Canonical Roles

| Role | Label | Meaning |
|------|-------|---------|
| `needs-triage` | `needs-triage` | Issue has not yet been evaluated by a maintainer |
| `needs-info` | `needs-info` | Waiting for the reporter to provide additional information |
| `ready-for-agent` | `ready-for-agent` | Fully specified, ready for an autonomous agent to implement |
| `ready-for-human` | `ready-for-human` | Requires human judgment, design decisions, or manual testing |
| `wontfix` | `wontfix` | Will not be actioned (duplicate, out of scope, rejected) |

## State Machine

```
(untriaged) --> needs-triage --> needs-info --> needs-triage (after reporter reply)
                                 |
                                 v
                          ready-for-agent
                                 |
                                 v
                          ready-for-human
                                 |
                                 v
                              wontfix
```

### Transitions

- **Untriaged → needs-triage**: `/triage` applies this label initially
- **needs-triage → needs-info**: More information required from reporter
- **needs-info → needs-triage**: Reporter replies, back to evaluation
- **needs-triage → ready-for-agent**: Fully specified, no blocking questions
- **needs-triage → ready-for-human**: Needs human-only decisions
- **Any → wontfix**: Duplicate, out of scope, rejected

## Usage Guidelines

### `/triage` Skill expectations

When you invoke `/triage`, the agent will:
1. Read the issue (or `.scratch/` file for local markdown)
2. Recommend a category (`bug` or `enhancement`) and a state role
3. Apply the appropriate label
4. Post an agent brief or triage note

### Agent Brief (for ready-for-agent)

An agent brief includes:
- Context summary (codebase knowledge, relevant modules)
- Reproduction steps (for bugs)
- Clear acceptance criteria
- Constraints and non-goals

### Triage Note (for needs-info)

```markdown
## Triage Notes

**What we've established so far:**
- point 1
- point 2

**What we still need from you (@reporter):**
- question 1
- question 2
```

## Customization

If your team already uses different label names, edit this file to map:

```yaml
needs-triage: status:needs-review
needs-info: status:awaiting-response
ready-for-agent: status:ready
ready-for-human: status:in-progress
wontfix: status:wontfix
```

Then inform the `/triage` skill by ensuring this mapping is present (the skill reads this file).

## Notes for Local Markdown

For Local Markdown trackers (`.scratch/`), labels are stored as the `status:` frontmatter field in each markdown file. The `/triage` skill will set this field appropriately.