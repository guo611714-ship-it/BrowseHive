"""Skills discovery: lee SKILL.md de ~/.claude/skills + ~/.claude/plugins.

Devuelve estructura uniforme: [{name, source, path, description}].

Tolerante a:
- SKILL.md ausente (skill se ignora)
- frontmatter inválido (degradar a name = dir name)
- Plugins con namespace (plugin:skill)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import audit_io, clusters_io, config

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_DESC_RE = re.compile(r"^description:\s*(.+?)\s*$", re.MULTILINE)


def _parse_skill_md(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    m = _FRONTMATTER_RE.match(text)
    front = m.group(1) if m else text[:2000]
    name_m = _NAME_RE.search(front)
    desc_m = _DESC_RE.search(front)
    return {
        "name": (name_m.group(1).strip() if name_m else "").strip("\"'"),
        "description": (desc_m.group(1).strip() if desc_m else "").strip("\"'")[:300],
    }


def _scan_skill_dir(root: Path, source_tag: str, namespace: str | None = None) -> list[dict[str, Any]]:
    """Escanea root buscando SKILL.md a 1 nivel."""
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        parsed = _parse_skill_md(skill_md)
        name = parsed.get("name") or child.name
        if namespace:
            full_name = f"{namespace}:{name}" if ":" not in name else name
        else:
            full_name = name
        out.append({
            "name": full_name,
            "raw_name": name,
            "source": source_tag,
            "path": str(child),
            "description": parsed.get("description") or "",
        })
    return out


def discover_skills() -> list[dict[str, Any]]:
    """Discovery completo: user skills + plugins."""
    out: list[dict[str, Any]] = []
    # User-installed skills (~/.claude/skills/*)
    out += _scan_skill_dir(config.SKILLS_USER_DIR, source_tag="user")

    # Plugins (~/.claude/plugins/marketplace/<vendor>/plugins/<plugin>/skills/<skill>)
    plugins_root = config.SKILLS_PLUGINS_DIR
    if plugins_root.exists():
        # Recorrer marketplaces y plugins
        for mp in plugins_root.iterdir():
            if not mp.is_dir():
                continue
            # Caminamos un par de niveles típicos
            for plugin_dir in mp.rglob("plugins/*"):
                if not plugin_dir.is_dir():
                    continue
                skills_dir = plugin_dir / "skills"
                if not skills_dir.exists():
                    continue
                ns = plugin_dir.name
                out += _scan_skill_dir(skills_dir, source_tag="plugin", namespace=ns)
    return out


def enriched_skills(days: int = 30) -> list[dict[str, Any]]:
    """Skills + invocation/suggested counts del audit."""
    skills = discover_skills()
    stats = {row["skill"]: row for row in audit_io.skill_stats(days)}
    # Index por raw name + namespaced
    by_name = {s["name"]: s for s in skills}
    for s in skills:
        st = stats.get(s["name"])
        s["suggested"] = st["suggested"] if st else 0
        s["invoked"] = st["invoked"] if st else 0
        s["ratio"] = st["ratio"] if st else 0.0
        s["ghost"] = st["ghost"] if st else False
    # Añade ghosts que están en clusters pero NO en filesystem
    declared = set(by_name.keys())
    referenced = set()
    try:
        for cdef in (clusters_io.load_clusters().get("clusters", {}) or {}).values():
            for sk in cdef.get("skills", []) or []:
                referenced.add(sk)
    except Exception:
        pass
    missing = referenced - declared
    for m in missing:
        st = stats.get(m, {})
        skills.append({
            "name": m,
            "raw_name": m,
            "source": "missing",
            "path": "",
            "description": "(declarada en cluster pero NO en filesystem)",
            "suggested": st.get("suggested", 0),
            "invoked": st.get("invoked", 0),
            "ratio": st.get("ratio", 0.0),
            "ghost": True,
        })
    skills.sort(key=lambda s: (s["source"] != "missing", -s["suggested"], s["name"]))
    return skills
