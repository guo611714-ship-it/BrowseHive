"""Tests para propose.py — T5, T6, T7."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fixtures.mock_audit import build_clusters_yaml, build_mock_log  # noqa: E402


def _reload_propose():
    for m in ("analyze", "propose"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import propose  # noqa: F401

    return sys.modules["propose"]


# ─────────────────────────────────────────────────────────────
# T5 — propose.py genera markdown válido
# ─────────────────────────────────────────────────────────────


def test_t5_render_report_returns_valid_markdown(tmp_audit_env):
    build_mock_log(tmp_audit_env["log_dir"], scenario="default")
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    propose = _reload_propose()
    md = propose.render_report(days=14)

    assert md.startswith("# Router Evolution Report"), "Debe abrir con H1"
    # Las 5 secciones canónicas presentes
    for h in [
        "## Ghosts",
        "## Cold clusters",
        "## Gap queries",
        "## False positive clusters",
        "## Gate friction",
        "## Acciones recomendadas",
    ]:
        assert h in md, f"falta sección {h!r}"
    # No debe tener placeholders sin reemplazar
    assert "{" not in md or "}" not in md or "{:" not in md


def test_t5_render_report_with_explicit_data():
    """Render acepta `data` precomputado para tests aislados."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import propose  # noqa: WPS433

    data = {
        "ghosts": ["a", "b", "c"],
        "cold_clusters": [{"cluster_id": "x", "activations": 1, "threshold": 5}],
        "gap_queries": [{"representative": "test prompt", "occurrences": 5, "examples": []}],
        "false_positives": [
            {
                "cluster_id": "foo",
                "skill_suggested": "bar",
                "suggested_count": 10,
                "invoked_count": 1,
                "ignored_ratio": 0.9,
            }
        ],
        "gate_friction": [
            {"cluster_id": "z", "total_activations": 10, "bypassed_count": 8, "bypass_ratio": 0.8}
        ],
    }
    md = propose.render_report(days=14, data=data)
    assert "`a`" in md and "`b`" in md
    assert "test prompt" in md
    assert "`x`" in md
    assert "`foo`" in md and "`bar`" in md
    assert "`z`" in md
    # Acciones priority debe listar al menos 1
    assert "1. " in md


# ─────────────────────────────────────────────────────────────
# T6 — Persistencia con naming correcto
# ─────────────────────────────────────────────────────────────


def test_t6_persist_report_writes_correct_filename(tmp_audit_env):
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    propose = _reload_propose()
    fixed_now = datetime(2026, 5, 17, 21, 0, tzinfo=timezone.utc)
    md = "# test report"
    out = propose.persist_report(md, now=fixed_now, reports_dir=tmp_audit_env["reports_dir"])

    iso = fixed_now.isocalendar()
    expected_name = f"{iso.year}-W{iso.week:02d}.md"
    assert out.name == expected_name, f"esperado {expected_name}, obtuvo {out.name}"
    assert out.read_text() == md
    assert out.parent == tmp_audit_env["reports_dir"]


def test_t6_persist_overwrites_same_week(tmp_audit_env):
    propose = _reload_propose()
    fixed_now = datetime(2026, 5, 17, 21, 0, tzinfo=timezone.utc)
    p1 = propose.persist_report("first", now=fixed_now, reports_dir=tmp_audit_env["reports_dir"])
    p2 = propose.persist_report("second", now=fixed_now, reports_dir=tmp_audit_env["reports_dir"])
    assert p1 == p2
    assert p2.read_text() == "second"


# ─────────────────────────────────────────────────────────────
# T7 — Telegram send (mock transport)
# ─────────────────────────────────────────────────────────────


def test_t7_telegram_send_uses_transport_mock(tmp_audit_env, monkeypatch):
    propose = _reload_propose()

    captured = {}

    def fake_transport(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"ok": True, "result": {"message_id": 42}}

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token-123")
    result = propose.send_telegram("hola mundo", chat_id="999", transport=fake_transport)

    assert result["ok"] is True
    assert "sendMessage" in captured["url"]
    assert "fake-token-123" in captured["url"]
    assert captured["payload"]["chat_id"] == "999"
    assert captured["payload"]["text"] == "hola mundo"


def test_t7_telegram_without_token_returns_error(tmp_audit_env, monkeypatch):
    propose = _reload_propose()
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("OPENCLAW_BOT_TOKEN", raising=False)

    result = propose.send_telegram("test")
    assert result["ok"] is False
    assert result["error"] == "no_bot_token"


def test_t7_telegram_truncates_long_messages(tmp_audit_env, monkeypatch):
    propose = _reload_propose()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")

    long_msg = "x" * 10000
    captured = {}

    def fake_transport(url, payload):
        captured["payload"] = payload
        return {"ok": True}

    propose.send_telegram(long_msg, chat_id="1", transport=fake_transport)
    sent = captured["payload"]["text"]
    assert len(sent) <= 4096
