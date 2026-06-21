"""Pytest fixtures comunes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

EVOLVE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVOLVE_DIR))


@pytest.fixture
def tmp_audit_env(tmp_path, monkeypatch):
    """Sandboxea analyze.py: redirige audit/log + clusters + skills + reports a tmp_path."""
    log_dir = tmp_path / "audit" / "log"
    log_dir.mkdir(parents=True)
    clusters_yaml = tmp_path / "v2" / "clusters.yaml"
    clusters_yaml.parent.mkdir(parents=True)
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    monkeypatch.setenv("SKILL_ROUTER_ROOT", str(tmp_path))
    monkeypatch.setenv("SKILL_ROUTER_AUDIT_LOG_DIR", str(log_dir))
    monkeypatch.setenv("SKILL_ROUTER_CLUSTERS_YAML", str(clusters_yaml))
    monkeypatch.setenv("SKILL_ROUTER_SKILLS_DIR", str(skills_dir))
    monkeypatch.setenv("SKILL_ROUTER_EVOLVE_REPORTS", str(reports_dir))

    # Reset módulos para que recojan envs nuevos
    for m in ("analyze", "propose"):
        if m in sys.modules:
            del sys.modules[m]

    import analyze  # noqa: F401  pylint: disable=unused-import
    import propose  # noqa: F401  pylint: disable=unused-import

    return {
        "root": tmp_path,
        "log_dir": log_dir,
        "clusters_yaml": clusters_yaml,
        "skills_dir": skills_dir,
        "reports_dir": reports_dir,
    }
