---
name: skill-creator
description: "Create, edit, audit, tidy, validate, or restructure AgentSkills and SKILL.md files."
---

# Skill Creator

Skills are compact triggerable workflows. Metadata is always visible; body loads only after trigger; references/scripts/assets load only as needed.

## Hard rules

- Keep `SKILL.md` lean; Codex is already capable.
- Put only trigger-critical facts in frontmatter `description`.
- Quote frontmatter `description`.
- Frontmatter needs `name` + `description`; local OpenClaw skills may also use `metadata`, `homepage`, `allowed-tools`, `user-invocable`, `license`.
- Prefer noun-phrase descriptions; short generic trigger phrase, not full workflow.
- Move long examples/docs to `references/`; scripts to `scripts/`; templates/media to `assets/`.
- No extra README/changelog/setup docs inside a skill unless they are actual task references.
- Validate YAML frontmatter after edits.

## Shape

```text
skill-name/
  SKILL.md
  scripts/      optional deterministic helpers
  references/   optional docs loaded only when needed
  assets/       optional output resources/templates
  agents/       optional UI metadata
```

## Good SKILL.md

```markdown
---
name: pdf-tools
description: "Inspect, split, merge, OCR, redact, or convert PDFs with local CLI tools."
---

# PDF tools

Use for PDF manipulation. Prefer deterministic scripts for page edits.

## Workflow

1. Inspect file/page count.
2. Choose exact operation.
3. Write output beside input unless user asked otherwise.
4. Render/verify changed pages.
```


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

## Edit workflow

1. Read existing skill and nearby resource names.
2. Remove generic advice the base model already knows.
3. Keep brittle command syntax, auth caveats, safety rules, and validation.
4. Replace tables with bullets unless a table is clearly needed.
5. Relax prose; fragments ok.
6. Validate frontmatter and run any script tests touched.

## Validation

```bash
python skills/skill-creator/scripts/quick_validate.py skills/<name>
python - <<'PY'
from pathlib import Path
import yaml
for p in Path("skills").glob("*/SKILL.md"):
    text=p.read_text()
    if not text.startswith("---\n"):
        raise SystemExit(f"missing frontmatter: {p}")
    fm=text.split("---",2)[1]
    yaml.safe_load(fm)
print("ok")
PY
```

`quick_validate.py` is conservative; repo-local frontmatter may allow keys beyond public skill bundles.
