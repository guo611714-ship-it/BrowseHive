"""Audit log JSONL reader + stats aggregator.

Lee de `~/.claude/skill-router/v3-niveldios/audit/log/YYYY-MM-DD.jsonl`.

Tolerante a:
- Log dir vacío (no entries)
- Líneas JSON inválidas (skip)
- Ts mal formado (incluye igualmente para no perder data)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def load_entries(days: int = 7, session_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """Carga entries JSONL filtradas por ventana de días y opcionalmente session."""
    log_dir = config.AUDIT_LOG_DIR
    if not log_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: list[dict[str, Any]] = []

    for path in sorted(log_dir.glob("*.jsonl")):
        try:
            stem_dt = datetime.strptime(path.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            # Margen de 1 día parcial
            if stem_dt < cutoff - timedelta(days=1):
                continue
        except ValueError:
            continue

        try:
            with path.open(encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts_dt = _parse_ts(entry.get("ts", ""))
                    if ts_dt and ts_dt < cutoff:
                        continue
                    if session_id and entry.get("session_id") != session_id:
                        continue
                    out.append(entry)
        except OSError:
            continue

    # Más recientes primero
    out.sort(key=lambda e: e.get("ts", ""), reverse=True)
    if limit:
        return out[:limit]
    return out


def summary(days: int = 7) -> dict[str, Any]:
    entries = load_entries(days)
    total = len(entries)
    ups = [e for e in entries if e.get("hook_event") == "UserPromptSubmit"]
    ups_with_cluster = [e for e in ups if e.get("clusters_activated")]
    hit_rate = (len(ups_with_cluster) / len(ups)) if ups else 0.0

    cluster_counter: Counter[str] = Counter()
    for e in entries:
        for c in e.get("clusters_activated") or []:
            cluster_counter[c.get("id", "?")] += 1

    skill_counter: Counter[str] = Counter()
    for e in entries:
        for s in e.get("skills_suggested") or []:
            skill_counter[s] += 1

    invoked_counter: Counter[str] = Counter()
    for e in entries:
        sk = e.get("skill_invoked_in_turn")
        if sk:
            invoked_counter[sk] += 1

    suggested_set = set(skill_counter.keys())
    invoked_set = set(invoked_counter.keys())
    ghosts = suggested_set - invoked_set

    bypass_counter: Counter[str] = Counter()
    for e in entries:
        b = e.get("bypass_used")
        if b:
            bypass_counter[b] += 1

    return {
        "days": days,
        "total_events": total,
        "user_prompts": len(ups),
        "hit_rate": round(hit_rate, 3),
        "ghost_count": len(ghosts),
        "top_clusters": cluster_counter.most_common(10),
        "top_skills_suggested": skill_counter.most_common(10),
        "top_skills_invoked": invoked_counter.most_common(10),
        "bypass_usage": bypass_counter.most_common(),
        "blocked_tools": sum(1 for e in entries if e.get("tool_blocked")),
    }


def cluster_stats(days: int = 7) -> list[dict[str, Any]]:
    entries = load_entries(days)
    activations: dict[str, int] = defaultdict(int)
    skills_sug_per: dict[str, set] = defaultdict(set)
    skills_inv_per: dict[str, set] = defaultdict(set)
    last_seen: dict[str, str] = {}

    for e in entries:
        invoked = e.get("skill_invoked_in_turn")
        for c in e.get("clusters_activated") or []:
            cid = c.get("id", "?")
            activations[cid] += 1
            if cid not in last_seen and e.get("ts"):
                last_seen[cid] = e["ts"]
            for s in e.get("skills_suggested") or []:
                skills_sug_per[cid].add(s)
            if invoked:
                skills_inv_per[cid].add(invoked)

    rows: list[dict[str, Any]] = []
    for cid, n in activations.items():
        sug = len(skills_sug_per[cid])
        inv = len(skills_inv_per[cid] & skills_sug_per[cid])
        rate = (inv / sug) if sug else 0.0
        rows.append({
            "cluster_id": cid,
            "activations": n,
            "skills_suggested": sug,
            "skills_invoked": inv,
            "invoke_rate": round(rate, 3),
            "last_seen": last_seen.get(cid, ""),
        })
    rows.sort(key=lambda r: -r["activations"])
    return rows


def skill_stats(days: int = 30) -> list[dict[str, Any]]:
    entries = load_entries(days)
    suggested: Counter[str] = Counter()
    invoked: Counter[str] = Counter()
    for e in entries:
        for s in e.get("skills_suggested") or []:
            suggested[s] += 1
        sk = e.get("skill_invoked_in_turn")
        if sk:
            invoked[sk] += 1

    rows: list[dict[str, Any]] = []
    for s in set(suggested.keys()) | set(invoked.keys()):
        sug = suggested[s]
        inv = invoked[s]
        ratio = (inv / sug) if sug else 0.0
        ghost = (sug > 3 and inv == 0)
        rows.append({
            "skill": s,
            "suggested": sug,
            "invoked": inv,
            "ratio": round(ratio, 3),
            "ghost": ghost,
        })
    rows.sort(key=lambda r: (-r["suggested"], r["skill"]))
    return rows


def gaps(days: int = 14, limit: int = 50) -> dict[str, Any]:
    entries = load_entries(days)
    ups = [e for e in entries if e.get("hook_event") == "UserPromptSubmit"]
    no_cluster = [e for e in ups if not (e.get("clusters_activated") or [])]
    excerpts = []
    for e in no_cluster[:limit]:
        excerpts.append({
            "ts": e.get("ts", "")[:19],
            "excerpt": (e.get("prompt_excerpt") or "")[:200],
            "cwd": e.get("cwd", "")[:80],
        })
    rate = 1 - (len(no_cluster) / len(ups)) if ups else 0.0
    return {
        "total_prompts": len(ups),
        "missing_cluster": len(no_cluster),
        "hit_rate": round(rate, 3),
        "samples": excerpts,
    }


def daily_activations(days: int = 14) -> list[dict[str, Any]]:
    """Serie temporal de activaciones de cluster por día."""
    entries = load_entries(days)
    by_day: dict[str, int] = defaultdict(int)
    for e in entries:
        ts = e.get("ts", "")[:10]
        if not ts:
            continue
        if e.get("clusters_activated"):
            by_day[ts] += 1
    series = sorted(by_day.items())
    return [{"date": d, "count": n} for d, n in series]


def last_event_ts() -> str | None:
    """Timestamp del último evento registrado (para health)."""
    entries = load_entries(days=30, limit=1)
    if not entries:
        return None
    return entries[0].get("ts")
