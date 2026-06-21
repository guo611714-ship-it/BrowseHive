"""Pytest fixtures — isolate filesystem so tests never touch real clusters.yaml."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

# Make repo importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolate_filesystem(tmp_path_factory):
    """Redirect dashboard config paths to an ephemeral tree.

    Crucially we copy the real clusters.yaml + 1 day of audit log fixtures
    into the temp tree so tests have realistic data, but write attempts go
    into the isolated copy — NEVER touching ~/.claude/skill-router/v2/.
    """
    from app import config as cfg  # noqa: WPS433  (after path injection)

    real_clusters = cfg.CLUSTERS_YAML
    real_audit_log = cfg.AUDIT_LOG_DIR

    tmp_router = tmp_path_factory.mktemp("router")
    tmp_v2 = tmp_router / "v2"
    tmp_v2.mkdir()
    tmp_v3 = tmp_router / "v3"
    tmp_audit = tmp_v3 / "audit"
    tmp_audit_log = tmp_audit / "log"
    tmp_audit_log.mkdir(parents=True)
    tmp_dash = tmp_v3 / "dashboard"
    (tmp_dash / "backups").mkdir(parents=True)
    (tmp_dash / "jobs").mkdir(parents=True)
    (tmp_dash / "log").mkdir(parents=True)
    (tmp_dash / "pid").mkdir(parents=True)

    # Copy real clusters.yaml so tests have realistic data
    test_clusters = tmp_v2 / "clusters.yaml"
    if real_clusters.exists():
        shutil.copy2(real_clusters, test_clusters)
    else:
        test_clusters.write_text(
            "clusters:\n"
            "  finance:\n"
            "    description: \"Test cluster financiero.\"\n"
            "    skills:\n"
            "      - finance-skills:financial-analyst\n"
            "    confidence_threshold: 0.7\n",
            encoding="utf-8",
        )

    # Seed audit log with synthetic entries (use TODAY's filename so window catches)
    import datetime as _dt
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    log_path = tmp_audit_log / f"{today}.jsonl"
    seed = [
        {
            "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": "test-session-1",
            "hook_event": "UserPromptSubmit",
            "prompt_excerpt": "vamos con marketing nuevo lanzamiento",
            "cwd": "/tmp/proj",
            "clusters_activated": [{"id": "marketing", "confidence": 0.91}],
            "skills_suggested": ["marketing-skills:copywriting"],
            "skill_invoked_in_turn": "marketing-skills:copywriting",
            "outcome": "tool_executed",
        },
        {
            "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": "test-session-2",
            "hook_event": "UserPromptSubmit",
            "prompt_excerpt": "hola que tal todo",  # no cluster
            "cwd": "/tmp/proj",
            "clusters_activated": [],
            "skills_suggested": [],
            "outcome": "no_match",
        },
    ]
    import json as _json
    with log_path.open("w", encoding="utf-8") as fh:
        for entry in seed:
            fh.write(_json.dumps(entry) + "\n")

    # Override config paths
    cfg.CLUSTERS_YAML = test_clusters
    cfg.AUDIT_LOG_DIR = tmp_audit_log
    cfg.AUDIT_DIR = tmp_audit
    cfg.BACKUPS_DIR = tmp_dash / "backups"
    cfg.JOBS_DIR = tmp_dash / "jobs"
    cfg.LOG_DIR = tmp_dash / "log"
    cfg.PID_DIR = tmp_dash / "pid"
    cfg.EMBEDDINGS_DIR = tmp_v3 / "embeddings"
    cfg.EVOLVE_DIR = tmp_v3 / "evolve"
    cfg.EVOLVE_BIN = cfg.EVOLVE_DIR / "bin"
    yield
    # No cleanup needed — tmp_path_factory handles it
