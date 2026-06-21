"""批量集成 fix_manifest 到高价值 Skills"""

import os

# 需要集成的 skill 列表
skills_to_integrate = [
    'claude-api', 'continuous-learning-v2', 'gitnexus-cli',
    'image-edit', 'academic-paper-reviewer', 'brainstorming',
    'ckm-design', 'gitnexus-exploring', 'next-best-practices',
    'python-debugpy', 'word-document-processor', 'developing-genkit-python',
    'karpathy-guidelines', 'node-inspect-debugger', 'notion',
    'pptx', 'receiving-code-review', 'obsidian', 'office-addin-workflow',
    'ai-models', 'ckm-design-system', 'find-skills', 'gitnexus-guide',
    'gitnexus-debugging', 'skill-creator', 'agent-team-launcher',
    'llm-patterns', 'remotion-best-practices', 'requesting-code-review',
    'session-logs',
]

# 集成模板
TEMPLATE = """

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
"""

skills_dir = '.claude/skills'
integrated = 0
skipped = 0

for skill_name in skills_to_integrate:
    skill_path = os.path.join(skills_dir, skill_name, 'SKILL.md')
    if not os.path.exists(skill_path):
        skipped += 1
        continue

    try:
        with open(skill_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否已集成
        if 'submit_fix_manifest' in content:
            skipped += 1
            continue

        # 找到合适的插入位置
        insert_pos = len(content)

        # 优先在 Workflow / Execution / Usage 等章节后插入
        for marker in ['## Workflow', '## Execution', '## Usage', '## How to', '## Process', '## Steps']:
            pos = content.find(marker)
            if pos != -1:
                # 找到这个章节的结束位置（下一个 ## 或文件末尾）
                next_section = content.find('\n## ', pos + len(marker))
                if next_section != -1:
                    insert_pos = next_section
                else:
                    insert_pos = len(content)
                break

        # 插入集成模板
        new_content = content[:insert_pos] + TEMPLATE + content[insert_pos:]

        with open(skill_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        integrated += 1
        print(f'OK {skill_name}')
    except Exception as e:
        print(f'FAIL {skill_name}: {e}')

print(f'\nDone: {integrated} integrated, {skipped} skipped')
