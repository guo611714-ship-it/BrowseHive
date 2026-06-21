#!/usr/bin/env python3
import sys
from pathlib import Path

SKILLS_DIR = Path.home() / ".agents" / "skills"
CLAUDE_SKILLS_DIR = Path.home() / ".claude" / "skills"

def get_skills_count():
    skills = set()
    # Check .agents/skills
    if SKILLS_DIR.exists():
        for skill_md in SKILLS_DIR.rglob("SKILL.md"):
            try:
                # Check if file is non-empty
                if skill_md.stat().st_size > 0:
                    # Read first few lines to see if meaningful
                    text = skill_md.read_text(encoding="utf-8", errors="ignore").strip()
                    if text:
                        name = skill_md.parent.name
                        skills.add(name)
            except (OSError, ValueError):
                continue
    # Check .claude/skills
    if CLAUDE_SKILLS_DIR.exists():
        for skill_md in CLAUDE_SKILLS_DIR.rglob("SKILL.md"):
            try:
                if skill_md.stat().st_size > 0:
                    text = skill_md.read_text(encoding="utf-8", errors="ignore").strip()
                    if text:
                        name = skill_md.parent.name
                        skills.add(name)
            except (OSError, ValueError):
                continue
    return len(skills), sorted(skills)

if __name__ == "__main__":
    count, skills = get_skills_count()
    print(f"Valid skills with non-empty SKILL.md: {count}")
    print("First 50:", skills[:50])
