# ADR 0001: Local Markdown Issue Tracker

## Status

Accepted

## Context

We needed to choose an issue tracking solution for this repository.

Options considered:
- **GitHub Issues**: Full-featured, requires `gh` CLI and GitHub remote
- **GitLab Issues**: Similar to GitHub, requires GitLab remote
- **Local Markdown**: Simple `.scratch/` directory with markdown files

This is a demonstration/solo project without a remote repository. We do not need full issue tracking capabilities yet.

## Decision

Use **Local Markdown** (`.scratch/` directory) for issue tracking.

The configuration is recorded in:
- `docs/agents/issue-tracker.md` - Detailed specification
- `docs/agents/triage-labels.md` - Label vocabulary (standard 5 roles)

## Consequences

### Positive
- No external dependencies (no Git remote, no CLI tools)
- Simple to understand and modify
- Works offline
- Easy to convert to GitHub Issues later if needed

### Negative
- No collaboration features (multiple people editing same issues)
- No web interface
- No notifications or assignees
- Manual file management required
- Not suitable for team projects or public repositories

---

**Next**: If this project grows or gets a remote repository, consider migrating to GitHub Issues via `/setup-matt-pocock-skills` (select "Other" to switch trackers).