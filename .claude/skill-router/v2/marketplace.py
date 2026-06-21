"""
marketplace.py — Auto-detección de skills no instaladas y sugerencia de instalación.

Si un cluster matchea pero alguna(s) de sus skills NO están instaladas,
sugiere el comando de instalación correspondiente al usuario (no ejecuta).
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set


SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
PLUGINS_CACHE = Path.home() / ".claude" / "plugins" / "cache"
INSTALLED_SKILLS_CACHE: Set[str] | None = None


def get_enabled_plugins() -> Dict[str, bool]:
    """Lee settings.json y devuelve el dict enabledPlugins."""
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text())
        return data.get("enabledPlugins", {})
    except (json.JSONDecodeError, OSError):
        return {}


def get_installed_skills(refresh: bool = False) -> Set[str]:
    """
    Devuelve set de nombres de skills instaladas (con sus prefijos plugin:skill).
    Cachea en memoria para evitar re-escanear el FS en cada hook.
    """
    global INSTALLED_SKILLS_CACHE
    if INSTALLED_SKILLS_CACHE is not None and not refresh:
        return INSTALLED_SKILLS_CACHE

    skills: Set[str] = set()
    # Scan PLUGINS_CACHE if exists
    if PLUGINS_CACHE.exists():
        # Escanear todos los SKILL.md de los plugins
        for skill_md in PLUGINS_CACHE.rglob("SKILL.md"):
            # Parts: marketplace/plugin/version[/subpath]/SKILL.md
            try:
                parts = skill_md.relative_to(PLUGINS_CACHE).parts
                if len(parts) < 3:
                    continue
                plugin = parts[1]
                # Nombre del skill: leer del frontmatter
                text = skill_md.read_text(encoding="utf-8", errors="ignore")
                name = None
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end != -1:
                        front = text[3:end]
                        for line in front.splitlines():
                            if line.strip().startswith("name:"):
                                name = line.split(":", 1)[1].strip().strip('"').strip("'")
                                break
                if not name:
                    # Fallback: usar nombre de carpeta
                    name = skill_md.parent.name
                # Añadir tanto el plain name como prefixed con plugin
                skills.add(name)
                skills.add(f"{plugin}:{name}")
            except (OSError, ValueError):
                continue

    # También añadir skills locales en ubicaciones conocidas
    local_paths = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".agents" / "skills",
    ]
    for local in local_paths:
        if not local.exists():
            continue
        for skill_md in local.rglob("SKILL.md"):
            # Nombre del frontmatter o de carpeta como fallback
            try:
                text = skill_md.read_text(encoding="utf-8", errors="ignore")
                name = None
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end != -1:
                        front = text[3:end]
                        for line in front.splitlines():
                            if line.strip().startswith("name:"):
                                name = line.split(":", 1)[1].strip().strip('"').strip("'")
                                break
                if not name:
                    name = skill_md.parent.name
                skills.add(name)
            except OSError:
                skills.add(skill_md.parent.name)

    INSTALLED_SKILLS_CACHE = skills
    return skills


def check_skill_availability(skill_name: str) -> bool:
    """¿La skill está instalada? (puede llevar prefijo `plugin:skill` o no)."""
    installed = get_installed_skills()
    if skill_name in installed:
        return True
    # Quitar prefijo plugin: y probar
    if ":" in skill_name:
        bare = skill_name.split(":", 1)[1]
        if bare in installed:
            return True
    return False


def find_missing_skills(skills: List[str]) -> List[str]:
    """De una lista de skills esperadas, cuáles NO están instaladas."""
    return [s for s in skills if not check_skill_availability(s)]


def suggest_install_command(missing_skill: str) -> str:
    """
    Sugiere el comando de instalación más probable para una skill faltante.
    NO ejecuta — solo devuelve texto para mostrar al usuario.
    """
    # Si lleva prefijo plugin:, sugerir habilitar plugin
    if ":" in missing_skill:
        plugin = missing_skill.split(":", 1)[0]
        return (
            f"Plugin `{plugin}` no parece estar habilitado. "
            f"Comprueba con `cat ~/.claude/settings.json | grep {plugin}` "
            f"y si aparece como `false`, cámbialo a `true`."
        )
    # Skills sueltas → posiblemente vienen de npx skills
    return (
        f"Skill `{missing_skill}` no encontrada. "
        f"Prueba `npx skills install {missing_skill}` o búscala en el marketplace."
    )


def build_missing_skills_message(missing: List[str]) -> str:
    """Mensaje legible para mostrar al usuario qué skills faltan."""
    if not missing:
        return ""
    lines = ["", "AVISO: algunas skills de este cluster no están instaladas:"]
    for s in missing:
        lines.append(f"  - {s}: {suggest_install_command(s)}")
    return "\n".join(lines)
