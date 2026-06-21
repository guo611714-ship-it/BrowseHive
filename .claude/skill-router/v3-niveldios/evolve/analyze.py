#!/usr/bin/env python3
"""
Skill Router V3 — Analyze (Agent E).

Consume el audit log JSONL (Agent B en `audit/log/YYYY-MM-DD.jsonl`) y los
clusters/skills declarados para detectar:

  1. Ghosts          — skills definidas pero nunca invocadas (>N días)
  2. Cold clusters   — clusters con <umbral activaciones en ventana
  3. Gap queries     — prompts sin cluster match que se repiten (3+ veces)
  4. False positives — clusters cuya skill sugerida NO se invoca (>70%)
  5. Gate friction   — clusters bypassed con [force-tool] (>30%)

Diseño:
- Tolerante a audit log vacío o ausente: devuelve listas vacías (no rompe cron).
- Compatible con Agent C (embeddings) — fallback a RapidFuzz si no instalado.
- 0 side effects. Pure read.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

# ──────────────────────────────────────────────────────────────────────────
# Paths canónicos (overridables vía env para tests)
# ──────────────────────────────────────────────────────────────────────────

ROOT = Path(os.environ.get("SKILL_ROUTER_ROOT", str(Path.home() / ".claude" / "skill-router")))
V3_ROOT = ROOT / "v3-niveldios"
AUDIT_LOG_DIR = Path(os.environ.get("SKILL_ROUTER_AUDIT_LOG_DIR", str(V3_ROOT / "audit" / "log")))
CLUSTERS_YAML = Path(os.environ.get("SKILL_ROUTER_CLUSTERS_YAML", str(ROOT / "v2" / "clusters.yaml")))
SKILLS_DIR = Path(os.environ.get("SKILL_ROUTER_SKILLS_DIR", str(Path.home() / ".claude" / "skills")))

# ──────────────────────────────────────────────────────────────────────────
# Audit log loading
# ──────────────────────────────────────────────────────────────────────────


def _iter_log_files(days: int, log_dir: Path | None = None) -> Iterable[Path]:
    """Itera ficheros JSONL de los últimos N días (ordenados ASC por fecha)."""
    log_dir = log_dir or AUDIT_LOG_DIR
    if not log_dir.exists():
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    files = []
    for f in log_dir.glob("*.jsonl"):
        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d").date()
            if file_date >= cutoff:
                files.append((file_date, f))
        except ValueError:
            continue
    files.sort()
    for _, f in files:
        yield f


def load_audit_entries(days: int = 14, log_dir: Path | None = None) -> list[dict[str, Any]]:
    """Carga todas las entries de audit log de los últimos N días.

    Tolerante a líneas corruptas (skip + stderr warning).
    """
    entries: list[dict[str, Any]] = []
    for f in _iter_log_files(days, log_dir=log_dir):
        try:
            with f.open("r", encoding="utf-8") as fp:
                for ln, line in enumerate(fp, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f"[analyze] WARN: {f.name}:{ln} skip ({e})", file=sys.stderr)
        except OSError as e:
            print(f"[analyze] WARN: cannot read {f}: {e}", file=sys.stderr)
    return entries


# ──────────────────────────────────────────────────────────────────────────
# Skill inventory
# ──────────────────────────────────────────────────────────────────────────


def _load_clusters_yaml(path: Path | None = None) -> dict[str, Any]:
    """Carga clusters.yaml. Si no existe o yaml no instalado, devuelve {}."""
    path = path or CLUSTERS_YAML
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        print("[analyze] WARN: PyYAML no instalado, clusters.yaml no leído", file=sys.stderr)
        return {}
    try:
        with path.open("r", encoding="utf-8") as fp:
            return yaml.safe_load(fp) or {}
    except yaml.YAMLError as e:
        print(f"[analyze] WARN: yaml error {path}: {e}", file=sys.stderr)
        return {}


def get_declared_skills(clusters_yaml_path: Path | None = None) -> set[str]:
    """Skills declaradas en clusters.yaml (todas las que cualquier cluster sugiere)."""
    data = _load_clusters_yaml(clusters_yaml_path)
    declared: set[str] = set()
    for _cid, cdata in (data.get("clusters") or {}).items():
        for sk in cdata.get("skills") or []:
            if isinstance(sk, str):
                declared.add(sk)
            elif isinstance(sk, dict) and sk.get("name"):
                declared.add(sk["name"])
    return declared


def get_installed_skills(skills_dir: Path | None = None) -> set[str]:
    """Skills instaladas en ~/.claude/skills/ (dirs + symlinks)."""
    skills_dir = skills_dir or SKILLS_DIR
    if not skills_dir.exists():
        return set()
    installed: set[str] = set()
    for entry in skills_dir.iterdir():
        if entry.name.startswith("."):
            continue
        # Aceptamos tanto dirs reales como symlinks que apuntan a dirs
        if entry.is_dir() or entry.is_symlink():
            installed.add(entry.name)
    return installed


# ──────────────────────────────────────────────────────────────────────────
# Detectors
# ──────────────────────────────────────────────────────────────────────────


def detect_ghosts(
    audit_log_days: int = 60,
    log_dir: Path | None = None,
    clusters_yaml_path: Path | None = None,
    skills_dir: Path | None = None,
) -> list[str]:
    """Skills declaradas/instaladas con 0 invocaciones en los últimos N días."""
    entries = load_audit_entries(audit_log_days, log_dir=log_dir)
    invoked: Counter[str] = Counter()
    for e in entries:
        sk = e.get("skill_invoked_in_turn")
        if isinstance(sk, str) and sk:
            invoked[sk] += 1
        # también lo que el LLM aceptó vía toolName / hookEvent meta
        for sug in e.get("skills_suggested") or []:
            if isinstance(sug, str):
                pass  # las suggestions NO cuentan como invocación
            elif isinstance(sug, dict) and sug.get("invoked"):
                name = sug.get("name") or sug.get("id")
                if name:
                    invoked[name] += 1

    declared = get_declared_skills(clusters_yaml_path)
    installed = get_installed_skills(skills_dir)
    universe = declared | installed
    ghosts = sorted(s for s in universe if invoked.get(s, 0) == 0)
    return ghosts


def detect_cold_clusters(
    audit_log_days: int = 14,
    min_activations: int = 5,
    log_dir: Path | None = None,
    clusters_yaml_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Clusters con <min_activations en la ventana.

    Solo cuentan activaciones donde el cluster realmente fue *activado*
    (no propuesto-y-descartado por bajo confidence).
    """
    entries = load_audit_entries(audit_log_days, log_dir=log_dir)
    counts: Counter[str] = Counter()
    for e in entries:
        for c in e.get("clusters_activated") or []:
            cid = c.get("id") if isinstance(c, dict) else None
            if cid:
                counts[cid] += 1

    # Universo: todos los clusters declarados en yaml (incluso si nunca activaron)
    yaml_data = _load_clusters_yaml(clusters_yaml_path)
    cluster_ids = list((yaml_data.get("clusters") or {}).keys())

    cold = []
    for cid in cluster_ids:
        n = counts.get(cid, 0)
        if n < min_activations:
            cold.append({"cluster_id": cid, "activations": n, "threshold": min_activations})
    cold.sort(key=lambda x: x["activations"])
    return cold


# ──────── Gap queries (con fallback a RapidFuzz si no hay embeddings) ────


_STOP_WORDS = {
    "el", "la", "los", "las", "de", "del", "en", "y", "a", "que", "es", "un",
    "una", "para", "con", "por", "se", "no", "si", "lo", "al", "the", "of",
    "in", "and", "to", "for", "is", "a", "it", "this", "that", "on",
}


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-záéíóúüñ0-9]{3,}", text)
    return [t for t in tokens if t not in _STOP_WORDS]


def _group_similar_prompts(
    prompts: list[str], similarity_threshold: int = 75
) -> list[tuple[str, list[str]]]:
    """Agrupa prompts similares.

    Intenta usar embeddings de Agent C (si disponible), fallback a RapidFuzz.
    Devuelve lista de tuplas (representative_prompt, [original_prompts]).
    """
    if not prompts:
        return []

    # Intento usar embeddings de Agent C si está
    try:
        from embeddings import group_similar  # type: ignore

        return group_similar(prompts, threshold=similarity_threshold / 100.0)
    except (ImportError, AttributeError):
        pass

    # Fallback: RapidFuzz token_set_ratio
    try:
        from rapidfuzz import fuzz  # type: ignore
    except ImportError:
        # último fallback: dedupe estricto por tokens normalizados
        groups: dict[str, list[str]] = defaultdict(list)
        for p in prompts:
            key = " ".join(sorted(set(_tokenize(p))))
            groups[key].append(p)
        return [(v[0], v) for v in groups.values()]

    groups: list[list[str]] = []
    for p in prompts:
        placed = False
        for g in groups:
            if fuzz.token_set_ratio(p, g[0]) >= similarity_threshold:
                g.append(p)
                placed = True
                break
        if not placed:
            groups.append([p])
    return [(g[0], g) for g in groups]


def detect_gap_queries(
    audit_log_days: int = 14,
    min_repetitions: int = 3,
    log_dir: Path | None = None,
    similarity_threshold: int = 75,
) -> list[dict[str, Any]]:
    """Prompts que NO matchearon ningún cluster y se repiten min_repetitions+."""
    entries = load_audit_entries(audit_log_days, log_dir=log_dir)
    unmatched_prompts: list[str] = []
    for e in entries:
        clusters = e.get("clusters_activated") or []
        prompt = e.get("prompt_excerpt") or ""
        if not clusters and prompt:
            unmatched_prompts.append(prompt.strip())

    grouped = _group_similar_prompts(unmatched_prompts, similarity_threshold=similarity_threshold)
    gaps = []
    for rep, members in grouped:
        if len(members) >= min_repetitions:
            gaps.append(
                {
                    "representative": rep,
                    "occurrences": len(members),
                    "examples": members[:3],
                }
            )
    gaps.sort(key=lambda x: -x["occurrences"])
    return gaps


def detect_false_positive_clusters(
    audit_log_days: int = 7,
    ignore_ratio_threshold: float = 0.7,
    min_suggestions: int = 3,
    log_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Clusters cuya skill sugerida NO es invocada por el LLM >threshold% de veces.

    Para cada (cluster, skill) calcula:
      suggested_n = veces que el cluster propuso la skill
      invoked_n   = veces que tras la sugerencia la skill se invocó en el turno
      ignored_ratio = (suggested_n - invoked_n) / suggested_n

    Filtra cluster+skill con suggested_n >= min_suggestions e ignored_ratio > threshold.
    """
    entries = load_audit_entries(audit_log_days, log_dir=log_dir)
    suggested: Counter[tuple[str, str]] = Counter()
    invoked: Counter[tuple[str, str]] = Counter()

    for e in entries:
        clusters = [c.get("id") for c in (e.get("clusters_activated") or []) if isinstance(c, dict)]
        skills_sug = e.get("skills_suggested") or []
        skill_invoked = e.get("skill_invoked_in_turn")
        if not clusters:
            continue
        # Normalizar skills_suggested (puede ser list[str] o list[dict])
        sug_names: list[str] = []
        for s in skills_sug:
            if isinstance(s, str):
                sug_names.append(s)
            elif isinstance(s, dict):
                name = s.get("name") or s.get("id")
                if name:
                    sug_names.append(name)
        for cid in clusters:
            if not cid:
                continue
            for sk in sug_names:
                suggested[(cid, sk)] += 1
                if skill_invoked == sk:
                    invoked[(cid, sk)] += 1

    fp = []
    for (cid, sk), n_sug in suggested.items():
        if n_sug < min_suggestions:
            continue
        n_inv = invoked.get((cid, sk), 0)
        ignored_ratio = (n_sug - n_inv) / n_sug if n_sug else 0
        if ignored_ratio > ignore_ratio_threshold:
            fp.append(
                {
                    "cluster_id": cid,
                    "skill_suggested": sk,
                    "suggested_count": n_sug,
                    "invoked_count": n_inv,
                    "ignored_ratio": round(ignored_ratio, 2),
                }
            )
    fp.sort(key=lambda x: (-x["ignored_ratio"], -x["suggested_count"]))
    return fp


def detect_gate_friction(
    audit_log_days: int = 7,
    bypass_ratio_threshold: float = 0.3,
    min_activations: int = 3,
    log_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Clusters cuyo gate fue bypassed con [force-tool] >threshold% de veces."""
    entries = load_audit_entries(audit_log_days, log_dir=log_dir)
    total: Counter[str] = Counter()
    bypassed: Counter[str] = Counter()
    for e in entries:
        clusters = e.get("clusters_activated") or []
        bypass = e.get("bypass_used")
        for c in clusters:
            cid = c.get("id") if isinstance(c, dict) else None
            if not cid:
                continue
            total[cid] += 1
            if bypass:
                bypassed[cid] += 1

    friction = []
    for cid, n_total in total.items():
        if n_total < min_activations:
            continue
        n_bp = bypassed.get(cid, 0)
        ratio = n_bp / n_total if n_total else 0
        if ratio > bypass_ratio_threshold:
            friction.append(
                {
                    "cluster_id": cid,
                    "total_activations": n_total,
                    "bypassed_count": n_bp,
                    "bypass_ratio": round(ratio, 2),
                }
            )
    friction.sort(key=lambda x: (-x["bypass_ratio"], -x["total_activations"]))
    return friction


# ──────────────────────────────────────────────────────────────────────────
# CLI debug
# ──────────────────────────────────────────────────────────────────────────


def _summary(days: int = 14) -> dict[str, Any]:
    return {
        "ghosts": detect_ghosts(audit_log_days=max(days * 2, 60)),
        "cold_clusters": detect_cold_clusters(audit_log_days=days),
        "gap_queries": detect_gap_queries(audit_log_days=days),
        "false_positives": detect_false_positive_clusters(audit_log_days=max(days // 2, 7)),
        "gate_friction": detect_gate_friction(audit_log_days=max(days // 2, 7)),
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Skill router evolve analyze")
    p.add_argument("--days", type=int, default=14)
    args = p.parse_args()
    print(json.dumps(_summary(args.days), indent=2, ensure_ascii=False))
