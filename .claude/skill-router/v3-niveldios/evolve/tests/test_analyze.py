"""Tests para analyze.py — T1, T2, T3, T4."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fixtures.mock_audit import build_clusters_yaml, build_mock_log  # noqa: E402


def _reload_analyze():
    if "analyze" in sys.modules:
        importlib.reload(sys.modules["analyze"])
    else:
        import analyze  # noqa: F401
    return sys.modules["analyze"]


# ─────────────────────────────────────────────────────────────
# T1 — detect_ghosts
# ─────────────────────────────────────────────────────────────


def test_t1_detect_ghosts_identifies_unused_skills(tmp_audit_env):
    """T1: ghosts = skills declaradas con 0 invocaciones en N días."""
    build_mock_log(tmp_audit_env["log_dir"], scenario="default")
    build_clusters_yaml(tmp_audit_env["clusters_yaml"], include_ghost=True)

    analyze = _reload_analyze()
    ghosts = analyze.detect_ghosts(audit_log_days=14)

    assert "dead-skill-1" in ghosts, f"dead-skill-1 debe ser ghost, obtuvo: {ghosts}"
    assert "marketing-copywriting" not in ghosts, "marketing-copywriting está siendo invocado"
    assert "finance-saas-metrics-coach" in ghosts, "esta skill nunca se invocó en default scenario"


def test_t1_detect_ghosts_empty_log_returns_declared(tmp_audit_env):
    """Sin audit log, todas las declaradas son ghosts."""
    build_clusters_yaml(tmp_audit_env["clusters_yaml"], include_ghost=True)

    analyze = _reload_analyze()
    ghosts = analyze.detect_ghosts(audit_log_days=14)

    assert "dead-skill-1" in ghosts
    assert "marketing-copywriting" in ghosts


# ─────────────────────────────────────────────────────────────
# T2 — detect_cold_clusters
# ─────────────────────────────────────────────────────────────


def test_t2_cold_clusters_threshold_works(tmp_audit_env):
    """T2: clusters con <umbral activaciones aparecen como cold."""
    build_mock_log(tmp_audit_env["log_dir"], scenario="default")
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    analyze = _reload_analyze()
    cold = analyze.detect_cold_clusters(audit_log_days=14, min_activations=5)
    cold_ids = {c["cluster_id"] for c in cold}

    # engineering tiene 1 activación → cold
    assert "engineering" in cold_ids
    # dead_zone tiene 0 → cold
    assert "dead_zone" in cold_ids
    # marketing tiene 28 (2/día × 14d) → NO cold
    assert "marketing" not in cold_ids


def test_t2_cold_clusters_high_threshold_marks_more(tmp_audit_env):
    build_mock_log(tmp_audit_env["log_dir"], scenario="default")
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    analyze = _reload_analyze()
    cold_low = analyze.detect_cold_clusters(audit_log_days=14, min_activations=5)
    cold_high = analyze.detect_cold_clusters(audit_log_days=14, min_activations=50)

    assert len(cold_high) >= len(cold_low)


# ─────────────────────────────────────────────────────────────
# T3 — detect_gap_queries
# ─────────────────────────────────────────────────────────────


def test_t3_gap_queries_groups_similar(tmp_audit_env):
    """T3: prompts similares sin cluster se agrupan."""
    build_mock_log(tmp_audit_env["log_dir"], scenario="default")
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    analyze = _reload_analyze()
    gaps = analyze.detect_gap_queries(audit_log_days=14, min_repetitions=3)

    assert len(gaps) >= 1, f"Debe detectar al menos 1 gap, obtuvo: {gaps}"
    top = gaps[0]
    assert top["occurrences"] >= 3
    assert "jardín" in top["representative"] or "skills" in top["representative"].lower()


def test_t3_gap_queries_below_threshold_excluded(tmp_audit_env):
    """Prompts que aparecen <min_repetitions NO son gaps."""
    build_mock_log(tmp_audit_env["log_dir"], scenario="default")
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    analyze = _reload_analyze()
    gaps = analyze.detect_gap_queries(audit_log_days=14, min_repetitions=99)

    assert gaps == [], f"Con threshold 99 no debe haber gaps, obtuvo: {gaps}"


# ─────────────────────────────────────────────────────────────
# T4 — detect_false_positive_clusters
# ─────────────────────────────────────────────────────────────


def test_t4_false_positive_calculates_correct_ratio(tmp_audit_env):
    """T4: ratio de skill sugerida pero no invocada."""
    build_mock_log(tmp_audit_env["log_dir"], scenario="default")
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    analyze = _reload_analyze()
    fp = analyze.detect_false_positive_clusters(
        audit_log_days=14, ignore_ratio_threshold=0.7, min_suggestions=3
    )

    # finance sugiere finance-business-investment-advisor 28 veces, invoca 0 → ignored=1.0
    finance_entries = [f for f in fp if f["cluster_id"] == "finance"]
    assert finance_entries, f"finance debe ser false positive, fp={fp}"
    e = finance_entries[0]
    assert e["ignored_ratio"] == 1.0
    assert e["invoked_count"] == 0
    assert e["suggested_count"] >= 3

    # marketing skill invocada → NO debe estar
    marketing_fp = [f for f in fp if f["cluster_id"] == "marketing" and f["skill_suggested"] == "marketing-copywriting"]
    assert not marketing_fp


# ─────────────────────────────────────────────────────────────
# Robustez: empty log
# ─────────────────────────────────────────────────────────────


def test_empty_log_no_crash(tmp_audit_env):
    """Sin audit log dir, nada explota."""
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    analyze = _reload_analyze()
    assert isinstance(analyze.detect_cold_clusters(14), list)
    assert isinstance(analyze.detect_gap_queries(14), list)
    assert isinstance(analyze.detect_false_positive_clusters(7), list)
    assert isinstance(analyze.detect_gate_friction(7), list)


def test_detect_gate_friction(tmp_audit_env):
    """Bonus: gate friction detecta bypass alto."""
    build_mock_log(tmp_audit_env["log_dir"], scenario="default")
    build_clusters_yaml(tmp_audit_env["clusters_yaml"])

    analyze = _reload_analyze()
    friction = analyze.detect_gate_friction(audit_log_days=14, bypass_ratio_threshold=0.3, min_activations=3)
    friction_ids = {f["cluster_id"] for f in friction}
    assert "security" in friction_ids, f"security debe tener friction (todos bypassed), obtuvo: {friction}"
