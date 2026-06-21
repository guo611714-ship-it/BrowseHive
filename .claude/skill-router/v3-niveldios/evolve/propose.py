#!/usr/bin/env python3
"""
Skill Router V3 — Propose (Agent E).

Genera report markdown con propuestas concretas a partir de la salida de
`analyze.py`. Persiste en `reports/YYYY-WNN.md` y opcionalmente envía
resumen por Telegram.

CLI:
    python propose.py --days 14 [--dry-run] [--send-telegram]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Permite import relativo cuando se ejecuta como script
sys.path.insert(0, str(Path(__file__).parent))

from analyze import (  # noqa: E402
    detect_cold_clusters,
    detect_false_positive_clusters,
    detect_gap_queries,
    detect_gate_friction,
    detect_ghosts,
)

V3_ROOT = Path(__file__).parent.parent
REPORTS_DIR = Path(os.environ.get("SKILL_ROUTER_EVOLVE_REPORTS", str(Path(__file__).parent / "reports")))


# ──────────────────────────────────────────────────────────────────────────
# Report rendering
# ──────────────────────────────────────────────────────────────────────────


def _iso_week(now: datetime | None = None) -> tuple[int, int]:
    now = now or datetime.now(timezone.utc)
    iso = now.isocalendar()
    return iso.year, iso.week


def render_report(
    days: int = 14,
    now: datetime | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    """Genera markdown del report semanal."""
    now = now or datetime.now(timezone.utc)
    year, week = _iso_week(now)

    if data is None:
        data = {
            "ghosts": detect_ghosts(audit_log_days=max(days * 4, 60)),
            "cold_clusters": detect_cold_clusters(audit_log_days=days),
            "gap_queries": detect_gap_queries(audit_log_days=days),
            "false_positives": detect_false_positive_clusters(audit_log_days=max(days // 2, 7)),
            "gate_friction": detect_gate_friction(audit_log_days=max(days // 2, 7)),
        }

    ghosts: list[str] = data.get("ghosts", []) or []
    cold: list[dict] = data.get("cold_clusters", []) or []
    gaps: list[dict] = data.get("gap_queries", []) or []
    fp: list[dict] = data.get("false_positives", []) or []
    friction: list[dict] = data.get("gate_friction", []) or []

    lines: list[str] = []
    lines.append(f"# Router Evolution Report — Semana {week:02d} del {year}")
    lines.append("")
    lines.append(f"_Ventana de análisis: últimos {days} días · generado {now.strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")
    lines.append(
        f"**Resumen:** {len(ghosts)} ghosts · {len(cold)} cold clusters · "
        f"{len(gaps)} gap queries · {len(fp)} false positives · {len(friction)} con gate friction"
    )
    lines.append("")

    # ── Ghosts ─────────────────────────────────────────────────────────
    lines.append("## Ghosts (skills nunca invocadas)")
    lines.append("")
    if not ghosts:
        lines.append("_Sin ghosts._")
    else:
        for sk in ghosts[:30]:
            lines.append(
                f"- `{sk}` → propuesta: REMOVE del cluster que la sugiere, "
                f"o DEPRECATE si no se usa en ningún sitio."
            )
        if len(ghosts) > 30:
            lines.append(f"- _… y {len(ghosts) - 30} ghosts más (truncado)._")
    lines.append("")

    # ── Cold clusters ──────────────────────────────────────────────────
    lines.append("## Cold clusters (pocas activaciones)")
    lines.append("")
    if not cold:
        lines.append("_Sin clusters fríos._")
    else:
        for c in cold[:20]:
            lines.append(
                f"- `{c['cluster_id']}` ({c['activations']} activaciones, "
                f"umbral {c['threshold']}) → propuesta: MERGE con cluster afín "
                f"o REVISAR keywords/triggers."
            )
        if len(cold) > 20:
            lines.append(f"- _… y {len(cold) - 20} clusters fríos más._")
    lines.append("")

    # ── Gap queries ────────────────────────────────────────────────────
    lines.append("## Gap queries (prompts sin cluster, repetidos 3+ veces)")
    lines.append("")
    if not gaps:
        lines.append("_Sin gaps detectados._")
    else:
        for g in gaps[:15]:
            rep = (g["representative"] or "").replace("\n", " ").strip()
            if len(rep) > 120:
                rep = rep[:117] + "..."
            lines.append(
                f"- _\"{rep}\"_ ({g['occurrences']} ocurrencias) → propuesta: "
                f"NUEVO cluster con keywords + skills asociadas."
            )
        if len(gaps) > 15:
            lines.append(f"- _… y {len(gaps) - 15} gaps más._")
    lines.append("")

    # ── False positives ────────────────────────────────────────────────
    lines.append("## False positive clusters (skill sugerida ignorada >70%)")
    lines.append("")
    if not fp:
        lines.append("_Sin false positives._")
    else:
        for f in fp[:20]:
            lines.append(
                f"- `{f['cluster_id']}` → skill `{f['skill_suggested']}` "
                f"sugerida {f['suggested_count']} veces, invocada {f['invoked_count']} "
                f"({int(f['ignored_ratio'] * 100)}% ignorada). "
                f"Propuesta: cambiar skill o re-tunear trigger."
            )
        if len(fp) > 20:
            lines.append(f"- _… y {len(fp) - 20} false positives más._")
    lines.append("")

    # ── Gate friction ──────────────────────────────────────────────────
    lines.append("## Gate friction ([force-tool] bypass >30%)")
    lines.append("")
    if not friction:
        lines.append("_Sin gate friction._")
    else:
        for f in friction[:20]:
            lines.append(
                f"- `{f['cluster_id']}` bypassed {f['bypassed_count']}/"
                f"{f['total_activations']} veces ({int(f['bypass_ratio'] * 100)}%). "
                f"Propuesta: bajar gate a `false` (sugerencia) o revisar trigger."
            )
        if len(friction) > 20:
            lines.append(f"- _… y {len(friction) - 20} con friction más._")
    lines.append("")

    # ── Acciones recomendadas ──────────────────────────────────────────
    lines.append("## Acciones recomendadas (orden prioridad)")
    lines.append("")
    actions = _build_action_list(ghosts, cold, gaps, fp, friction)
    if not actions:
        lines.append("_Sin acciones recomendadas esta semana._")
    else:
        for i, a in enumerate(actions, 1):
            lines.append(f"{i}. {a}")
    lines.append("")

    lines.append("---")
    lines.append("_Generado por evolve/propose.py (Agent E · Skill Router V3 nivel dios)._")
    return "\n".join(lines)


def _build_action_list(
    ghosts: list[str],
    cold: list[dict],
    gaps: list[dict],
    fp: list[dict],
    friction: list[dict],
) -> list[str]:
    actions: list[str] = []
    if gaps:
        top = gaps[0]
        rep = (top["representative"] or "")[:60]
        actions.append(
            f"Crear cluster nuevo para gap query `{rep}…` ({top['occurrences']} ocurrencias) — alto impacto."
        )
    if fp:
        top = fp[0]
        actions.append(
            f"Revisar cluster `{top['cluster_id']}` (skill `{top['skill_suggested']}` "
            f"ignorada {int(top['ignored_ratio'] * 100)}% de veces)."
        )
    if friction:
        top = friction[0]
        actions.append(
            f"Bajar gate de `{top['cluster_id']}` o simplificar regla (bypass "
            f"{int(top['bypass_ratio'] * 100)}%)."
        )
    if cold:
        top = cold[0]
        actions.append(
            f"Mergear/eliminar cluster `{top['cluster_id']}` ({top['activations']} activaciones)."
        )
    if ghosts:
        actions.append(
            f"Deprecar {len(ghosts)} skills ghost (revisar lista) o moverlas a cluster vivo."
        )
    return actions


# ──────────────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────────────


def persist_report(markdown: str, now: datetime | None = None, reports_dir: Path | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    year, week = _iso_week(now)
    reports_dir = reports_dir or REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / f"{year}-W{week:02d}.md"
    out.write_text(markdown, encoding="utf-8")
    return out


# ──────────────────────────────────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────────────────────────────────


def _telegram_summary(markdown: str, max_chars: int = 3800) -> str:
    """Recorta el report a un resumen Telegram-friendly (4096 char limit)."""
    if len(markdown) <= max_chars:
        return markdown
    # Coge cabecera + Resumen + secciones recortadas
    lines = markdown.splitlines()
    out: list[str] = []
    size = 0
    for ln in lines:
        if size + len(ln) + 1 > max_chars:
            out.append("…")
            break
        out.append(ln)
        size += len(ln) + 1
    return "\n".join(out)


def send_telegram(
    text: str,
    bot_token: str | None = None,
    chat_id: str | None = None,
    *,
    timeout: float = 10.0,
    transport=None,
) -> dict[str, Any]:
    """Envía un mensaje Telegram. Devuelve dict con `ok`, `status`, `error`.

    `transport`: callable opcional para tests (signature: (url, data) -> dict).
    Si no se pasa, usa urllib.
    """
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("OPENCLAW_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID") or "662454777"
    if not bot_token:
        return {"ok": False, "error": "no_bot_token", "status": 0}

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": _telegram_summary(text),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    if transport is not None:
        try:
            result = transport(url, payload)
            return {"ok": bool(result.get("ok")), "status": 200, "raw": result}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "status": 0}

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "raw": json.loads(body)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": e.reason}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return {"ok": False, "status": 0, "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Skill router evolve propose")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true", help="No persist, no telegram, print stdout")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--no-persist", action="store_true", help="Skip writing report file")
    args = parser.parse_args(argv)

    md = render_report(days=args.days)

    if args.dry_run:
        print(md)
        return 0

    if not args.no_persist:
        out = persist_report(md)
        print(f"[evolve] report → {out}", file=sys.stderr)

    if args.send_telegram:
        result = send_telegram(md)
        if not result["ok"]:
            print(f"[evolve] telegram ERROR: {result.get('error')}", file=sys.stderr)
            return 1
        print(f"[evolve] telegram ok status={result['status']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
