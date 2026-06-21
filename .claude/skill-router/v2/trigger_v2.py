#!/usr/bin/env python3
"""
Skill Router V2 — Entrada principal.

Mejoras sobre V1:
- Detección semántica con Gemini Flash 2.0 (no solo keywords).
- Concepto de "cluster" (grupos lógicos de skills/plugins).
- Anti-spam por skill Y por cluster (no re-sugerir <5 turnos).
- Auto-detección de skills faltantes con sugerencia de instalación.
- Cache LLM con TTL 1h (mismo prompt → 0 coste).
- Fallback a V1 (regex) si LLM falla o API key no disponible.
- Bypass con `[raw]` o `SKILL_ROUTER_OFF=1`.
- Volver a V1 con `SKILL_ROUTER_VERSION=1`.

Fase 1 quirúrgica (17-may-2026):
- PreToolUse inspecciona tool_input.file_path + tool_input.command + tool_match.
- Gate grace period C2: warning primero, bloqueo si el segundo turn ignora.
- gate_reminder per cluster inyectado al output.
- Multi-proyecto: merge ~/.claude/skill-router/v2/clusters.yaml +
  $CWD/.claude/skill-router/clusters.local.yaml (local wins por id).

Hooks:
    UserPromptSubmit  → matchea prompt → inyecta reminder
    PreToolUse        → path/command/tool_match → activa cluster + gate
    SessionStart      → noop (rescan se hace bajo demanda)
"""

import argparse
import fnmatch
import json
import os
import sys
import time
from pathlib import Path

ROUTER_V2 = Path(__file__).parent
ROUTER_V1 = ROUTER_V2.parent
sys.path.insert(0, str(ROUTER_V2))
sys.path.insert(0, str(ROUTER_V1))

# Imports V2
try:
    import yaml
except ImportError:
    yaml = None

from state import (  # noqa: E402
    load_state, save_state, increment_turn, is_recently_invoked,
    is_cluster_recently_invoked, record_invocation, filter_unrecent_skills,
    cache_llm_result, get_cached_llm_result, increment_llm_counter,
    activate_skill_gate, get_active_gate, satisfy_gate_if_match,
    reset_turn_skill_flags, mark_skill_invoked_this_turn, global_gate_blocks,
)
from marketplace import find_missing_skills, build_missing_skills_message  # noqa: E402
from llm_match import match_semantic, get_api_key  # noqa: E402

# Import V1 trigger module (regex fallback)
import importlib.util  # noqa: E402
_v1_spec = importlib.util.spec_from_file_location("trigger_v1", ROUTER_V1 / "trigger.py")
_v1 = importlib.util.module_from_spec(_v1_spec)
try:
    _v1_spec.loader.exec_module(_v1)
except Exception:
    _v1 = None

# Audit V3 integration (17-may-2026, graceful — no falla si Agent B no instalado)
_ROUTER_HOME = Path(os.environ.get("SKILL_ROUTER_HOME", str(Path.home() / ".claude" / "skill-router")))
_AUDIT_PATH = _ROUTER_HOME / "v3-niveldios" / "audit"
try:
    sys.path.insert(0, str(_AUDIT_PATH))
    from logger import log_decision as _audit_log  # type: ignore[import]
    _AUDIT_AVAILABLE = True
except Exception:
    _AUDIT_AVAILABLE = False
    def _audit_log(payload: dict) -> bool:  # type: ignore[no-redef]
        return False

# Embeddings V3 integration (17-may-2026, graceful — no falla si Agent C no instalado)
# Disponible como fallback semántico para process_user_prompt si keyword/Gemini < threshold.
_EMBEDDINGS_PATH = _ROUTER_HOME / "v3-niveldios" / "embeddings"
try:
    sys.path.insert(0, str(_EMBEDDINGS_PATH))
    from search import search_skills as _embeddings_search_impl  # type: ignore[import]
    _EMBEDDINGS_AVAILABLE = True
except Exception:
    _EMBEDDINGS_AVAILABLE = False
    def _embeddings_search_impl(query: str, top_k: int = 5, threshold: float = 0.5) -> list[dict]:  # type: ignore[no-redef]
        return []


def _embeddings_search(query: str, top_k: int = 5, threshold: float = 0.5) -> list[dict]:
    """Wrapper graceful sobre Agent C search_skills. Devuelve [] si no disponible o error."""
    if not _EMBEDDINGS_AVAILABLE:
        return []
    try:
        return _embeddings_search_impl(query, top_k=top_k, threshold=threshold)
    except Exception:
        return []


CLUSTERS_YAML = ROUTER_V2 / "clusters.yaml"
LOG_FILE = ROUTER_V2 / "log.jsonl"
GATE_GRACE_FILE = ROUTER_V2 / "state" / "gate_grace.json"

# Settings defaults
DEFAULT_SETTINGS = {
    "llm_model": "gemini-2.0-flash",
    "fallback_to_v1": True,
    "dedup_turns": 5,
    "min_prompt_words": 3,
    "max_prompt_chars": 2000,
    "cache_ttl_seconds": 3600,
    "log_level": "INFO",
    "cost_alert_threshold_usd": 1.0,
    "gate_grace_ttl_seconds": 300,
    "context_injection_enabled": True,
    "context_injection_max_skills": 2,
    "context_injection_max_chars_per_skill": 3000,
    "embeddings_fallback_enabled": True,
    "embeddings_fallback_min_confidence": 0.60,
    "embeddings_fallback_top_k": 3,
    # ZH_EN_MAP cross-language matching (zero-token)
    "zh_en_map_enabled": True,
    # Jaccard semantic fallback (zero-token)
    "jaccard_fallback_enabled": True,
    "jaccard_threshold": 0.3,
    # Chain detection
    "chain_detection_enabled": True,
}


# ─────────────────────────────────────────────────────────────────────────────
# ZH_EN_MAP: Cross-language Chinese→English matching (zero-token)
# ─────────────────────────────────────────────────────────────────────────────

_ZH_EN_MAP: dict[str, list[str]] = {}


def _load_zh_en_map(force_reload: bool = False) -> dict[str, list[str]]:
    """Load ZH_EN_MAP from clusters.yaml (top-level ZH_EN_MAP section)."""
    global _ZH_EN_MAP
    if _ZH_EN_MAP and not force_reload:
        return _ZH_EN_MAP
    try:
        raw = yaml.safe_load(CLUSTERS_YAML.read_text(encoding='utf-8')) if yaml and CLUSTERS_YAML.exists() else {}
        _ZH_EN_MAP = raw.get("ZH_EN_MAP", {})
    except Exception:
        _ZH_EN_MAP = {}
    return _ZH_EN_MAP


def _match_zh_en_map(prompt: str, zh_map: dict[str, list[str]], clusters: dict) -> list[dict]:
    """Match prompt against ZH_EN_MAP. Returns list of {cluster, confidence, reason, skills}.

    For each Chinese key found in the prompt, look up its English keywords,
    then find clusters whose keywords contain any of those English keywords.
    """
    if not zh_map:
        return []

    lower = prompt.lower()
    matched_clusters: dict[str, dict] = {}

    for zh_key, en_keywords in zh_map.items():
        if zh_key.lower() not in lower:
            continue
        # For each English keyword from ZH_EN_MAP, find matching clusters
        for cluster_id, cluster_cfg in clusters.items():
            cluster_keywords = [k.lower() for k in (cluster_cfg.get("keywords") or [])]
            cluster_triggers_zh = [t.lower() for t in (cluster_cfg.get("triggers_zh") or [])]

            # Check if any ZH_EN_MAP English keyword matches cluster keywords
            score = 0
            for ek in en_keywords:
                if ek.lower() in cluster_keywords:
                    score += 1
            # Also check if the Chinese key itself is in cluster's triggers_zh
            if zh_key.lower() in cluster_triggers_zh:
                score += 2

            if score > 0:
                if cluster_id not in matched_clusters or matched_clusters[cluster_id]["confidence"] < score * 0.3:
                    matched_clusters[cluster_id] = {
                        "cluster": cluster_id,
                        "confidence": min(score * 0.3, 0.95),
                        "reason": f"ZH_EN_MAP: '{zh_key}' → {en_keywords[:3]}",
                        "skills": cluster_cfg.get("skills", []),
                    }

    return sorted(matched_clusters.values(), key=lambda x: -x["confidence"])


# ─────────────────────────────────────────────────────────────────────────────
# Multi-skill chain detection (v1.7 concept, zero-token)
# ─────────────────────────────────────────────────────────────────────────────

_CHAIN_SEPARATORS = ["，", "、", "和", "然后", "接着", "再", ",", " and ", " then ", " also "]


def _detect_chain(prompt: str, clusters: dict, zh_map: dict, chain_groups: dict) -> list[dict] | None:
    """Detect if prompt contains multiple actions that should chain skills.

    Returns list of {segment, cluster, skills} or None if no chain detected.
    """
    settings = {}
    try:
        _, settings, _ = load_clusters_config()
    except Exception:
        pass
    if not settings.get("chain_detection_enabled", True):
        return None

    # Split prompt by separators
    segments = [prompt]
    for sep in _CHAIN_SEPARATORS:
        new_segments = []
        for seg in segments:
            new_segments.extend(seg.split(sep))
        segments = new_segments

    segments = [s.strip() for s in segments if s.strip() and len(s.strip()) >= 2]
    if len(segments) < 2:
        return None

    # Match each segment independently
    results = []
    used_clusters = set()
    for seg in segments:
        # Try ZH_EN_MAP first
        zh_matches = _match_zh_en_map(seg, zh_map, clusters)
        if zh_matches:
            best = zh_matches[0]
            if best["cluster"] not in used_clusters:
                results.append({"segment": seg, "cluster": best["cluster"], "skills": best["skills"][:1]})
                used_clusters.add(best["cluster"])
                continue

        # Try keyword match
        lower = seg.lower()
        for cluster_id, cluster_cfg in clusters.items():
            if cluster_id in used_clusters:
                continue
            keywords = [k.lower() for k in (cluster_cfg.get("keywords") or [])]
            triggers_zh = [t.lower() for t in (cluster_cfg.get("triggers_zh") or [])]
            hits = sum(1 for kw in keywords if kw in lower)
            zh_hits = sum(1 for t in triggers_zh if t in lower)
            if hits >= 2 or zh_hits >= 1:
                results.append({"segment": seg, "cluster": cluster_id, "skills": cluster_cfg.get("skills", [])[:1]})
                used_clusters.add(cluster_id)
                break

    return results if len(results) >= 2 else None


# ─────────────────────────────────────────────────────────────────────────────
# Jaccard semantic fallback (zero-token, zero-cost)
# ─────────────────────────────────────────────────────────────────────────────

_STOP_WORDS_EN = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "his", "how", "its", "may",
    "new", "now", "old", "see", "way", "who", "why", "did", "get", "got",
    "let", "say", "she", "too", "use", "with", "that", "this", "will",
    "each", "make", "like", "long", "look", "many", "most", "over",
    "such", "take", "than", "them", "then", "what", "when", "your",
    "from", "they", "been", "have", "into", "just", "know", "also",
    "back", "only", "very", "some", "time", "about", "would",
    "his", "these", "two", "write", "go", "number", "add", "still",
    "should", "after", "being", "does", "first", "any", "where", "much",
    "using", "used",
}


def _extract_words(text: str) -> set[str]:
    """Extract meaningful words from text (English keywords + Chinese 2-4 char segments)."""
    import re
    words = set()
    lower = text.lower()
    for w in lower.split():
        c = re.sub(r"[^a-z0-9\-]", "", w)
        if len(c) > 2 and c not in _STOP_WORDS_EN:
            words.add(c)
    # Extract Chinese 2-4 char segments
    zh_matches = re.findall(r"[一-鿿]{2,4}", lower)
    words.update(zh_matches)
    return words


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _jaccard_fallback(prompt: str, clusters: dict, zh_map: dict) -> list[dict]:
    """Zero-token semantic fallback using Jaccard word overlap.

    Extracts words from prompt and cluster keywords/triggers, computes similarity.
    """
    prompt_words = _extract_words(prompt)
    # Also add ZH_EN_MAP translated words
    for zh_key, en_keywords in zh_map.items():
        if zh_key.lower() in prompt.lower():
            prompt_words.update(k.lower() for k in en_keywords)

    if not prompt_words:
        return []

    results = []
    for cluster_id, cluster_cfg in clusters.items():
        cluster_words = set()
        for kw in (cluster_cfg.get("keywords") or []):
            cluster_words.add(kw.lower())
        for t in (cluster_cfg.get("triggers_zh") or []):
            cluster_words.add(t.lower())
        for t in (cluster_cfg.get("triggers_natural") or []):
            cluster_words.update(_extract_words(t))

        sim = _jaccard_similarity(prompt_words, cluster_words)
        if sim > 0:
            results.append({
                "cluster": cluster_id,
                "confidence": min(sim, 0.95),
                "reason": f"Jaccard: {sim:.2f}",
                "skills": cluster_cfg.get("skills", []),
            })

    results.sort(key=lambda x: -x["confidence"])
    return results[:3]


# ─────────────────────────────────────────────────────────────────────────────
# Context Injection (17-may-2026) — carga SKILL.md y los inyecta completos
# ─────────────────────────────────────────────────────────────────────────────

# Cache de paths SKILL.md descubiertos en runtime (warm-cache simple per-process).
_SKILL_PATH_CACHE: dict[str, str | None] = {}


def _candidate_skill_paths(skill_name: str) -> list[Path]:
    """Devuelve la lista ordenada de paths candidatos donde un SKILL.md podría vivir.

    Orden (más específico → más genérico):
      1. ~/.claude/skills/<skill_name>/SKILL.md  (canónico CKS)
      2. ~/.agents/skills/<skill_name>/SKILL.md  (skills compartidas Agents)
      3. ~/.claude/plugins/cache/**/skills/<skill_name>/SKILL.md  (todos plugins instalados)
      4. Si nombre tiene prefijo `plugin:skill` (e.g. `superpowers:commit-work`):
         busca específicamente bajo ~/.claude/plugins/cache/**/<plugin>/**/skills/<skill>/SKILL.md
         con fallback al bare name en los paths 1-2.
    """
    home = Path.home()
    out: list[Path] = []

    if ":" in skill_name:
        plugin, bare = skill_name.split(":", 1)
        plugin_root = home / ".claude" / "plugins" / "cache"
        if plugin_root.exists():
            try:
                for repo_dir in plugin_root.iterdir():
                    if not repo_dir.is_dir():
                        continue
                    # Caso A: cache/<repo>/<plugin>/<version>/skills/<bare>/SKILL.md
                    plugin_subdir = repo_dir / plugin
                    if plugin_subdir.exists():
                        try:
                            for version_dir in plugin_subdir.iterdir():
                                if not version_dir.is_dir():
                                    continue
                                cand = version_dir / "skills" / bare / "SKILL.md"
                                if cand.exists():
                                    out.append(cand)
                        except OSError:
                            pass
                    # Caso B: cache/<repo>/<plugin>/skills/<bare>/SKILL.md (sin versión)
                    direct = repo_dir / plugin / "skills" / bare / "SKILL.md"
                    if direct.exists():
                        out.append(direct)
            except OSError:
                pass
        # Fallback bare al canónico
        out.append(home / ".claude" / "skills" / bare / "SKILL.md")
        out.append(home / ".agents" / "skills" / bare / "SKILL.md")
    else:
        out.append(home / ".claude" / "skills" / skill_name / "SKILL.md")
        out.append(home / ".agents" / "skills" / skill_name / "SKILL.md")
        # Búsqueda en plugins (cache/<repo>/<plugin>/<version>/skills/<name>/SKILL.md)
        plugin_root = home / ".claude" / "plugins" / "cache"
        if plugin_root.exists():
            try:
                for repo_dir in plugin_root.iterdir():
                    if not repo_dir.is_dir():
                        continue
                    try:
                        for plugin_dir in repo_dir.iterdir():
                            if not plugin_dir.is_dir():
                                continue
                            try:
                                for version_dir in plugin_dir.iterdir():
                                    if not version_dir.is_dir():
                                        continue
                                    cand = version_dir / "skills" / skill_name / "SKILL.md"
                                    if cand.exists():
                                        out.append(cand)
                            except OSError:
                                pass
                    except OSError:
                        pass
            except OSError:
                pass

    return out


def _load_skill_content(skill_name: str, max_chars: int = 3000) -> tuple[str | None, str | None]:
    """Carga el contenido del SKILL.md para `skill_name`. Trunca si > max_chars.

    Returns (content, path_str). Si no encuentra → (None, None).

    Cache: el path resuelto se cachea per-process. El contenido NO (puede cambiar
    entre runs). Negative cache: si no se encuentra, futuras llamadas devuelven
    rápido sin re-buscar disco.
    """
    cached_path = _SKILL_PATH_CACHE.get(skill_name)
    if cached_path == "":  # explicit miss
        return None, None

    resolved: Path | None = None
    if cached_path:
        p = Path(cached_path)
        if p.exists():
            resolved = p
        else:
            _SKILL_PATH_CACHE.pop(skill_name, None)

    if resolved is None:
        for cand in _candidate_skill_paths(skill_name):
            if cand.exists() and cand.is_file():
                resolved = cand
                _SKILL_PATH_CACHE[skill_name] = str(cand)
                break

    if resolved is None:
        _SKILL_PATH_CACHE[skill_name] = ""  # negative cache
        try:
            print(f"[skill-router] WARN: SKILL.md no encontrado para `{skill_name}`", file=sys.stderr)
        except Exception:
            pass
        return None, None

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        try:
            print(f"[skill-router] WARN: error leyendo {resolved}: {e}", file=sys.stderr)
        except Exception:
            pass
        return None, str(resolved)

    if len(content) > max_chars:
        # Reservar espacio para el marker para que el OUTPUT TOTAL respete max_chars.
        marker = f"\n\n[truncated — read full at {resolved}]"
        # Si el marker solo ocupa más de la mitad de max_chars, lo recortamos a un fallback breve.
        if len(marker) > max_chars // 2:
            marker = "\n\n[truncated]"
        budget = max(0, max_chars - len(marker))
        truncated = content[:budget].rstrip()
        content = truncated + marker

    return content, str(resolved)


def _build_injected_skills_block(
    skills: list[str],
    max_skills: int,
    max_chars_per_skill: int,
) -> tuple[list[str], list[str], list[str]]:
    """Construye el bloque markdown con SKILL.md inyectados para top-N skills.

    Returns (block_lines, skills_injected_full, skills_not_loaded).
    """
    block: list[str] = []
    injected: list[str] = []
    not_loaded: list[str] = []
    top_skills = skills[:max_skills]
    for skill in top_skills:
        content, _path = _load_skill_content(skill, max_chars=max_chars_per_skill)
        if content is None:
            not_loaded.append(skill)
            continue
        block.append("")
        block.append(f"=== SKILL: {skill} (auto-cargada por router, NO necesitas invocar Skill tool) ===")
        block.append(content)
        block.append(f"=== FIN SKILL: {skill} ===")
        injected.append(skill)
    return block, injected, not_loaded


# ─────────────────────────────────────────────────────────────────────────────
# Multi-proyecto: merge base + local clusters
# ─────────────────────────────────────────────────────────────────────────────

def _find_local_clusters_yaml(cwd: str | None) -> Path | None:
    """Busca clusters.local.yaml subiendo desde cwd hasta home/raíz.

    Patrón: <cwd>/.claude/skill-router/clusters.local.yaml (o cualquier ancestro).
    Solo se considera si el path está bajo HOME (seguridad).
    """
    if not cwd:
        return None
    try:
        cur = Path(cwd).resolve()
    except (OSError, ValueError):
        return None
    home = Path.home().resolve()
    # Solo buscamos dentro del HOME del usuario
    if not str(cur).startswith(str(home)):
        return None
    # Subir como máximo 8 niveles desde cwd buscando .claude/skill-router/clusters.local.yaml
    for _ in range(8):
        candidate = cur / ".claude" / "skill-router" / "clusters.local.yaml"
        if candidate.exists() and candidate.is_file():
            return candidate
        if cur == cur.parent:
            break
        cur = cur.parent
    return None


def load_clusters_config(cwd: str | None = None) -> tuple[dict, dict, dict]:
    """Lee clusters.yaml base + (opcional) clusters.local.yaml del proyecto.

    Returns (clusters_dict, settings_dict, debug_info_dict).
    Merge local-wins por id.
    """
    base_clusters: dict = {}
    base_settings: dict = dict(DEFAULT_SETTINGS)
    debug: dict = {
        "base_yaml": str(CLUSTERS_YAML),
        "base_loaded": False,
        "local_yaml": None,
        "local_loaded": False,
        "overrides": [],
        "additions": [],
    }

    if CLUSTERS_YAML.exists() and yaml is not None:
        try:
            data = yaml.safe_load(CLUSTERS_YAML.read_text(encoding='utf-8')) or {}
            base_clusters = data.get("clusters", {}) or {}
            base_settings = {**DEFAULT_SETTINGS, **(data.get("settings", {}) or {})}
            debug["base_loaded"] = True
        except Exception as e:
            debug["base_error"] = str(e)

    local_path = _find_local_clusters_yaml(cwd)
    if local_path and yaml is not None:
        debug["local_yaml"] = str(local_path)
        try:
            ldata = yaml.safe_load(local_path.read_text(encoding='utf-8')) or {}
            local_clusters = ldata.get("clusters", {}) or {}
            local_settings = ldata.get("settings", {}) or {}
            for cid, cdef in local_clusters.items():
                if not isinstance(cdef, dict):
                    continue
                if cid in base_clusters:
                    debug["overrides"].append(cid)
                else:
                    debug["additions"].append(cid)
                base_clusters[cid] = cdef
            # Local settings overlay (local wins)
            base_settings = {**base_settings, **local_settings}
            debug["local_loaded"] = True
        except Exception as e:
            debug["local_error"] = str(e)

    return base_clusters, base_settings, debug


def write_log(entry: dict) -> None:
    """Append-only log JSON."""
    entry.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def is_trivial_prompt(prompt: str, min_words: int = 3) -> bool:
    """¿El prompt es demasiado corto/trivial para invocar LLM?"""
    if not prompt or not prompt.strip():
        return True
    # Split by whitespace
    words = [w for w in prompt.split() if len(w) > 1]
    # Also consider Chinese characters as words if there are many
    if len(words) < min_words:
        # Count Chinese characters that could form words
        zh_char_count = sum(1 for c in prompt if '一' <= c <= '鿿')
        # Treat 2+ Chinese characters as a "word"
        if zh_char_count >= min_words * 2:
            return False
        # Check if the prompt has enough meaningful characters overall
        meaningful_chars = len([c for c in prompt if c.isalnum()])
        if meaningful_chars >= min_words * 2:
            return False
        return True
    # Saludos/cierres triviales
    trivial = {"hola", "ok", "vale", "gracias", "si", "no", "perfecto", "genial"}
    if prompt.strip().lower() in trivial:
        return True
    return False


def should_use_v2(env: dict | None = None) -> bool:
    """¿Está V2 activo? Permite volver a V1 con SKILL_ROUTER_VERSION=1."""
    env = env if env is not None else os.environ
    version = (env.get("SKILL_ROUTER_VERSION") or "").strip()
    if version == "1":
        return False
    return True


def should_bypass(prompt: str, env: dict | None = None) -> bool:
    """Bypass total (igual que V1)."""
    env = env if env is not None else os.environ
    if (env.get("SKILL_ROUTER_OFF") or "").strip() == "1":
        return True
    if (prompt or "").lstrip().startswith("[raw]"):
        return True
    return False


def context_injection_disabled_by_env(env: dict | None = None) -> bool:
    """Override env para desactivar Context Injection sin tocar clusters.yaml.

    Útil para tests Fase 1 (que dependen del flow warning→deny clásico) y
    para investigación / rollback rápido si la feature da problemas.

    Activar con: `SKILL_ROUTER_NO_CONTEXT_INJECTION=1`
    """
    env = env if env is not None else os.environ
    return (env.get("SKILL_ROUTER_NO_CONTEXT_INJECTION") or "").strip() == "1"


def build_reminder_v2(
    cluster_name: str,
    skills: list[str],
    reason: str,
    confidence: float,
    missing: list[str] | None = None,
    gate_active: bool = False,
    gate_reminder: str | None = None,
    inject_full: bool = False,
    inject_max_skills: int = 2,
    inject_max_chars: int = 3000,
) -> tuple[str, list[str]]:
    """Construye el reminder que se inyecta al agente.

    Returns (reminder_text, skills_injected_full).

    Si `inject_full=True`, carga el SKILL.md COMPLETO de las primeras
    `inject_max_skills` skills sugeridas y lo inyecta literal en el reminder.
    Eso permite al LLM consumir la skill sin invocar la tool Skill manualmente
    (que es ruidosa para el CEO porque el output del Skill tool se imprime
    literal en el chat).

    Las skills más allá del top-N se siguen mostrando como nombres con la
    instrucción clásica "invócala via Skill". Razón: limitar tokens.
    """
    # Skills "candidatas" para inyección full: solo las instaladas (NO faltantes)
    missing_set = set(missing or [])
    eligible_for_injection = [s for s in skills if s not in missing_set]

    injected_block: list[str] = []
    skills_injected_full: list[str] = []
    skills_inject_failed: list[str] = []
    if inject_full and eligible_for_injection:
        injected_block, skills_injected_full, skills_inject_failed = _build_injected_skills_block(
            eligible_for_injection,
            max_skills=inject_max_skills,
            max_chars_per_skill=inject_max_chars,
        )

    if gate_active:
        if skills_injected_full:
            # Auto-satisfied: el LLM ya tiene el SKILL.md en contexto.
            lines = [
                f"✅ GATE ACTIVO + SKILL AUTO-CARGADA — cluster `{cluster_name}` (confidence {confidence:.2f})",
                f"Razón: {reason}",
                "",
                "**El SKILL.md siguiente ya está en tu contexto. NO necesitas invocar la tool Skill.**",
                "Aplica el protocolo descrito y procede directo.",
            ]
        else:
            lines = [
                f"⛔ GATE OBLIGATORIO ACTIVO — cluster `{cluster_name}` (confidence {confidence:.2f})",
                f"Razón: {reason}",
                "",
                "**SESGO POR CONSTRUCCIÓN: si hay skill, USAS skill. No es opcional.**",
                "",
                "INVOCA AHORA una de estas skills vía la tool Skill ANTES de cualquier Bash/Edit/Write:",
            ]
    else:
        if skills_injected_full:
            lines = [
                f"CLUSTER ACTIVADO + SKILL AUTO-CARGADA: `{cluster_name}` (confidence {confidence:.2f})",
                f"Razón: {reason}",
                "",
                "**El SKILL.md siguiente ya está en tu contexto. NO necesitas invocar la tool Skill.**",
                "Sigue su protocolo y aplícalo directo. Si la skill no aplica, ignora.",
            ]
        else:
            lines = [
                f"CLUSTER ACTIVADO: `{cluster_name}` (confidence {confidence:.2f})",
                f"Razón: {reason}",
                "",
                "**Sesgo: si hay skill instalada que aplica, INVÓCALA (no improvises sin ella).**",
                "",
                "Skills relevantes (invócalas vía la tool Skill):",
            ]

    # Lista de skills no-inyectadas (siguen requiriendo invocación manual)
    remaining = [s for s in skills if s not in skills_injected_full]
    if remaining:
        if skills_injected_full:
            lines.append("")
            lines.append("Skills adicionales del cluster (invócalas via Skill si las necesitas):")
        for s in remaining:
            marker = " (NO INSTALADA — instala con `npx skills add` primero)" if s in missing_set else ""
            note = ""
            if s in skills_inject_failed:
                note = " (SKILL.md no localizado en disco)"
            lines.append(f"  - `{s}`{marker}{note}")
    else:
        # No remaining; aún así mostrar los inyectados como referencia visible
        for s in skills:
            marker = " (NO INSTALADA — instala con `npx skills add` primero)" if s in missing_set else ""
            note = " (cargada ↓)" if s in skills_injected_full else ""
            lines.append(f"  - `{s}`{marker}{note}")

    if missing:
        msg = build_missing_skills_message(missing)
        if msg:
            lines.append(msg)

    # Inyectar gate_reminder (memorias críticas + recordatorios per-cluster)
    if gate_reminder:
        lines.append("")
        lines.append("REMINDER OPERATIVO:")
        for ln in gate_reminder.strip().splitlines():
            lines.append(f"  {ln}")

    # Bloque SKILL.md auto-cargados (lo más voluminoso al final)
    if injected_block:
        lines.extend(injected_block)

    lines.append("")
    if gate_active and not skills_injected_full:
        lines.append("Bash/Edit/Write quedarán BLOQUEADOS hasta que invoques Skill. Bypass solo con [force-tool] al inicio del prompt del usuario.")
    elif gate_active and skills_injected_full:
        lines.append("Gate auto-satisfecho: el SKILL.md ya está en contexto, puedes proceder con Bash/Edit/Write aplicando su protocolo.")
    else:
        lines.append("Si ya invocaste alguna hace <5 turnos, sáltala. Si no aplica al contexto real, ignora explícitamente con [skip-cluster:<name>].")
    return "\n".join(lines), skills_injected_full


def process_user_prompt(payload: dict) -> dict:
    """
    Hook UserPromptSubmit — el principal.

    Flujo:
    1. Bypass? → noop
    2. V2 disabled? → delegar a V1
    3. Prompt trivial? → noop (sin coste)
    4. Cache hit? → usar cached result
    5. LLM semantic match → cluster + skills
    6. Anti-spam: filtrar skills/clusters recientes
    7. Detectar skills faltantes
    8. Construir reminder + log
    """
    prompt = payload.get("prompt", "")
    cwd = payload.get("cwd", "")

    if should_bypass(prompt):
        # Aún así, resetear flags del turn (no exigir skill si bypass)
        state = load_state()
        increment_turn(state)
        reset_turn_skill_flags(state, needs_skill=False)
        save_state(state)
        write_log({"hook": "UserPromptSubmit", "bypass": True})
        return {}

    if not should_use_v2():
        # Delegar a V1
        if _v1:
            return _v1.process_hook("UserPromptSubmit", payload, log_only=False)
        return {}

    clusters, settings, cfg_debug = load_clusters_config(cwd=cwd)
    if not clusters:
        # Sin config → fallback a V1
        if _v1 and settings.get("fallback_to_v1", True):
            return _v1.process_hook("UserPromptSubmit", payload, log_only=False)
        return {}

    state = load_state()
    turn = increment_turn(state)

    # Cualquier UserPromptSubmit nuevo limpia el contador de grace de turns anteriores
    # (el grace pertenece a un único cluster activo; el contador se reinicia al cambiar de turn).
    # Se reactiva más abajo si el match activa un cluster con gate.
    # NOTA: NO se borra GATE_GRACE_FILE entero, solo se permite que cada turn lo refresque.

    # GATE GLOBAL SIMPLE: regla CEO 15-may EOD — TODO prompt no-trivial exige Skill antes de Bash/Edit/Write
    force_tool_bypass = (prompt or "").lstrip().startswith("[force-tool]")
    skip_skill_bypass = "[no-skill]" in (prompt or "")
    is_trivial = is_trivial_prompt(prompt, settings.get("min_prompt_words", 3))
    needs_skill = not (is_trivial or force_tool_bypass or skip_skill_bypass)
    reset_turn_skill_flags(state, needs_skill=needs_skill)

    if is_trivial:
        save_state(state)
        write_log({"hook": "UserPromptSubmit", "turn": turn, "skipped": "trivial_prompt", "needs_skill": False})
        return {}

    # Truncar prompt largo
    max_chars = settings.get("max_prompt_chars", 2000)
    prompt_truncated = prompt[:max_chars]

    # ── Zero-cost matching: ZH_EN_MAP → chain detection → Jaccard fallback ──
    zh_map = _load_zh_en_map()
    chain_groups_cfg = {}
    try:
        _, _, _ = load_clusters_config(cwd=cwd)
        # chain_groups loaded from YAML
    except Exception:
        pass
    try:
        raw_yaml = yaml.safe_load(CLUSTERS_YAML.read_text(encoding='utf-8')) or {} if yaml and CLUSTERS_YAML.exists() else {}
        chain_groups_cfg = raw_yaml.get("chain_groups", {})
    except Exception:
        pass

    # Step 1: ZH_EN_MAP matching (zero cost)
    if settings.get("zh_en_map_enabled", True) and zh_map:
        zh_matches = _match_zh_en_map(prompt_truncated, zh_map, clusters)
        if zh_matches:
            best = zh_matches[0]
            if best["confidence"] >= 0.6:
                # High confidence ZH_EN_MAP match — skip LLM
                cluster = best["cluster"]
                confidence = best["confidence"]
                reason = best["reason"]
                skills = best["skills"]
                match = {"cluster_match": cluster, "confidence": confidence, "reason": reason, "skills": skills, "cost_usd": 0.0}
                write_log({"hook": "UserPromptSubmit", "turn": turn, "zh_en_map_match": True, "cluster": cluster, "confidence": confidence})
                # Continue to anti-spam and reminder building (jump to cluster processing)
                # We set match and fall through to the existing processing below
            else:
                # Low confidence — try Jaccard
                jaccard_results = _jaccard_fallback(prompt_truncated, clusters, zh_map)
                if jaccard_results and jaccard_results[0]["confidence"] >= settings.get("jaccard_threshold", 0.3):
                    best_j = jaccard_results[0]
                    cluster = best_j["cluster"]
                    confidence = best_j["confidence"]
                    reason = best_j["reason"]
                    skills = best_j["skills"]
                    match = {"cluster_match": cluster, "confidence": confidence, "reason": reason, "skills": skills, "cost_usd": 0.0}
                    write_log({"hook": "UserPromptSubmit", "turn": turn, "jaccard_match": True, "cluster": cluster, "confidence": confidence})
    else:
        # No ZH_EN_MAP — try Jaccard directly
        if settings.get("jaccard_fallback_enabled", True):
            jaccard_results = _jaccard_fallback(prompt_truncated, clusters, zh_map)
            if jaccard_results and jaccard_results[0]["confidence"] >= settings.get("jaccard_threshold", 0.3):
                best_j = jaccard_results[0]
                cluster = best_j["cluster"]
                confidence = best_j["confidence"]
                reason = best_j["reason"]
                skills = best_j["skills"]
                match = {"cluster_match": cluster, "confidence": confidence, "reason": reason, "skills": skills, "cost_usd": 0.0}
                write_log({"hook": "UserPromptSubmit", "turn": turn, "jaccard_match": True, "cluster": cluster, "confidence": confidence})

    # Step 2: Chain detection (zero cost) — only if no single match found
    if settings.get("chain_detection_enabled", True) and not (match and match.get("cluster_match")):
        chain_result = _detect_chain(prompt_truncated, clusters, zh_map, chain_groups_cfg)
        if chain_result and len(chain_result) >= 2:
            # Chain detected — build chain reminder
            chain_skills = []
            for cr in chain_result:
                chain_skills.extend(cr["skills"][:1])
            chain_str = " → ".join(chain_skills)
            reminder = f"[chain:{chain_str}]"
            save_state(state)
            write_log({"hook": "UserPromptSubmit", "turn": turn, "chain_detected": True, "chain": chain_str})
            return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "updatedPrompt": prompt + f"\n\n{reminder}"}}

    # Step 3: If zero-cost match found, skip LLM and process directly
    if match and match.get("cluster_match"):
        cluster = match["cluster_match"]
        confidence = match["confidence"]
        reason = match["reason"]
        skills = match["skills"]
        cost = 0.0
        # Jump to anti-spam processing (below the LLM section)
    else:
        # Cache lookup function
        def _cache_lookup(h):
            return get_cached_llm_result(h, state)

        def _cache_store(h, result):
            cache_llm_result(h, result, state, ttl=settings.get("cache_ttl_seconds", 3600))

        # LLM semantic match
        match = match_semantic(
            user_text=prompt_truncated,
            clusters=clusters,
            cwd=cwd,
            cache_lookup=_cache_lookup,
            cache_store=_cache_store,
        )

        # Si LLM falla → fallback a V1
        if match is None:
            if _v1 and settings.get("fallback_to_v1", True):
                save_state(state)
                write_log({
                    "hook": "UserPromptSubmit",
                    "turn": turn,
                    "fallback": "v1",
                    "reason": "LLM unavailable or failed",
                })
                return _v1.process_hook("UserPromptSubmit", payload, log_only=False)
            save_state(state)
            return {}

        cost = match.get("cost_usd", 0.0)
        if cost > 0:
            increment_llm_counter(state, cost)

        cluster = match.get("cluster_match")
        confidence = match.get("confidence", 0)
        reason = match.get("reason", "")
        skills = match.get("skills", [])

    if not cluster:
        save_state(state)
        write_log({
            "hook": "UserPromptSubmit",
            "turn": turn,
            "no_match": True,
            "confidence": confidence,
            "reason": reason,
        })
        return {}

    # Anti-spam: si cluster entero se invocó <dedup_turns turnos, skip
    dedup = settings.get("dedup_turns", 5)
    if is_cluster_recently_invoked(cluster, state, dedup):
        save_state(state)
        write_log({
            "hook": "UserPromptSubmit",
            "turn": turn,
            "cluster": cluster,
            "skipped": "recently_invoked",
        })
        return {}

    # Filtrar skills ya invocadas recientemente
    fresh_skills = filter_unrecent_skills(skills, state, dedup)
    if not fresh_skills:
        save_state(state)
        write_log({
            "hook": "UserPromptSubmit",
            "turn": turn,
            "cluster": cluster,
            "skipped": "all_skills_recent",
        })
        return {}

    # Detectar skills faltantes
    missing = find_missing_skills(fresh_skills)

    # GATE: activar bloqueo físico si cluster tiene gate=true Y confidence >= gate_confidence
    cluster_cfg = clusters.get(cluster, {})
    gate_enabled = cluster_cfg.get("gate", False)
    gate_threshold = cluster_cfg.get("gate_confidence", 0.85)
    force_bypass = (prompt or "").lstrip().startswith("[force-tool]")
    skip_directive = f"[skip-cluster:{cluster}]"
    user_skipped = skip_directive in (prompt or "")
    gate_active = bool(gate_enabled and confidence >= gate_threshold and not force_bypass and not user_skipped)

    # Limpiar gate viejo SIEMPRE (al inicio de cada turno con cluster nuevo)
    state["skill_gate"] = None

    if gate_active:
        # Gate skills = TODAS las skills del cluster instaladas (no solo fresh).
        # Una skill ya invocada hace turnos también puede cerrar el gate si la vuelve a invocar.
        all_cluster_skills = cluster_cfg.get("skills", [])
        installed_cluster_skills = [s for s in all_cluster_skills if s not in (missing or [])]

        # Auto-satisfacción: si alguna skill del cluster ya se invocó en últimos N turnos,
        # consideramos el gate implícitamente satisfecho (evita re-invocaciones molestas).
        recent_match = any(is_recently_invoked(s, state, dedup) for s in installed_cluster_skills)
        if recent_match:
            gate_active = False
        elif installed_cluster_skills:
            activate_skill_gate(cluster, installed_cluster_skills, state)
            # Refrescar el slot grace para este cluster (turno inicial = ningún warning todavía)
            _grace_register_active_cluster(payload.get("session_id"), cluster, installed_cluster_skills, settings)
        else:
            gate_active = False

    # Reminder operativo del cluster (memorias críticas)
    gate_reminder_text = cluster_cfg.get("gate_reminder")

    # Context Injection settings
    inject_enabled = bool(settings.get("context_injection_enabled", True))
    inject_max_skills = int(settings.get("context_injection_max_skills", 2))
    inject_max_chars = int(settings.get("context_injection_max_chars_per_skill", 3000))

    # Construir reminder (build_reminder_v2 ahora devuelve tuple)
    reminder, skills_injected_full = build_reminder_v2(
        cluster, fresh_skills, reason, confidence, missing,
        gate_active=gate_active,
        gate_reminder=gate_reminder_text,
        inject_full=inject_enabled,
        inject_max_skills=inject_max_skills,
        inject_max_chars=inject_max_chars,
    )

    # Si inyectamos SKILL.md completo Y el gate estaba activo, lo marcamos auto-satisfecho.
    # El LLM ya tiene el SKILL.md en su contexto — no necesita ejecutar Skill tool.
    if gate_active and skills_injected_full:
        # Cerrar gate del state (igual que satisfy_gate_if_match)
        gate = state.get("skill_gate")
        if gate:
            gate["satisfied"] = True
            gate["auto_satisfied"] = True
            state["skill_gate"] = gate
        # También marcar el global gate como satisfecho (regla CEO 15-may)
        state["turn_skill_invoked"] = True
        state["turn_auto_satisfied_by_injection"] = True

    # Si NO había gate (cluster suave) pero inyectamos full → también marcamos
    # el global gate como auto-satisfecho, para evitar deny en PreToolUse posterior.
    if (not gate_active) and skills_injected_full:
        state["turn_skill_invoked"] = True
        state["turn_auto_satisfied_by_injection"] = True

    # Registrar invocación
    record_invocation(cluster, fresh_skills, state)
    save_state(state)

    write_log({
        "hook": "UserPromptSubmit",
        "turn": turn,
        "cluster": cluster,
        "confidence": confidence,
        "skills_injected": fresh_skills,
        "missing_skills": missing,
        "gate_active": gate_active,
        "cost_usd": cost,
        "context_injection_applied": bool(skills_injected_full),
        "skills_injected_full": skills_injected_full,
        "cfg_debug": cfg_debug,
    })

    # Audit V3 (graceful, never raises)
    if _AUDIT_AVAILABLE:
        try:
            _audit_log({
                "session_id": payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "unknown"),
                "hook_event": "UserPromptSubmit",
                "prompt_excerpt": prompt,
                "cwd": payload.get("cwd") or os.getcwd(),
                "clusters_activated": [{"id": cluster, "confidence": float(confidence or 0), "trigger": "keyword"}] if cluster else [],
                "skills_suggested": fresh_skills,
                "skill_invoked_in_turn": None,
                "tool_name": None,
                "tool_blocked": False,
                "bypass_used": "[raw]" if "[raw]" in (prompt or "") else None,
                "outcome": "tool_executed" if cluster else "no_cluster_match",
                "context_injection_applied": bool(skills_injected_full),
                "skills_injected_full": skills_injected_full,
            })
        except Exception:
            pass

    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": reminder,
        }
    }


BLOCKABLE_TOOLS = {"Bash", "Edit", "Write", "NotebookEdit", "MultiEdit"}


# ─────────────────────────────────────────────────────────────────────────────
# Path & command matching para PreToolUse (B)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_path(p: str) -> str:
    """Normaliza un path para fnmatch (con `**`).

    fnmatch nativo de Python NO entiende `**` recursivo, así que aplicamos:
    - prefijo `**/`  → cualquier prefijo
    - `**`           → cualquier substring (incluye `/`)
    """
    return p


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """Match path-vs-pattern usando fnmatch + lógica `**` recursiva.

    Conservative: el path puede ser relativo o absoluto. Probamos ambas variantes:
    - Match directo
    - Match contra basename
    - Match con substring (`**/foo.tsx` matchea `/x/y/z/foo.tsx`)
    """
    if not path or not pattern:
        return False
    # 1. fnmatch directo
    if fnmatch.fnmatch(path, pattern):
        return True
    # 2. fnmatch sobre basename si el pattern es `**/algo` o `*algo`
    base = os.path.basename(path)
    if fnmatch.fnmatch(base, pattern):
        return True
    # 3. `**` recursivo: convertir `**/foo` → buscar substring `/foo` o final `/foo` o basename
    if "**" in pattern:
        # Reemplazar `**/` por algo que matchea cualquier substring path
        # En fnmatch, `*` matchea cualquier char EXCEPTO /. Aquí toleramos /.
        # Aplicamos heurística simple: si pattern.endswith con segmento y ese segmento aparece como sufijo del path
        suffix = pattern.replace("**/", "").replace("**", "*")
        if fnmatch.fnmatch(path, "*" + suffix):
            return True
        if fnmatch.fnmatch(path, suffix):
            return True
        # También match con cualquier ancestor segment
        # Probamos eliminando el prefijo `**/` y matcheando contra cada `path.split('/')` sufijo
        parts = path.split("/")
        for i in range(len(parts)):
            sub = "/".join(parts[i:])
            if fnmatch.fnmatch(sub, suffix):
                return True
    return False


def _command_matches_pattern(command: str, pattern: str) -> bool:
    """Match command-vs-pattern. Pattern es prefix-match exacto.

    Ejemplo: pattern="git commit" matchea "git commit -m 'foo'".
    Pattern="git push" matchea "git push origin main".
    """
    if not command or not pattern:
        return False
    cmd = command.strip()
    pat = pattern.strip()
    return cmd.startswith(pat) or (" " + pat + " ") in (" " + cmd + " ")


def _tool_input_matches(tool_input: dict, criteria: dict) -> bool:
    """Match tool_input contra un dict de criterios (e.g., `run_in_background: True`)."""
    if not isinstance(tool_input, dict) or not isinstance(criteria, dict):
        return False
    for k, v in criteria.items():
        if k not in tool_input:
            return False
        # Comparación tolerante: booleanos pueden venir como string en algunos hooks
        actual = tool_input[k]
        if actual != v and str(actual).lower() != str(v).lower():
            return False
    return True


def _classify_pretool(payload: dict, clusters: dict) -> tuple[str | None, str]:
    """Devuelve (cluster_id, razón) si algún cluster matchea el tool call.

    Conservative: solo activa cluster si path/command matchea EXACTO una regla
    declarada. Zero false positives en .md plain genérico.
    """
    tool_name = payload.get("tool_name", "") or payload.get("tool", "")
    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
    command = tool_input.get("command", "")

    for cluster_id, cdef in clusters.items():
        if not isinstance(cdef, dict):
            continue

        # 1) tool_match (lista de criterios sobre tool_name + tool_input)
        tool_match_rules = cdef.get("tool_match", []) or []
        for rule in tool_match_rules:
            if not isinstance(rule, dict):
                continue
            rule_tool = rule.get("tool_name")
            if rule_tool and rule_tool != tool_name:
                continue
            crit = rule.get("tool_input_contains", {}) or {}
            if not crit or _tool_input_matches(tool_input, crit):
                return cluster_id, f"tool_match {rule_tool} en cluster `{cluster_id}`"

        # 2) paths (solo si tool toca filesystem y hay file_path)
        if file_path and tool_name in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
            for pat in cdef.get("paths", []) or []:
                if _path_matches_pattern(file_path, pat):
                    return cluster_id, f"path `{file_path}` matchea pattern `{pat}` (cluster `{cluster_id}`)"

        # 3) commands (solo si tool es Bash y hay command)
        if command and tool_name == "Bash":
            for pat in cdef.get("commands", []) or []:
                if _command_matches_pattern(command, pat):
                    return cluster_id, f"command `{pat}` detectado (cluster `{cluster_id}`)"

    return None, ""


# ─────────────────────────────────────────────────────────────────────────────
# Gate grace period C2 (warning → bloqueo)
# ─────────────────────────────────────────────────────────────────────────────

def _grace_load() -> dict:
    """Carga estado grace persistido (por session_id)."""
    try:
        if GATE_GRACE_FILE.exists():
            return json.loads(GATE_GRACE_FILE.read_text() or "{}")
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _grace_save(data: dict) -> None:
    GATE_GRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        GATE_GRACE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    except OSError:
        pass


def _grace_prune(data: dict, ttl_seconds: int) -> dict:
    """Elimina entries expiradas."""
    now = int(time.time())
    keep = {}
    for sid, entry in data.items():
        if not isinstance(entry, dict):
            continue
        ts = entry.get("ts", 0)
        if now - ts <= ttl_seconds:
            keep[sid] = entry
    return keep


def _grace_register_active_cluster(session_id: str | None, cluster: str, skills: list[str], settings: dict) -> None:
    """Registra (o resetea) el cluster gate activo para esta sesión."""
    if not session_id:
        session_id = "_no_session_"
    data = _grace_load()
    ttl = int(settings.get("gate_grace_ttl_seconds", 300))
    data = _grace_prune(data, ttl)
    data[session_id] = {
        "cluster": cluster,
        "skills": list(skills),
        "warnings_issued": 0,
        "ts": int(time.time()),
    }
    _grace_save(data)


def _grace_get_active(session_id: str | None, settings: dict) -> dict | None:
    """Devuelve cluster gate activo si está vigente, o None."""
    if not session_id:
        session_id = "_no_session_"
    data = _grace_load()
    ttl = int(settings.get("gate_grace_ttl_seconds", 300))
    data = _grace_prune(data, ttl)
    _grace_save(data)
    return data.get(session_id)


def _grace_clear(session_id: str | None) -> None:
    if not session_id:
        session_id = "_no_session_"
    data = _grace_load()
    if session_id in data:
        data.pop(session_id, None)
        _grace_save(data)


def _grace_bump_warning(session_id: str | None) -> int:
    """Incrementa contador de warnings emitidos y lo devuelve."""
    if not session_id:
        session_id = "_no_session_"
    data = _grace_load()
    entry = data.get(session_id)
    if not entry:
        return 0
    entry["warnings_issued"] = int(entry.get("warnings_issued", 0)) + 1
    entry["ts"] = int(time.time())
    data[session_id] = entry
    _grace_save(data)
    return entry["warnings_issued"]


def process_pretool(payload: dict) -> dict:
    """
    Hook PreToolUse.
    Capa nueva V2:
      - Cluster auto-activation via paths/commands/tool_match (B).
      - Gate físico + grace period C2 (warning, luego bloqueo).
    Capa legacy V1: regex reminders (no bloquean, solo sugieren).
    """
    state = load_state()
    tool_name = payload.get("tool_name", "") or payload.get("tool", "")
    tool_input = payload.get("tool_input", {}) or {}
    session_id = payload.get("session_id", "") or ""
    cwd = payload.get("cwd", "") or ""

    # 1) Si tool es Skill, marcar turn como satisfecho (gate global) + cerrar grace si skill del cluster
    if tool_name == "Skill":
        invoked_skill = tool_input.get("skill", "") or tool_input.get("name", "")
        mark_skill_invoked_this_turn(state)
        if invoked_skill:
            satisfy_gate_if_match(invoked_skill, state)
        # ¿Cierra el grace de un cluster activo?
        clusters_all, settings_all, _ = load_clusters_config(cwd=cwd)
        grace_entry = _grace_get_active(session_id, settings_all)
        if grace_entry and invoked_skill:
            cluster_skills = grace_entry.get("skills", []) or []
            # Match exacto OR sufijo (`plugin:skill` ↔ `skill`)
            bare = invoked_skill.split(":", 1)[1] if ":" in invoked_skill else invoked_skill
            matches = invoked_skill in cluster_skills or any(
                s == invoked_skill or s == bare or (":" in s and s.split(":", 1)[1] == bare)
                for s in cluster_skills
            )
            if matches:
                _grace_clear(session_id)
        save_state(state)
        write_log({
            "hook": "PreToolUse",
            "tool": "Skill",
            "invoked_skill": invoked_skill,
            "turn_satisfied": True,
        })
        if _v1:
            try:
                return _v1.process_hook("PreToolUse", payload, log_only=False)
            except Exception:
                pass
        return {}

    # 2) Inspección B + C2: si la tool call activa un cluster via path/command/tool_match
    clusters_all, settings_all, _ = load_clusters_config(cwd=cwd)
    auto_cluster_id, auto_reason = _classify_pretool(payload, clusters_all)

    if auto_cluster_id:
        cdef = clusters_all.get(auto_cluster_id, {}) or {}
        gate_enabled = bool(cdef.get("gate", False))
        cluster_skills = cdef.get("skills", []) or []
        gate_reminder_text = cdef.get("gate_reminder", "")

        # Registrar/refrescar cluster activo si tiene gate (para C2)
        if gate_enabled:
            existing = _grace_get_active(session_id, settings_all)
            if not existing or existing.get("cluster") != auto_cluster_id:
                _grace_register_active_cluster(session_id, auto_cluster_id, cluster_skills, settings_all)
                existing = _grace_get_active(session_id, settings_all)

            # ¿La skill que abre el gate ya está invocada recientemente? si sí, dejar pasar.
            already_recent = any(is_recently_invoked(s, state, settings_all.get("dedup_turns", 5)) for s in cluster_skills)
            if already_recent:
                save_state(state)
                write_log({
                    "hook": "PreToolUse",
                    "tool": tool_name,
                    "auto_cluster": auto_cluster_id,
                    "auto_reason": auto_reason,
                    "grace_state": "passthrough_recent_invocation",
                })
                # Aún así inyectar reminder informativo (no bloquea)
                inject_enabled = bool(settings_all.get("context_injection_enabled", True))
                inject_max_chars = int(settings_all.get("context_injection_max_chars_per_skill", 3000))
                reminder, _injected = _build_pretool_reminder(
                    auto_cluster_id, cluster_skills, auto_reason,
                    gate_active=False, gate_reminder=gate_reminder_text,
                    inject_full=inject_enabled, inject_max_chars=inject_max_chars,
                )
                if reminder:
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": reminder,
                            "permissionDecision": "allow",
                        }
                    }
                return {}

            # Bypass `[force-tool]`: NO aplicable a PreToolUse directo (no hay prompt), pero
            # respetamos gate_global_blocks() del gate global (que ya cubre [force-tool] del prompt).
            warnings_far = (existing or {}).get("warnings_issued", 0)

            # Context Injection (17-may-2026): si está enabled, en vez de warning/deny
            # cargamos el SKILL.md de la primera skill del cluster y cerramos el grace.
            inject_enabled = bool(settings_all.get("context_injection_enabled", True))
            if inject_enabled:
                inject_max_chars = int(settings_all.get("context_injection_max_chars_per_skill", 3000))
                inj_block, inj_skills, _failed = _build_injected_skills_block(
                    cluster_skills,
                    max_skills=1,
                    max_chars_per_skill=inject_max_chars,
                )
                if inj_skills:
                    # Cerrar grace (equivalente a invocar Skill del cluster)
                    _grace_clear(session_id)
                    # Marcar global gate como satisfecho por inyección
                    state["turn_skill_invoked"] = True
                    state["turn_auto_satisfied_by_injection"] = True
                    auto_msg_lines = [
                        f"✅ Cluster `{auto_cluster_id}` auto-cargado en contexto (gate satisfecho por Context Injection).",
                        f"Razón: {auto_reason}",
                        "",
                        f"El SKILL.md de `{inj_skills[0]}` ya está en tu contexto, procede con {tool_name} aplicando su protocolo.",
                    ]
                    if gate_reminder_text:
                        auto_msg_lines.append("")
                        auto_msg_lines.append("RECORDATORIO:")
                        for ln in gate_reminder_text.strip().splitlines():
                            auto_msg_lines.append(f"  {ln}")
                    auto_msg_lines.extend(inj_block)
                    save_state(state)
                    write_log({
                        "hook": "PreToolUse",
                        "tool": tool_name,
                        "auto_cluster": auto_cluster_id,
                        "auto_reason": auto_reason,
                        "grace_state": "auto_satisfied_by_injection",
                        "context_injection_applied": True,
                        "skills_injected_full": inj_skills,
                    })
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": "\n".join(auto_msg_lines),
                            "permissionDecision": "allow",
                        }
                    }
                # Si NO se encontró ningún SKILL.md → fallback al flow clásico
                # (warning → deny). Log explicito.
                write_log({
                    "hook": "PreToolUse",
                    "tool": tool_name,
                    "auto_cluster": auto_cluster_id,
                    "grace_state": "injection_fallback_no_skill_files",
                })

            if warnings_far == 0:
                # WARNING + permitir (grace de cortesía)
                _grace_bump_warning(session_id)
                warn_msg = (
                    f"⚠️ Cluster `{auto_cluster_id}` activado por {auto_reason}. "
                    f"Te dejo pasar {tool_name} UNA vez como cortesía.\n\n"
                    f"Invoca a continuación una de estas skills vía la tool Skill: {', '.join('`'+s+'`' for s in cluster_skills)}\n"
                )
                if gate_reminder_text:
                    warn_msg += "\nRECORDATORIO:\n"
                    for ln in gate_reminder_text.strip().splitlines():
                        warn_msg += f"  {ln}\n"
                warn_msg += "\nSi reintentas otra tool sin invocar la skill, te lo BLOQUEARÉ."
                save_state(state)
                write_log({
                    "hook": "PreToolUse",
                    "tool": tool_name,
                    "auto_cluster": auto_cluster_id,
                    "auto_reason": auto_reason,
                    "grace_state": "warning_issued",
                    "warnings_count": 1,
                })
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": warn_msg,
                        "permissionDecision": "allow",
                    }
                }
            else:
                # 2º+ ciclo sin invocar skill DEL CLUSTER → BLOQUEAR.
                # NOTA crítica (fix 17-may-2026): el flag global `state.turn_skill_invoked` NO se
                # consulta aquí. El grace per-session+cluster (existing) ya garantiza que llegamos
                # aquí SOLO si el usuario no invocó una skill del cluster específico (de lo
                # contrario `_grace_clear` lo habría borrado, `existing` sería None y el código
                # volvería a la rama de `register_active_cluster` con counter 0).
                reason = (
                    f"⛔ Cluster `{auto_cluster_id}` requiere invocar una skill antes de {tool_name}.\n"
                    f"Razón: {auto_reason}\n\n"
                    f"Skills del cluster: {', '.join('`'+s+'`' for s in cluster_skills)}\n"
                )
                if gate_reminder_text:
                    reason += "\nRECORDATORIO:\n"
                    for ln in gate_reminder_text.strip().splitlines():
                        reason += f"  {ln}\n"
                reason += "\nBypass de emergencia: añade `[force-tool]` al inicio del próximo prompt del usuario."
                save_state(state)
                write_log({
                    "hook": "PreToolUse",
                    "tool": tool_name,
                    "auto_cluster": auto_cluster_id,
                    "auto_reason": auto_reason,
                    "grace_state": "blocked_after_grace",
                    "warnings_count": warnings_far,
                })
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
        else:
            # Cluster sin gate (suave) → solo sugerir (no bloquear)
            inject_enabled = bool(settings_all.get("context_injection_enabled", True))
            inject_max_chars = int(settings_all.get("context_injection_max_chars_per_skill", 3000))
            reminder, injected_soft = _build_pretool_reminder(
                auto_cluster_id, cluster_skills, auto_reason,
                gate_active=False, gate_reminder=gate_reminder_text,
                inject_full=inject_enabled, inject_max_chars=inject_max_chars,
            )
            # Si inyectamos SKILL.md, marcar auto-satisfecho (global gate)
            if injected_soft:
                state["turn_skill_invoked"] = True
                state["turn_auto_satisfied_by_injection"] = True
            save_state(state)
            write_log({
                "hook": "PreToolUse",
                "tool": tool_name,
                "auto_cluster": auto_cluster_id,
                "auto_reason": auto_reason,
                "grace_state": "soft_suggest",
                "context_injection_applied": bool(injected_soft),
                "skills_injected_full": injected_soft,
            })
            if reminder:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": reminder,
                        "permissionDecision": "allow",
                    }
                }

    # 3) Si tool es bloqueable Y gate global activo → BLOCK (regla CEO 15-may)
    if tool_name in BLOCKABLE_TOOLS and global_gate_blocks(state):
        save_state(state)
        reason = (
            f"⛔ GATE GLOBAL — invoca PRIMERO una Skill (la que sea) antes de usar {tool_name}.\n\n"
            f"Regla CEO 15-may: 'si te mando algo cualquier cosa, activa la puta skill ya está'.\n\n"
            f"Cómo desbloquearte:\n"
            f"  1. Lee el reminder del UserPromptSubmit (skills sugeridas para este prompt)\n"
            f"  2. Invoca cualquier skill relevante vía la tool Skill\n"
            f"  3. Reintenta {tool_name}\n\n"
            f"Si NINGUNA skill aplica realmente, pide al usuario que añada [no-skill] o [force-tool] al inicio del próximo prompt."
        )
        write_log({
            "hook": "PreToolUse",
            "tool": tool_name,
            "global_gate_blocked": True,
        })
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    # 4) Tool no bloqueable o gate ya satisfecho → delegar a V1 (reminders normales)
    save_state(state)

    # Audit V3 (graceful, never raises) — captura PreToolUse para tracking gate+outcome
    if _AUDIT_AVAILABLE:
        try:
            tool_input = payload.get("tool_input") or {}
            _audit_log({
                "session_id": payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "unknown"),
                "hook_event": "PreToolUse",
                "prompt_excerpt": (tool_input.get("command") or tool_input.get("file_path") or "")[:200],
                "cwd": payload.get("cwd") or os.getcwd(),
                "clusters_activated": [],
                "skills_suggested": [],
                "skill_invoked_in_turn": None,
                "tool_name": tool_name,
                "tool_blocked": False,
                "bypass_used": None,
                "outcome": "tool_executed",
            })
        except Exception:
            pass

    if _v1:
        try:
            return _v1.process_hook("PreToolUse", payload, log_only=False)
        except Exception:
            pass
    return {}


def _build_pretool_reminder(
    cluster: str,
    skills: list[str],
    reason: str,
    gate_active: bool,
    gate_reminder: str | None,
    inject_full: bool = False,
    inject_max_chars: int = 3000,
) -> tuple[str, list[str]]:
    """Reminder compacto inyectado en PreToolUse (no bloquea).

    Returns (reminder_text, skills_injected_full).

    Si `inject_full=True`, inyecta el SKILL.md COMPLETO de SOLO la primera
    skill del cluster (a diferencia de UserPromptSubmit donde inyectamos top-N).
    Razón: PreToolUse se dispara MUY a menudo y no queremos saturar el contexto.
    """
    skills_injected_full: list[str] = []
    injected_block: list[str] = []

    if inject_full and skills:
        block, injected, _failed = _build_injected_skills_block(
            skills,
            max_skills=1,  # Solo la primera skill en PreToolUse
            max_chars_per_skill=inject_max_chars,
        )
        injected_block = block
        skills_injected_full = injected

    if skills_injected_full:
        lines = [
            f"✅ CLUSTER AUTO-CARGADO en tool call: `{cluster}`",
            f"Razón: {reason}",
            "",
            "El SKILL.md siguiente ya está en tu contexto, NO necesitas invocar Skill tool.",
            "Aplica el protocolo y procede directo.",
        ]
    else:
        lines = [
            f"CLUSTER AUTODETECTADO en tool call: `{cluster}`",
            f"Razón: {reason}",
            "",
            "Skills sugeridas (invoca vía Skill):",
        ]
    for s in skills:
        note = " (cargada ↓)" if s in skills_injected_full else ""
        lines.append(f"  - `{s}`{note}")
    if gate_reminder:
        lines.append("")
        lines.append("REMINDER OPERATIVO:")
        for ln in gate_reminder.strip().splitlines():
            lines.append(f"  {ln}")
    if injected_block:
        lines.extend(injected_block)
    return "\n".join(lines), skills_injected_full


def cmd_hook(hook_name: str) -> int:
    """Entrada CLI desde hooks de Claude Code."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}

    try:
        if hook_name == "UserPromptSubmit":
            result = process_user_prompt(payload)
        elif hook_name == "PreToolUse":
            result = process_pretool(payload)
        else:
            result = {}
    except Exception as e:
        # Nunca dejar al usuario sin router. Fallback silencioso a V1.
        write_log({"hook": hook_name, "error": str(e), "fallback": "v1"})
        try:
            if _v1:
                result = _v1.process_hook(hook_name, payload, log_only=False)
            else:
                result = {}
        except Exception as e2:
            write_log({"hook": hook_name, "error_fallback": str(e2)})
            result = {}

    if result:
        print(json.dumps(result))
    return 0


def cmd_status() -> int:
    """Muestra estado del router V2."""
    state = load_state()
    clusters, settings, cfg_debug = load_clusters_config(cwd=os.getcwd())
    api_key_present = get_api_key() is not None

    info = {
        "version": "v2",
        "v2_active": should_use_v2(),
        "gemini_api_key_present": api_key_present,
        "clusters_loaded": len(clusters),
        "cluster_names": sorted(clusters.keys()),
        "turn_count": state.get("turn", 0),
        "llm_calls_today": state.get("llm_calls_today", 0),
        "llm_total_calls": state.get("llm_total_calls", 0),
        "llm_total_cost_usd": round(state.get("llm_total_cost_usd", 0.0), 4),
        "settings": settings,
        "config_sources": cfg_debug,
        "grace_state_file": str(GATE_GRACE_FILE),
        "grace_state_present": GATE_GRACE_FILE.exists(),
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(prog="skill-router-v2")
    parser.add_argument("--hook", choices=["UserPromptSubmit", "PreToolUse", "SessionStart"])
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        return cmd_status()
    if args.hook:
        if args.hook == "SessionStart":
            # No hacemos nada especial en SessionStart (V1 rescanea, V2 no necesita)
            return 0
        return cmd_hook(args.hook)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
