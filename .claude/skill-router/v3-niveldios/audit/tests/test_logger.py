"""Tests del logger audit V3."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

AUDIT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUDIT_DIR))


@pytest.fixture()
def tmp_log_dir(tmp_path, monkeypatch):
    """Redirige LOG_DIR a tmp_path para aislamiento."""
    import logger as logger_mod
    monkeypatch.setattr(logger_mod, "LOG_DIR", tmp_path / "log")
    return tmp_path / "log"


def test_t1_logger_escribe_jsonl_valido(tmp_log_dir):
    """T1: logger escribe JSONL válido + retorna True."""
    import logger as logger_mod

    payload = {
        "session_id": "test-1",
        "hook_event": "UserPromptSubmit",
        "prompt_excerpt": "hola mundo",
        "cwd": "/tmp",
        "clusters_activated": [{"id": "marketing", "confidence": 0.9, "trigger": "keyword"}],
        "skills_suggested": ["copywriting"],
        "outcome": "tool_executed",
    }
    ok = logger_mod.log_decision(payload)
    assert ok is True

    files = list(tmp_log_dir.glob("*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["session_id"] == "test-1"
    assert parsed["hook_event"] == "UserPromptSubmit"
    assert "ts" in parsed
    assert parsed["clusters_activated"][0]["id"] == "marketing"


def test_t2_rotacion_diaria_funciona(tmp_log_dir):
    """T2: payloads de días distintos van a ficheros distintos."""
    import logger as logger_mod

    day1 = datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 5, 16, 10, 0, 0, tzinfo=timezone.utc)

    logger_mod.log_decision({"session_id": "d1", "hook_event": "UserPromptSubmit"}, _now=day1)
    logger_mod.log_decision({"session_id": "d2", "hook_event": "UserPromptSubmit"}, _now=day2)

    files = sorted(f.name for f in tmp_log_dir.glob("*.jsonl"))
    assert "2026-05-15.jsonl" in files
    assert "2026-05-16.jsonl" in files


def test_t3_retencion_90_dias_borra_antiguos(tmp_log_dir):
    """T3: logs >90d se borran en cada write."""
    import logger as logger_mod

    tmp_log_dir.mkdir(parents=True, exist_ok=True)
    # Fichero antiguo (100 días)
    old_date = datetime.now(timezone.utc) - timedelta(days=100)
    old_file = tmp_log_dir / f"{old_date.strftime('%Y-%m-%d')}.jsonl"
    old_file.write_text('{"session_id": "antiguo"}\n', encoding="utf-8")

    # Fichero reciente (10 días)
    recent_date = datetime.now(timezone.utc) - timedelta(days=10)
    recent_file = tmp_log_dir / f"{recent_date.strftime('%Y-%m-%d')}.jsonl"
    recent_file.write_text('{"session_id": "reciente"}\n', encoding="utf-8")

    # Trigger write → prune
    logger_mod.log_decision({"session_id": "trigger", "hook_event": "UserPromptSubmit"})

    assert not old_file.exists(), "fichero >90d debió borrarse"
    assert recent_file.exists(), "fichero <90d NO debió borrarse"


def test_pii_scrub_en_prompt_excerpt(tmp_log_dir):
    """Bonus: scrub PII (tokens visibles) en prompt_excerpt — cubre múltiples formatos."""
    import logger as logger_mod

    cases = [
        ("mi token sk-abc1234567890defghij1234567890 y ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaa", ["sk-abc", "ghp_aaaa"]),
        ("formato laxo sk-secret-VISIBLE-1000 dentro", ["sk-secret-VISIBLE"]),
        ("Bearer eyJabc123def456ghi789jkl012 fin", ["eyJabc123"]),
        ("password=miClaveSuperSecreta123 ok", ["miClaveSuperSecreta"]),
        ("token: abc12345678901234 stuff", ["abc12345678901234"]),
    ]
    for prompt, leaked_tokens in cases:
        # Limpiar logs entre cases
        for f in tmp_log_dir.glob("*.jsonl"):
            f.unlink()
        logger_mod.log_decision({
            "session_id": "pii-test",
            "hook_event": "UserPromptSubmit",
            "prompt_excerpt": prompt,
        })
        files = list(tmp_log_dir.glob("*.jsonl"))
        assert files, f"no log para case: {prompt}"
        line = files[0].read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        for token in leaked_tokens:
            assert token not in parsed["prompt_excerpt"], f"LEAK '{token}' en case '{prompt}' → got '{parsed['prompt_excerpt']}'"
        assert "[REDACTED]" in parsed["prompt_excerpt"], f"no [REDACTED] en case '{prompt}' → got '{parsed['prompt_excerpt']}'"


def test_truncate_excerpt_200_chars(tmp_log_dir):
    """Bonus: prompt_excerpt se trunca a 200 chars max."""
    import logger as logger_mod

    long_prompt = "a" * 500
    logger_mod.log_decision({
        "session_id": "trunc",
        "hook_event": "UserPromptSubmit",
        "prompt_excerpt": long_prompt,
    })
    line = list(tmp_log_dir.glob("*.jsonl"))[0].read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    # 200 + "..." = 203
    assert len(parsed["prompt_excerpt"]) <= 210
    assert parsed["prompt_excerpt"].endswith("...")


def test_logger_fail_safe_no_raises(tmp_path, monkeypatch):
    """Bonus: si write falla, devuelve False pero NO lanza."""
    import logger as logger_mod
    # Apuntar a path imposible (read-only de root)
    monkeypatch.setattr(logger_mod, "LOG_DIR", Path("/sys/this/cannot/be/written"))
    ok = logger_mod.log_decision({"session_id": "fail", "hook_event": "UserPromptSubmit"})
    assert ok is False  # falló pero NO raise
