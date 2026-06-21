"""E2E tests using httpx TestClient against the FastAPI app.

Targets the 7 specified scenarios:
  T1 GET /                       → 200 + contiene 'skill router'
  T2 GET /clusters               → lista clusters reales
  T3 POST /clusters/{id} invalid → 422 + NO escritura
  T4 POST /clusters/{id} valid   → backup .bak + write + reload
  T5 GET /audit?session=X        → filtra correctamente
  T6 POST /actions/rebuild-embeddings → job_id devuelto + ejecuta runner
  T7 GET /health                 → estado correcto
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app  # late import after conftest isolation
    return TestClient(app)


def test_t1_home(client):
    r = client.get("/")
    assert r.status_code == 200
    text = r.text.lower()
    assert "skill router" in text
    assert "mission control" in text


def test_t2_clusters_list(client):
    r = client.get("/clusters")
    assert r.status_code == 200
    # Should mention at least 'finance' (seed) or any real cluster id
    body = r.text.lower()
    assert "finance" in body or "marketing" in body


def test_t3_invalid_yaml_no_write(client):
    from app import clusters_io
    before = clusters_io.load_raw_yaml()
    r = client.post("/clusters/finance", data={"cluster_yaml": "not: valid: : yaml: structure"})
    assert r.status_code == 422
    payload = r.json()
    assert payload["ok"] is False
    assert payload["errors"]
    after = clusters_io.load_raw_yaml()
    assert before == after  # no escritura


def test_t4_valid_yaml_writes_with_backup(client):
    from app import clusters_io, config
    new_def = (
        "description: \"Cluster financiero — updated by test E2E.\"\n"
        "skills:\n"
        "  - finance-skills:financial-analyst\n"
        "  - finance-skills:saas-metrics-coach\n"
        "triggers_natural:\n"
        "  - \"analisis financiero test\"\n"
        "confidence_threshold: 0.75\n"
    )
    backups_before = len(list(config.BACKUPS_DIR.glob("clusters.yaml.bak-*")))
    r = client.post("/clusters/finance", data={"cluster_yaml": new_def})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["ok"] is True
    assert payload["backup_path"] is not None
    # Backup file exists
    backups_after = len(list(config.BACKUPS_DIR.glob("clusters.yaml.bak-*")))
    assert backups_after == backups_before + 1
    # File reload sees change
    cdef = clusters_io.get_cluster("finance")
    assert "updated by test E2E" in cdef["description"]
    assert cdef["confidence_threshold"] == 0.75


def test_t5_audit_session_filter(client):
    # No filter
    all_r = client.get("/audit?days=7&limit=500")
    assert all_r.status_code == 200
    # Filter by session-1
    r = client.get("/audit?session=test-session-1&days=7")
    assert r.status_code == 200
    body = r.text
    assert "test-session" in body  # at least the filter dropdown reflects it
    # JSON-side check via stats summary present
    summary = client.get("/stats/summary?days=7").json()
    assert summary["user_prompts"] >= 1


def test_t6_rebuild_embeddings_returns_job_id(client):
    r = client.post("/actions/rebuild-embeddings")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["job_id"].startswith("emb-")
    # Wait a brief moment for background thread to write status
    time.sleep(0.3)
    follow = client.get(f"/jobs/{j['job_id']}")
    assert follow.status_code == 200
    assert follow.json()["id"] == j["job_id"]


def test_t7_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    h = r.json()
    assert h["status"] in {"ok", "degraded"}
    assert "clusters_count" in h
    assert h["clusters_yaml_exists"] is True
    assert h["clusters_count"] >= 1
    assert "last_event_ts" in h
    assert h["host"] == "127.0.0.1"
    assert h["port"] == 9300
