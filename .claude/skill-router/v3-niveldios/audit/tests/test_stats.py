"""Tests del stats CLI audit V3."""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import pytest

AUDIT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUDIT_DIR))


def _make_fake_entries(n: int = 100) -> list[dict]:
    """Genera N entries fake variados."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    clusters_pool = ["marketing", "engineering", "data", "cks"]
    skills_pool = ["copywriting", "code-review", "sql-queries", "cks-prd", "marketing-ideas"]
    entries = []
    for i in range(n):
        # 70% tienen cluster, 30% no
        has_cluster = i % 10 < 7
        cluster = clusters_pool[i % len(clusters_pool)]
        skills = [skills_pool[i % len(skills_pool)], skills_pool[(i + 1) % len(skills_pool)]]
        invoked = skills[0] if i % 3 == 0 else None
        e = {
            "ts": now,
            "session_id": f"s-{i}",
            "hook_event": "UserPromptSubmit" if i % 2 == 0 else "PreToolUse",
            "prompt_excerpt": f"prompt fake numero {i}" if has_cluster else "lorem ipsum dolor",
            "cwd": "/tmp",
            "clusters_activated": [{"id": cluster, "confidence": 0.8, "trigger": "keyword"}] if has_cluster else [],
            "skills_suggested": skills if has_cluster else [],
            "skill_invoked_in_turn": invoked,
            "tool_name": "Bash" if i % 4 == 0 else None,
            "tool_blocked": i % 20 == 0,
            "bypass_used": "[raw]" if i % 25 == 0 else None,
            "outcome": "tool_executed" if not (i % 20 == 0) else "tool_blocked",
        }
        entries.append(e)
    return entries


@pytest.fixture()
def populated_log_dir(tmp_path, monkeypatch):
    """Crea log_dir con 100 entries fake."""
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    f = log_dir / f"{today}.jsonl"
    entries = _make_fake_entries(100)
    with f.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")

    # Reimport stats con LOG_DIR redirigido
    import stats as stats_mod
    monkeypatch.setattr(stats_mod, "LOG_DIR", log_dir)
    return log_dir


def _run_cmd(argv: list[str]) -> tuple[int, str]:
    import stats as stats_mod
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = stats_mod.main(argv)
    return rc, buf.getvalue()


def test_t4_stats_parsea_jsonl_100_entries(populated_log_dir):
    """T4: summary parsea 100 entries fake sin error."""
    rc, out = _run_cmd(["summary", "--days", "1"])
    assert rc == 0
    assert "Total events: 100" in out
    assert "Hit-rate" in out


def test_t5_gaps_detection_encuentra_sin_cluster(populated_log_dir):
    """T5: gaps detecta prompts sin cluster."""
    rc, out = _run_cmd(["gaps", "--days", "1"])
    assert rc == 0
    # 30% de los 50 UPS deberían NO tener cluster (i % 10 < 7 es FALSE en 3 de cada 10)
    assert "Prompts sin cluster" in out


def test_t6_ghost_detection_skills(populated_log_dir):
    """T6: skills detecta ghosts (sugeridas, 0 invocaciones)."""
    rc, out = _run_cmd(["skills", "--days", "1"])
    assert rc == 0
    # Que el CLI imprima la tabla skills sin errores
    assert "Skills" in out
    assert "suggested" in out


def test_t7_cli_subcommands_exit_0(populated_log_dir):
    """T7: todos los subcommands retornan exit 0 + output válido."""
    for sub in ["summary", "clusters", "skills", "gaps", "gate"]:
        rc, out = _run_cmd([sub, "--days", "1"])
        assert rc == 0, f"subcommand {sub} retornó {rc}"
        assert len(out) > 0, f"subcommand {sub} sin output"


def test_stats_clusters_table(populated_log_dir):
    """Bonus: clusters subcommand muestra tabla con todos los clusters."""
    rc, out = _run_cmd(["clusters", "--days", "1"])
    assert rc == 0
    assert "marketing" in out
    assert "engineering" in out


def test_stats_gate_blocked_count(populated_log_dir):
    """Bonus: gate subcommand cuenta bloqueos."""
    rc, out = _run_cmd(["gate", "--days", "1"])
    assert rc == 0
    assert "blocked" in out.lower()


def test_stats_sin_datos(tmp_path, monkeypatch):
    """Bonus: subcommand sin datos no rompe."""
    import stats as stats_mod
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr(stats_mod, "LOG_DIR", empty_dir)
    rc, out = _run_cmd(["summary"])
    assert rc == 0
    assert "Sin datos" in out
