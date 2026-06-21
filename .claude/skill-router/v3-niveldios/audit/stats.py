#!/usr/bin/env python3
"""
Skill Router V3 — Audit Stats CLI.

Subcomandos:
    router-stats summary [--days 7]
    router-stats clusters [--days 7]
    router-stats skills [--days 30]
    router-stats gaps [--days 14]
    router-stats gate [--days 7]

Output: tablas ASCII con colores (verde/amarillo/rojo) por threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

AUDIT_DIR = Path(__file__).parent
LOG_DIR = AUDIT_DIR / "log"

# ANSI colors (degradan a vacío si NO_COLOR o no TTY)
_USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
GREEN = "\033[32m" if _USE_COLOR else ""
YELLOW = "\033[33m" if _USE_COLOR else ""
RED = "\033[31m" if _USE_COLOR else ""
BOLD = "\033[1m" if _USE_COLOR else ""
RESET = "\033[0m" if _USE_COLOR else ""


def _color_pct(value: float, healthy: float = 0.7, warning: float = 0.4) -> str:
    """Colorea un % según threshold."""
    if value >= healthy:
        return f"{GREEN}{value*100:.1f}%{RESET}"
    if value >= warning:
        return f"{YELLOW}{value*100:.1f}%{RESET}"
    return f"{RED}{value*100:.1f}%{RESET}"


def _color_count(value: int, healthy_max: int = 5, warning_max: int = 20) -> str:
    """Colorea un contador (más bajo = mejor en ghost detection)."""
    if value <= healthy_max:
        return f"{GREEN}{value}{RESET}"
    if value <= warning_max:
        return f"{YELLOW}{value}{RESET}"
    return f"{RED}{value}{RESET}"


def _load_entries(days: int) -> list[dict]:
    """Carga entries JSONL de últimos N días."""
    if not LOG_DIR.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries: list[dict] = []
    for f in sorted(LOG_DIR.glob("*.jsonl")):
        try:
            dt = datetime.strptime(f.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if dt < cutoff - timedelta(days=1):  # margen de día parcial
                continue
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except ValueError:
            continue
    # Filter por ts real
    out = []
    for e in entries:
        ts = e.get("ts", "")
        try:
            ts_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if ts_dt >= cutoff:
                out.append(e)
        except (ValueError, TypeError):
            out.append(e)  # incluir si ts mal formado para no perder data
    return out


def _table(rows: list[list[str]], headers: list[str]) -> str:
    """ASCII table simple sin dependencias."""
    if not rows:
        return "  (sin datos)"
    # Strip ANSI para calcular ancho
    import re
    ansi = re.compile(r"\033\[[0-9;]*m")
    def visible_len(s: str) -> int:
        return len(ansi.sub("", str(s)))
    cols = list(zip(headers, *rows))
    widths = [max(visible_len(c) for c in col) for col in cols]
    sep = "  "
    def fmt_row(r):
        parts = []
        for i, cell in enumerate(r):
            pad = widths[i] - visible_len(cell)
            parts.append(str(cell) + " " * pad)
        return sep.join(parts)
    lines = [fmt_row(headers), fmt_row(["-" * w for w in widths])]
    for r in rows:
        lines.append(fmt_row(r))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Subcomandos
# ─────────────────────────────────────────────────────────────────────

def cmd_summary(args) -> int:
    entries = _load_entries(args.days)
    total = len(entries)
    if total == 0:
        print(f"{YELLOW}Sin datos en últimos {args.days} días.{RESET}")
        return 0

    # Hit rate: % de entries UserPromptSubmit con al menos 1 cluster activado
    ups = [e for e in entries if e.get("hook_event") == "UserPromptSubmit"]
    ups_with_cluster = [e for e in ups if e.get("clusters_activated")]
    hit_rate = len(ups_with_cluster) / len(ups) if ups else 0.0

    # Top clusters
    cluster_counter = Counter()
    for e in entries:
        for c in e.get("clusters_activated", []) or []:
            cluster_counter[c.get("id", "?")] += 1
    top_clusters = cluster_counter.most_common(5)

    # Top skills sugeridas
    skill_counter = Counter()
    for e in entries:
        for s in e.get("skills_suggested", []) or []:
            skill_counter[s] += 1
    top_skills = skill_counter.most_common(5)

    # Ghost skills: sugeridas pero nunca invocadas
    suggested_set = set(skill_counter.keys())
    invoked_set = {e.get("skill_invoked_in_turn") for e in entries if e.get("skill_invoked_in_turn")}
    ghosts = suggested_set - invoked_set

    # Bypass usage
    bypass_counter = Counter()
    for e in entries:
        b = e.get("bypass_used")
        if b:
            bypass_counter[b] += 1

    print(f"{BOLD}=== Router Stats — Summary (últimos {args.days}d) ==={RESET}")
    print(f"Total events: {total}  ·  UserPromptSubmit: {len(ups)}")
    print(f"Hit-rate (cluster activado): {_color_pct(hit_rate)}")
    print(f"Ghost skills (sugeridas, 0 invocaciones): {_color_count(len(ghosts), 3, 10)}")
    print()
    print(f"{BOLD}Top clusters activados:{RESET}")
    print(_table([[c, str(n)] for c, n in top_clusters], ["cluster", "n"]))
    print()
    print(f"{BOLD}Top skills sugeridas:{RESET}")
    print(_table([[s, str(n)] for s, n in top_skills], ["skill", "n"]))
    print()
    if bypass_counter:
        print(f"{BOLD}Bypass usage:{RESET}")
        print(_table([[b, str(n)] for b, n in bypass_counter.most_common()], ["bypass", "n"]))
    return 0


def cmd_clusters(args) -> int:
    entries = _load_entries(args.days)
    if not entries:
        print(f"{YELLOW}Sin datos en últimos {args.days} días.{RESET}")
        return 0

    activations: dict[str, int] = defaultdict(int)
    skills_per_cluster: dict[str, set] = defaultdict(set)
    invoked_per_cluster: dict[str, set] = defaultdict(set)

    for e in entries:
        invoked = e.get("skill_invoked_in_turn")
        for c in e.get("clusters_activated", []) or []:
            cid = c.get("id", "?")
            activations[cid] += 1
            for s in e.get("skills_suggested", []) or []:
                skills_per_cluster[cid].add(s)
            if invoked:
                invoked_per_cluster[cid].add(invoked)

    rows = []
    for cid, n in sorted(activations.items(), key=lambda x: -x[1]):
        suggested = len(skills_per_cluster[cid])
        invoked = len(invoked_per_cluster[cid] & skills_per_cluster[cid])
        ratio = invoked / suggested if suggested else 0.0
        fp_rate = 1.0 - ratio  # false positive proxy
        rows.append([
            cid,
            str(n),
            str(suggested),
            str(invoked),
            _color_pct(ratio, 0.5, 0.2),
            _color_pct(fp_rate, 0.0, 0.5) if fp_rate > 0.5 else f"{fp_rate*100:.1f}%",
        ])

    print(f"{BOLD}=== Router Stats — Clusters (últimos {args.days}d) ==={RESET}")
    print(_table(rows, ["cluster", "activations", "skills_sug", "skills_inv", "invoke_rate", "false_pos"]))
    return 0


def cmd_skills(args) -> int:
    entries = _load_entries(args.days)
    if not entries:
        print(f"{YELLOW}Sin datos en últimos {args.days} días.{RESET}")
        return 0

    suggested = Counter()
    invoked = Counter()
    for e in entries:
        for s in e.get("skills_suggested", []) or []:
            suggested[s] += 1
        if e.get("skill_invoked_in_turn"):
            invoked[e["skill_invoked_in_turn"]] += 1

    rows = []
    all_skills = set(suggested.keys()) | set(invoked.keys())
    for s in sorted(all_skills, key=lambda x: -suggested.get(x, 0)):
        sug = suggested.get(s, 0)
        inv = invoked.get(s, 0)
        ratio = inv / sug if sug else 0.0
        ghost = "GHOST" if (sug > 3 and inv == 0) else ""
        rows.append([
            s[:50],
            str(sug),
            str(inv),
            _color_pct(ratio, 0.3, 0.1),
            f"{RED}{ghost}{RESET}" if ghost else "",
        ])

    print(f"{BOLD}=== Router Stats — Skills (últimos {args.days}d) ==={RESET}")
    print(_table(rows, ["skill", "suggested", "invoked", "ratio", "flag"]))
    return 0


def cmd_gaps(args) -> int:
    entries = _load_entries(args.days)
    ups = [e for e in entries if e.get("hook_event") == "UserPromptSubmit"]
    if not ups:
        print(f"{YELLOW}Sin UserPromptSubmit en últimos {args.days} días.{RESET}")
        return 0

    no_cluster = [e for e in ups if not (e.get("clusters_activated") or [])]
    print(f"{BOLD}=== Router Stats — Gaps (últimos {args.days}d) ==={RESET}")
    print(f"Prompts sin cluster: {len(no_cluster)} de {len(ups)} ({_color_pct(1 - len(no_cluster)/len(ups), 0.7, 0.4)} hit)")
    print()

    if not no_cluster:
        return 0

    # Top excerpts representativos
    print(f"{BOLD}Sample prompts sin cluster (top 20):{RESET}")
    for e in no_cluster[:20]:
        excerpt = e.get("prompt_excerpt", "")[:120]
        ts = e.get("ts", "")[:10]
        print(f"  [{ts}] {excerpt}")
    if len(no_cluster) > 20:
        print(f"  ... y {len(no_cluster) - 20} más")
    return 0


def cmd_gate(args) -> int:
    entries = _load_entries(args.days)
    if not entries:
        print(f"{YELLOW}Sin datos en últimos {args.days} días.{RESET}")
        return 0

    blocked = sum(1 for e in entries if e.get("tool_blocked"))
    bypass_counter = Counter()
    for e in entries:
        b = e.get("bypass_used")
        if b:
            bypass_counter[b] += 1

    outcomes = Counter(e.get("outcome", "") for e in entries if e.get("outcome"))

    print(f"{BOLD}=== Router Stats — Gate (últimos {args.days}d) ==={RESET}")
    print(f"Tool blocked count: {_color_count(blocked, 5, 30)}")
    print(f"Total events: {len(entries)}")
    print()
    if bypass_counter:
        print(f"{BOLD}Bypass usage:{RESET}")
        print(_table([[b, str(n)] for b, n in bypass_counter.most_common()], ["bypass", "n"]))
        print()
    if outcomes:
        print(f"{BOLD}Outcomes:{RESET}")
        print(_table([[o, str(n)] for o, n in outcomes.most_common()], ["outcome", "n"]))
    return 0


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="router-stats", description="Skill Router audit stats.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sum = sub.add_parser("summary", help="Resumen general")
    p_sum.add_argument("--days", type=int, default=7)
    p_sum.set_defaults(func=cmd_summary)

    p_cl = sub.add_parser("clusters", help="Stats por cluster")
    p_cl.add_argument("--days", type=int, default=7)
    p_cl.set_defaults(func=cmd_clusters)

    p_sk = sub.add_parser("skills", help="Stats por skill (ghost detection)")
    p_sk.add_argument("--days", type=int, default=30)
    p_sk.set_defaults(func=cmd_skills)

    p_gp = sub.add_parser("gaps", help="Prompts sin cluster (nuevos cluster candidates)")
    p_gp.add_argument("--days", type=int, default=14)
    p_gp.set_defaults(func=cmd_gaps)

    p_gt = sub.add_parser("gate", help="Gate stats (blocks, bypass, warnings)")
    p_gt.add_argument("--days", type=int, default=7)
    p_gt.set_defaults(func=cmd_gate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
