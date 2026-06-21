"""Async job runner para acciones del dashboard.

Triggers:
- rebuild_embeddings → exec script de Agent C (no-op fallback si no existe)
- router_evolve → exec script de Agent D --dry-run (no-op fallback)

Job status persistido en JSONL para que UI haga polling.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import config


def _jobs_file() -> Path:
    config.ensure_dirs()
    return config.JOBS_DIR / "jobs.jsonl"


def _write_job(job: dict[str, Any]) -> None:
    path = _jobs_file()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(job, ensure_ascii=False) + "\n")


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    path = _jobs_file()
    if not path.exists():
        return []
    seen: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen[j["id"]] = j  # last status wins
    out = list(seen.values())
    out.sort(key=lambda j: j.get("started_at", ""), reverse=True)
    return out[:limit]


def get_job(job_id: str) -> dict[str, Any] | None:
    for j in list_jobs(limit=1000):
        if j["id"] == job_id:
            return j
    return None


def _run_async(job_id: str, action: str, cmd: list[str] | None, fallback_msg: str) -> None:
    """Background runner. Captura stdout/stderr, persiste estado."""
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_job({
        "id": job_id,
        "action": action,
        "status": "running",
        "started_at": started,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
    })

    def runner() -> None:
        if not cmd:
            # Fallback: no script disponible
            _write_job({
                "id": job_id,
                "action": action,
                "status": "no_op",
                "started_at": started,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "stdout": fallback_msg,
                "stderr": "",
                "exit_code": 0,
            })
            return
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            _write_job({
                "id": job_id,
                "action": action,
                "status": "ok" if proc.returncode == 0 else "fail",
                "started_at": started,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "stdout": (proc.stdout or "")[-4000:],
                "stderr": (proc.stderr or "")[-2000:],
                "exit_code": proc.returncode,
                "cmd": " ".join(cmd),
            })
        except subprocess.TimeoutExpired:
            _write_job({
                "id": job_id,
                "action": action,
                "status": "timeout",
                "started_at": started,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "stdout": "",
                "stderr": "timeout 300s",
                "exit_code": 124,
                "cmd": " ".join(cmd),
            })
        except Exception as exc:
            _write_job({
                "id": job_id,
                "action": action,
                "status": "fail",
                "started_at": started,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "stdout": "",
                "stderr": str(exc),
                "exit_code": 1,
                "cmd": " ".join(cmd) if cmd else "",
            })

    threading.Thread(target=runner, daemon=True).start()


def _find_script(directory: Path, names: list[str]) -> list[str] | None:
    if not directory.exists():
        return None
    for n in names:
        p = directory / n
        if p.exists() and p.is_file():
            # .py: usa venv del paquete si existe, fallback python3
            if p.suffix == ".py":
                venv_py = directory.parent / "venv" / "bin" / "python"
                if not venv_py.exists():
                    venv_py = directory / "venv" / "bin" / "python"
                if venv_py.exists():
                    return [str(venv_py), str(p)]
                return ["python3", str(p)]
            # .sh: bash explícito
            if p.suffix == ".sh":
                return ["bash", str(p)]
            # sin sufijo: ejecutable directo
            if not p.suffix:
                return [str(p)]
    return None


def trigger_rebuild_embeddings() -> str:
    """Lanza job rebuild embeddings (Agent C)."""
    job_id = "emb-" + uuid.uuid4().hex[:8]
    # 17-may coordinator: Agent C entregó build_index.py en raíz EMBEDDINGS_DIR
    cmd = _find_script(
        config.EMBEDDINGS_DIR,
        ["build_index.py", "rebuild.py"],
    ) or _find_script(
        config.EMBEDDINGS_DIR / "bench",
        ["build_index.py", "rebuild.py", "rebuild"],
    ) or _find_script(
        config.EMBEDDINGS_DIR / "bin",
        ["build_index.py", "rebuild.py", "rebuild"],
    )
    fallback = (
        "Embeddings module not deployed yet (Agent C pending). "
        "Job marked as no_op."
    )
    _run_async(job_id, "rebuild_embeddings", cmd, fallback)
    return job_id


def trigger_evolve(dry_run: bool = True) -> str:
    """Lanza job router-evolve (Agent D)."""
    job_id = "evo-" + uuid.uuid4().hex[:8]
    # 17-may coordinator: Agent D entregó router-evolve.sh (con extensión .sh)
    base = _find_script(
        config.EVOLVE_BIN,
        ["router-evolve.sh", "router-evolve", "evolve.py", "router_evolve.py"],
    )
    if base and dry_run:
        base = base + ["--dry-run"]
    fallback = (
        "Evolve module not deployed yet (Agent D pending). "
        "Job marked as no_op."
    )
    _run_async(job_id, "router_evolve", base, fallback)
    return job_id
