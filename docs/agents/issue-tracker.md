# Issue Tracker Configuration

## Type: Local Markdown

This repository uses **Local Markdown** for issue tracking. This is suitable for:
- Solo projects
- Projects without a remote repository
- Early-stage prototypes before setting up a full issue tracker

## Structure

Issues are stored as markdown files in the `.scratch/` directory, organized by feature or category:

```
.scratch/
├── feature-name/
│   ├── 001-issue-title.md
│   ├── 002-another-issue.md
│   └── ...
├── bug-fixes/
│   └── ...
└── ...
```

## File Format

Each issue file follows this template:

```markdown
---
title: Issue title
status: needs-triage | needs-info | ready-for-agent | ready-for-human | wontfix
created: 2025-05-13
assignee: (optional)
---

## Problem Statement

Description of the problem or feature request.

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Notes

Any additional context, screenshots, or references.
```

## Operations

### Creating an Issue

```bash
# Manual creation
mkdir -p .scratch/feature-name
cat > .scratch/feature-name/001-my-issue.md
# (paste template content)
```

### Listing Issues

```bash
find .scratch -name "*.md" -exec grep -h "^title:" {} \;
```

### Updating Status

Edit the `status:` frontmatter field in the issue file.

### Workflow

The `/triage` skill reads from and writes to this `.scratch/` structure. It will:
- Detect existing issues
- Apply labels via status field
- Create agent briefs in issue bodies
- Move issues through the state machine

## Notes for Agents

- The `gh` CLI or GitLab CLI are **not** used
- All operations are file-based
- `.scratch/` can be added to `.gitignore` if issues are not meant to be version controlled
- For team projects, consider migrating to GitHub Issues when ready