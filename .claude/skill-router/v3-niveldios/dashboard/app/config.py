"""Dashboard config — paths + read-only references.

Single source of truth para rutas. SOLO escribe en:
  - CLUSTERS_YAML (con backup .bak SIEMPRE pre-write)
  - JOBS_DIR (job status async)

Lee de:
  - V2_DIR (state, llm cache)
  - AUDIT_LOG_DIR (JSONL diario)
  - EMBEDDINGS / EVOLVE dirs (status sólo)
"""
from __future__ import annotations

import os
from pathlib import Path

HOME = Path.home()

# Skill router paths
ROUTER_ROOT = HOME / ".claude" / "skill-router"
V2_DIR = ROUTER_ROOT / "v2"
V3_DIR = ROUTER_ROOT / "v3-niveldios"

CLUSTERS_YAML = V2_DIR / "clusters.yaml"
V2_STATE = V2_DIR / "state.json"

AUDIT_DIR = V3_DIR / "audit"
AUDIT_LOG_DIR = AUDIT_DIR / "log"
AUDIT_STATS_PY = AUDIT_DIR / "stats.py"

EMBEDDINGS_DIR = V3_DIR / "embeddings"
EVOLVE_DIR = V3_DIR / "evolve"
EVOLVE_BIN = EVOLVE_DIR / "bin"
EMBEDDINGS_BIN = EMBEDDINGS_DIR / "bench"  # rebuild scripts may land here too

# Dashboard internal
DASHBOARD_DIR = V3_DIR / "dashboard"
TEMPLATES_DIR = DASHBOARD_DIR / "app" / "templates"
STATIC_DIR = DASHBOARD_DIR / "app" / "static"
BACKUPS_DIR = DASHBOARD_DIR / "backups"
JOBS_DIR = DASHBOARD_DIR / "jobs"
LOG_DIR = DASHBOARD_DIR / "log"
PID_DIR = DASHBOARD_DIR / "pid"

# Skill discovery (from CLAUDE Code skills + plugins)
SKILLS_USER_DIR = HOME / ".claude" / "skills"
SKILLS_PLUGINS_DIR = HOME / ".claude" / "plugins"

# Bind
HOST = os.getenv("ROUTER_DASH_HOST", "127.0.0.1")
PORT = int(os.getenv("ROUTER_DASH_PORT", "9300"))


def ensure_dirs() -> None:
    """Idempotent — create runtime dirs."""
    for d in (BACKUPS_DIR, JOBS_DIR, LOG_DIR, PID_DIR):
        d.mkdir(parents=True, exist_ok=True)
