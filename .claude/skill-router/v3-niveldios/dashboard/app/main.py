"""FastAPI app — Mission Control for the Skill Router V3.

Runs on 127.0.0.1:9300 by default. Localhost-only.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import audit_io, clusters_io, config, jobs, skills_io

config.ensure_dirs()
app = FastAPI(title="Skill Router Mission Control", version="1.0.0")

templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
if config.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Template helpers
# ─────────────────────────────────────────────────────────────────────────────


def _ctx(**extra: Any) -> dict[str, Any]:
    base = {
        "host": config.HOST,
        "port": config.PORT,
        "version": app.version,
        "build_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    base.update(extra)
    return base


def _render(request: Request, template: str, **context: Any):
    """Wrapper compatible con Starlette 1.x — pasa request como 1er arg posicional."""
    return templates.TemplateResponse(request, template, _ctx(**context))


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health", response_class=JSONResponse)
def health() -> dict[str, Any]:
    try:
        clusters = clusters_io.load_clusters()
        cluster_count = len(clusters.get("clusters", {}))
        clusters_ok = True
    except Exception as exc:  # noqa: BLE001
        cluster_count = 0
        clusters_ok = False
        _ = exc

    last_audit = audit_io.last_event_ts()
    audit_log_files = (
        len(list(config.AUDIT_LOG_DIR.glob("*.jsonl"))) if config.AUDIT_LOG_DIR.exists() else 0
    )

    return {
        "status": "ok" if clusters_ok else "degraded",
        "version": app.version,
        "clusters_count": cluster_count,
        "clusters_yaml_path": str(config.CLUSTERS_YAML),
        "clusters_yaml_exists": config.CLUSTERS_YAML.exists(),
        "audit_log_dir": str(config.AUDIT_LOG_DIR),
        "audit_log_files": audit_log_files,
        "last_event_ts": last_audit,
        "embeddings_dir_exists": config.EMBEDDINGS_DIR.exists(),
        "evolve_dir_exists": config.EVOLVE_DIR.exists(),
        "host": config.HOST,
        "port": config.PORT,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Home / overview
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    s = audit_io.summary(days=7)
    daily = audit_io.daily_activations(days=14)
    gap = audit_io.gaps(days=7, limit=5)
    cluster_count = len((clusters_io.load_clusters() or {}).get("clusters", {}))
    return _render(
        request,
        "home.html",
        summary=s,
        daily=daily,
        gap=gap,
        cluster_count=cluster_count,
    )


@app.get("/partials/overview-cards", response_class=HTMLResponse)
def overview_cards(request: Request) -> HTMLResponse:
    s = audit_io.summary(days=7)
    cluster_count = len((clusters_io.load_clusters() or {}).get("clusters", {}))
    return _render(request, "partials/overview_cards.html", summary=s, cluster_count=cluster_count)


# ─────────────────────────────────────────────────────────────────────────────
# Clusters
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/clusters", response_class=HTMLResponse)
def clusters_list(request: Request, days: int = 7) -> HTMLResponse:
    data = clusters_io.load_clusters().get("clusters", {})
    stats_by = {row["cluster_id"]: row for row in audit_io.cluster_stats(days)}
    rows = []
    for cid, cdef in data.items():
        st = stats_by.get(cid, {})
        rows.append({
            "id": cid,
            "description": cdef.get("description", ""),
            "skills_count": len(cdef.get("skills", []) or []),
            "triggers_count": len(cdef.get("triggers_natural", []) or []),
            "threshold": cdef.get("confidence_threshold", "—"),
            "auto_invoke": bool(cdef.get("auto_invoke", False)),
            "activations": st.get("activations", 0),
            "skills_suggested": st.get("skills_suggested", 0),
            "skills_invoked": st.get("skills_invoked", 0),
            "invoke_rate": st.get("invoke_rate", 0.0),
            "last_seen": st.get("last_seen", ""),
        })
    rows.sort(key=lambda r: (-r["activations"], r["id"]))
    return _render(request, "clusters.html", clusters=rows, days=days)


@app.get("/clusters/{cluster_id}", response_class=HTMLResponse)
def cluster_detail(request: Request, cluster_id: str, days: int = 30) -> HTMLResponse:
    cdef = clusters_io.get_cluster(cluster_id)
    if cdef is None:
        raise HTTPException(404, f"cluster '{cluster_id}' not found")
    yaml_snippet = yaml.safe_dump(
        {cluster_id: cdef}, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    stats_rows = audit_io.cluster_stats(days)
    stats = next((r for r in stats_rows if r["cluster_id"] == cluster_id), {})
    return _render(
        request,
        "cluster_detail.html",
        cluster_id=cluster_id,
        cdef=cdef,
        yaml_snippet=yaml_snippet,
        stats=stats,
        days=days,
    )


@app.get("/clusters/{cluster_id}/edit", response_class=HTMLResponse)
def cluster_edit_form(request: Request, cluster_id: str) -> HTMLResponse:
    cdef = clusters_io.get_cluster(cluster_id)
    if cdef is None:
        raise HTTPException(404, f"cluster '{cluster_id}' not found")
    yaml_snippet = yaml.safe_dump(
        cdef, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return _render(request, "cluster_edit.html", cluster_id=cluster_id, yaml_snippet=yaml_snippet)


@app.post("/clusters/{cluster_id}")
async def cluster_save(request: Request, cluster_id: str):
    form = await request.form()
    yaml_text = (form.get("cluster_yaml") or "").strip()
    if not yaml_text:
        return JSONResponse({"ok": False, "errors": ["empty body"]}, status_code=422)

    # Parse cluster def in isolation
    try:
        cluster_def = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return JSONResponse({"ok": False, "errors": [f"YAML parse error: {exc}"]}, status_code=422)
    if not isinstance(cluster_def, dict):
        return JSONResponse(
            {"ok": False, "errors": ["Cluster body debe ser un dict (description/skills/...)"]},
            status_code=422,
        )

    # Build full doc + validate full schema
    full = clusters_io.load_clusters()
    full.setdefault("clusters", {})[cluster_id] = cluster_def
    full_text = yaml.safe_dump(full, sort_keys=False, allow_unicode=True, default_flow_style=False)
    result = clusters_io.save_clusters_yaml(full_text)
    status = 200 if result["ok"] else 422
    return JSONResponse(result, status_code=status)


@app.post("/clusters/_raw/save")
async def raw_save(request: Request):
    """Save full clusters.yaml (advanced editor)."""
    form = await request.form()
    text = form.get("clusters_yaml", "")
    result = clusters_io.save_clusters_yaml(text)
    return JSONResponse(result, status_code=200 if result["ok"] else 422)


# ─────────────────────────────────────────────────────────────────────────────
# Skills
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/skills", response_class=HTMLResponse)
def skills_page(request: Request, filter: str = "all", days: int = 30) -> HTMLResponse:
    items = skills_io.enriched_skills(days=days)
    if filter == "active":
        items = [s for s in items if s["invoked"] > 0]
    elif filter == "ghost":
        items = [s for s in items if s["ghost"]]
    elif filter == "missing":
        items = [s for s in items if s["source"] == "missing"]
    return _render(request, "skills.html", skills=items, filter=filter, days=days, total=len(items))


# ─────────────────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request,
    session: str | None = None,
    days: int = 7,
    limit: int = 100,
) -> HTMLResponse:
    entries = audit_io.load_entries(days=days, session_id=session, limit=limit)
    sessions = sorted({e.get("session_id", "") for e in entries if e.get("session_id")})
    return _render(
        request,
        "audit.html",
        entries=entries,
        sessions=sessions,
        session_filter=session,
        days=days,
        limit=limit,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stats (JSON + page)
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/stats/summary", response_class=JSONResponse)
def stats_summary(days: int = 7) -> dict[str, Any]:
    return audit_io.summary(days=days)


@app.get("/stats/gaps", response_class=JSONResponse)
def stats_gaps(days: int = 14, limit: int = 100) -> dict[str, Any]:
    return audit_io.gaps(days=days, limit=limit)


@app.get("/stats/clusters", response_class=JSONResponse)
def stats_clusters(days: int = 7) -> list[dict[str, Any]]:
    return audit_io.cluster_stats(days=days)


@app.get("/stats/daily", response_class=JSONResponse)
def stats_daily(days: int = 14) -> list[dict[str, Any]]:
    return audit_io.daily_activations(days=days)


@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, days: int = 14) -> HTMLResponse:
    daily = audit_io.daily_activations(days=days)
    summary = audit_io.summary(days=days)
    cluster_rows = audit_io.cluster_stats(days=days)
    return _render(
        request,
        "stats.html",
        daily=daily,
        summary=summary,
        cluster_rows=cluster_rows,
        days=days,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Actions (jobs)
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/actions/rebuild-embeddings", response_class=JSONResponse)
def action_rebuild_embeddings() -> dict[str, Any]:
    job_id = jobs.trigger_rebuild_embeddings()
    return {"ok": True, "job_id": job_id}


@app.post("/actions/evolve", response_class=JSONResponse)
def action_evolve(dry_run: bool = True) -> dict[str, Any]:
    job_id = jobs.trigger_evolve(dry_run=dry_run)
    return {"ok": True, "job_id": job_id}


@app.get("/jobs", response_class=JSONResponse)
def list_jobs_endpoint(limit: int = 20) -> list[dict[str, Any]]:
    return jobs.list_jobs(limit=limit)


@app.get("/jobs/{job_id}", response_class=JSONResponse)
def get_job_endpoint(job_id: str) -> dict[str, Any]:
    j = jobs.get_job(job_id)
    if j is None:
        raise HTTPException(404, f"job '{job_id}' not found")
    return j


# ─────────────────────────────────────────────────────────────────────────────
# Robots / favicon noise prevention
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow: /\n"


@app.get("/favicon.ico")
def favicon():
    return PlainTextResponse("", status_code=204)
