#!/usr/bin/env python3
"""
Skill Router V3 — Audit Logger.

Logger append-only JSONL con rotación diaria + retención 90 días.

Integración:
    from logger import log_decision
    log_decision({...})

Diseño:
- 1 fichero por día: log/YYYY-MM-DD.jsonl
- Append atómico con fcntl.LOCK_EX (POSIX) para concurrencia segura
- Retención 90 días: borra logs >90d en cada write (cheap, idempotente)
- Tolerante a fallos: si write falla, log error a stderr + NO bloquea hook
- PII safety: prompt_excerpt max 200 chars + scrub tokens visibles
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

AUDIT_DIR = Path(__file__).parent
LOG_DIR = AUDIT_DIR / "log"
RETENTION_DAYS = 90
MAX_PROMPT_EXCERPT = 200

# Regex para scrub PII visible (tokens, bearer, api keys, jwt, sk-*, ghp_*, vcp_*)
# Nota: usamos clases que aceptan guiones para cubrir formatos tipo `sk-secret-VISIBLE-1000`,
# no solo strings hex puros. El umbral baja a 10+ chars tras el prefijo para mejor recall.
_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}", re.IGNORECASE),
    re.compile(r"\bghp_[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bvcp_[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-.=]+", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|apikey)[\"'\s:=]+[\"']?[A-Za-z0-9_\-]{12,}", re.IGNORECASE),
    re.compile(r"\bey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),  # JWT
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"),  # Google API keys
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]+"),  # Slack tokens
    re.compile(r"\b(?:token|secret|password|passwd|pwd)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
]


def _scrub(text: str) -> str:
    """Sustituye secretos por [REDACTED]."""
    if not text:
        return text
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _truncate_excerpt(prompt: str, limit: int = MAX_PROMPT_EXCERPT) -> str:
    """Truncate + scrub para privacy."""
    if not prompt:
        return ""
    s = str(prompt)
    if len(s) > limit:
        s = s[:limit] + "..."
    return _scrub(s)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%d")


def _log_path(now: datetime | None = None) -> Path:
    return LOG_DIR / f"{_today_str(now)}.jsonl"


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _prune_old_logs(retention_days: int = RETENTION_DAYS) -> int:
    """Borra logs >retention_days. Retorna # borrados. Idempotente y barato."""
    if not LOG_DIR.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0
    for f in LOG_DIR.glob("*.jsonl"):
        try:
            # Parse fecha del nombre
            stem = f.stem  # YYYY-MM-DD
            dt = datetime.strptime(stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if dt < cutoff:
                f.unlink()
                deleted += 1
        except (ValueError, OSError):
            continue
    return deleted


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normaliza payload + scrub PII. Mutación: NO (crea copia)."""
    out = dict(payload)
    out.setdefault("ts", _now_utc_iso())
    out.setdefault("session_id", "")
    out.setdefault("hook_event", "")
    out.setdefault("cwd", "")
    out.setdefault("clusters_activated", [])
    out.setdefault("skills_suggested", [])
    out.setdefault("skill_invoked_in_turn", None)
    out.setdefault("tool_name", None)
    out.setdefault("tool_blocked", False)
    out.setdefault("bypass_used", None)
    out.setdefault("outcome", "")

    # Sanitize prompt_excerpt
    if "prompt_excerpt" in out:
        out["prompt_excerpt"] = _truncate_excerpt(out["prompt_excerpt"])
    else:
        out["prompt_excerpt"] = ""

    return out


def log_decision(payload: dict[str, Any], _now: datetime | None = None) -> bool:
    """
    Append payload a log JSONL del día. Idempotente, atómico, fail-safe.

    Args:
        payload: dict con campos del schema (ver INTERFACE.md).
        _now: datetime override para tests (inyección).

    Returns:
        bool: True si escribió OK, False si falló (NO lanza).
    """
    try:
        _ensure_log_dir()
        normalized = _normalize_payload(payload)
        path = _log_path(_now)
        line = json.dumps(normalized, ensure_ascii=False) + "\n"

        # Append atómico con file lock (POSIX)
        with path.open("a", encoding="utf-8") as fh:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                fh.write(line)
                fh.flush()
            finally:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass

        # Prune cheap (1 dir scan, no IO si nada que borrar)
        try:
            _prune_old_logs()
        except Exception as exc:
            print(f"[audit-logger] prune warning: {exc}", file=sys.stderr)

        return True
    except Exception as exc:
        # Fail-safe: NO bloqueamos al hook
        print(f"[audit-logger] write failed: {exc}", file=sys.stderr)
        return False


if __name__ == "__main__":
    # Smoke test rápido
    ok = log_decision({
        "session_id": "smoke-test",
        "hook_event": "UserPromptSubmit",
        "prompt_excerpt": "test prompt with sk-fake-secret-1234567890abcdef inside",
        "cwd": str(Path.cwd()),
        "clusters_activated": [{"id": "marketing", "confidence": 0.9, "trigger": "keyword"}],
        "skills_suggested": ["copywriting"],
        "outcome": "tool_executed",
    })
    print(f"smoke test: {'OK' if ok else 'FAIL'}")
    print(f"log path: {_log_path()}")
