"""Generador de audit log mock para tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _entry(
    ts: datetime,
    *,
    prompt: str = "test",
    clusters: list[dict] | None = None,
    skills_suggested: list[Any] | None = None,
    skill_invoked: str | None = None,
    bypass: str | None = None,
    tool: str | None = None,
) -> dict[str, Any]:
    return {
        "ts": ts.isoformat(),
        "session_id": "sess-mock",
        "hook_event": "UserPromptSubmit",
        "prompt_excerpt": prompt,
        "cwd": "/tmp/test",
        "clusters_activated": clusters or [],
        "skills_suggested": skills_suggested or [],
        "skill_invoked_in_turn": skill_invoked,
        "tool_name": tool,
        "tool_blocked": False,
        "bypass_used": bypass,
        "outcome": "ok",
    }


def build_mock_log(target_dir: Path, *, scenario: str = "default") -> None:
    """Crea ficheros YYYY-MM-DD.jsonl con entries simuladas.

    Escenarios:
      'default'  — mezcla con ghosts, cold, gaps, fp, friction
      'empty'    — sin entries
      'sparse'   — pocas entries (cold-only)
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    if scenario == "empty":
        return

    entries_per_day: list[tuple[int, list[dict]]] = []

    if scenario == "sparse":
        for d in range(14):
            day = now - timedelta(days=d)
            es: list[dict] = []
            if d < 3:
                es.append(
                    _entry(
                        day,
                        prompt="run financial report",
                        clusters=[{"id": "finance", "confidence": 0.8, "trigger": "financial"}],
                        skills_suggested=["finance-saas-metrics-coach"],
                        skill_invoked="finance-saas-metrics-coach",
                    )
                )
            entries_per_day.append((d, es))
    else:  # default
        for d in range(14):
            day = now - timedelta(days=d)
            es: list[dict] = []
            # marketing: bien (muchas activaciones, skill invocada)
            for _ in range(2):
                es.append(
                    _entry(
                        day,
                        prompt="ayuda con copywriting de landing",
                        clusters=[{"id": "marketing", "confidence": 0.9, "trigger": "marketing"}],
                        skills_suggested=["marketing-copywriting", "marketing-content-creator"],
                        skill_invoked="marketing-copywriting",
                    )
                )
            # finance: cluster sugiere skill, LLM nunca invoca (false positive)
            for _ in range(2):
                es.append(
                    _entry(
                        day,
                        prompt="estado de cuentas",
                        clusters=[{"id": "finance", "confidence": 0.85, "trigger": "cuentas"}],
                        skills_suggested=["finance-business-investment-advisor"],
                        skill_invoked=None,
                    )
                )
            # engineering: muy poco usado (cold)
            if d == 0:
                es.append(
                    _entry(
                        day,
                        prompt="revisa este código",
                        clusters=[{"id": "engineering", "confidence": 0.7, "trigger": "código"}],
                        skills_suggested=["code-review"],
                        skill_invoked="code-review",
                    )
                )
            # security: gate bypassed siempre (friction)
            if d < 5:
                es.append(
                    _entry(
                        day,
                        prompt="ejecuta este comando",
                        clusters=[{"id": "security", "confidence": 0.95, "trigger": "ejecuta"}],
                        skills_suggested=["security-review"],
                        skill_invoked=None,
                        bypass="[force-tool]",
                    )
                )
            # gap queries: prompt no matcheado, repetido
            if d < 5:
                es.append(
                    _entry(
                        day,
                        prompt="abre el panel del jardín de skills",
                        clusters=[],
                        skills_suggested=[],
                    )
                )
            entries_per_day.append((d, es))

    for d, entries in entries_per_day:
        day = now - timedelta(days=d)
        f = target_dir / f"{day.strftime('%Y-%m-%d')}.jsonl"
        with f.open("w", encoding="utf-8") as fp:
            for e in entries:
                fp.write(json.dumps(e, ensure_ascii=False) + "\n")


def build_clusters_yaml(target: Path, *, include_ghost: bool = True) -> None:
    """Crea un clusters.yaml mínimo para tests."""
    import yaml  # type: ignore

    data = {
        "clusters": {
            "marketing": {
                "description": "marketing y copy",
                "skills": ["marketing-copywriting", "marketing-content-creator"],
            },
            "finance": {
                "description": "finanzas",
                "skills": ["finance-business-investment-advisor", "finance-saas-metrics-coach"],
            },
            "engineering": {
                "description": "ingenieria",
                "skills": ["code-review", "engineering:debug"],
            },
            "security": {
                "description": "seguridad",
                "skills": ["security-review"],
            },
            "dead_zone": {
                "description": "nadie activa esto",
                "skills": ["dead-skill-1"] if include_ghost else [],
            },
        }
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(data, fp, allow_unicode=True, sort_keys=False)
