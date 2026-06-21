"""Clusters YAML IO with safe write + validation.

NUNCA edita v2/ código. Solo lee clusters.yaml y escribe con backup .bak.
Validación: jsonschema (estructura) + Pydantic-style sanity checks.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from . import config

# ─────────────────────────────────────────────────────────────────────────────
# Schema (lo definimos vivo aquí — refleja lo que trigger_v2.py espera)
# ─────────────────────────────────────────────────────────────────────────────

CLUSTER_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["clusters"],
    "additionalProperties": True,
    "properties": {
        "clusters": {
            "type": "object",
            "minProperties": 1,
            "patternProperties": {
                r"^[a-z][a-z0-9_]*$": {
                    "type": "object",
                    "required": ["description", "skills"],
                    "additionalProperties": True,
                    "properties": {
                        "description": {"type": "string", "minLength": 5},
                        "triggers_natural": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                        "skills": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "confidence_threshold": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "auto_invoke": {"type": "boolean"},
                        "gate_reminder": {"type": "string"},
                    },
                }
            },
            "additionalProperties": False,
        }
    },
}

_validator = Draft202012Validator(CLUSTER_SCHEMA)


# ─────────────────────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────────────────────


def load_clusters() -> dict[str, Any]:
    """Carga el YAML completo. Devuelve dict {clusters: {...}}.

    Si falla parseo, raise ValueError con detalle.
    """
    if not config.CLUSTERS_YAML.exists():
        return {"clusters": {}}
    try:
        raw = config.CLUSTERS_YAML.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        if "clusters" not in data:
            data["clusters"] = {}
        return data
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML parse error: {exc}") from exc


def load_raw_yaml() -> str:
    """Devuelve el contenido raw del fichero (para editor)."""
    if not config.CLUSTERS_YAML.exists():
        return ""
    return config.CLUSTERS_YAML.read_text(encoding="utf-8")


def get_cluster(cluster_id: str) -> dict[str, Any] | None:
    data = load_clusters()
    return data.get("clusters", {}).get(cluster_id)


# ─────────────────────────────────────────────────────────────────────────────
# Validate
# ─────────────────────────────────────────────────────────────────────────────


def validate_yaml_text(text: str) -> tuple[bool, list[str]]:
    """Valida string YAML completo. Devuelve (ok, errors[])."""
    errors: list[str] = []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return False, [f"YAML parse error: {exc}"]

    if not isinstance(data, dict):
        return False, ["Root debe ser un dict con clave 'clusters'."]

    schema_errors = sorted(_validator.iter_errors(data), key=lambda e: e.path)
    for err in schema_errors:
        loc = ".".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{loc}: {err.message}")

    # Custom sanity: cluster ids deben ser snake_case
    if isinstance(data, dict) and isinstance(data.get("clusters"), dict):
        for cid in data["clusters"].keys():
            if not cid.replace("_", "").isalnum() or not cid[0].isalpha():
                errors.append(f"cluster id '{cid}': debe ser snake_case (a-z, 0-9, _).")

    return (len(errors) == 0), errors


# ─────────────────────────────────────────────────────────────────────────────
# Write (siempre con backup)
# ─────────────────────────────────────────────────────────────────────────────


def _backup_path() -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    config.ensure_dirs()
    return config.BACKUPS_DIR / f"clusters.yaml.bak-{ts}"


def save_clusters_yaml(text: str) -> dict[str, Any]:
    """Valida + backup + write. Devuelve {ok, backup_path, errors[]}."""
    ok, errors = validate_yaml_text(text)
    if not ok:
        return {"ok": False, "errors": errors, "backup_path": None}

    # Backup primero (incluso si destino no existe — entonces backup vacío skip)
    backup_path = None
    if config.CLUSTERS_YAML.exists():
        backup_path = _backup_path()
        shutil.copy2(config.CLUSTERS_YAML, backup_path)

    # Write atómico (write to tmp, rename)
    tmp = config.CLUSTERS_YAML.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(config.CLUSTERS_YAML)

    return {"ok": True, "errors": [], "backup_path": str(backup_path) if backup_path else None}


def save_single_cluster(cluster_id: str, cluster_def: dict[str, Any]) -> dict[str, Any]:
    """Actualiza UN cluster + persist completo. Backup + validate."""
    data = load_clusters()
    data.setdefault("clusters", {})[cluster_id] = cluster_def
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return save_clusters_yaml(text)
