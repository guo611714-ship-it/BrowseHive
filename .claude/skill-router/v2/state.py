"""
state.py — Persistencia anti-spam del Skill Router V2.

Mantiene estado de qué clusters/skills se han invocado en turnos recientes
para no spamear al usuario re-sugiriendo lo mismo.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Set


STATE_PATH = Path.home() / ".claude" / "skill-router" / "v2" / "state.json"


def _default_state() -> Dict:
    """Factory de estado por defecto. Devuelve copia fresca (no compartida)."""
    return {
        "turn": 0,
        "recent_clusters": [],   # [{cluster, turn, ts}]
        "recent_skills": [],     # [{skill, turn, ts}]
        "llm_cache": {},         # {prompt_hash: {result, ts}}
        "llm_calls_today": 0,
        "llm_calls_today_date": "",
        "llm_total_calls": 0,
        "llm_total_cost_usd": 0.0,
    }


def load_state(path: Path = STATE_PATH) -> Dict:
    """Carga estado, devolviendo defaults si no existe o está corrupto."""
    if not path.exists():
        return _default_state()
    try:
        text = path.read_text()
        if not text.strip():
            return _default_state()
        data = json.loads(text)
        # Asegurar todas las keys (con factory fresco)
        defaults = _default_state()
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, OSError):
        return _default_state()


def save_state(state: Dict, path: Path = STATE_PATH) -> None:
    """Guarda estado, creando directorios si hace falta."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Trim state: max 50 recent items, max 200 cache entries
    state["recent_clusters"] = state.get("recent_clusters", [])[-50:]
    state["recent_skills"] = state.get("recent_skills", [])[-50:]
    if len(state.get("llm_cache", {})) > 200:
        # Drop oldest by ts
        items = sorted(state["llm_cache"].items(), key=lambda x: x[1].get("ts", 0))
        state["llm_cache"] = dict(items[-200:])
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def increment_turn(state: Dict) -> int:
    """Incrementa contador de turno y devuelve nuevo valor."""
    state["turn"] = int(state.get("turn", 0)) + 1
    return state["turn"]


def is_recently_invoked(skill: str, state: Dict, dedup_turns: int = 5) -> bool:
    """¿Esta skill se invocó hace menos de `dedup_turns` turnos?"""
    current = state.get("turn", 0)
    for entry in state.get("recent_skills", []):
        if entry.get("skill") == skill:
            if current - entry.get("turn", 0) < dedup_turns:
                return True
    return False


def is_cluster_recently_invoked(cluster: str, state: Dict, dedup_turns: int = 5) -> bool:
    """¿Este cluster completo se invocó hace menos de `dedup_turns` turnos?"""
    current = state.get("turn", 0)
    for entry in state.get("recent_clusters", []):
        if entry.get("cluster") == cluster:
            if current - entry.get("turn", 0) < dedup_turns:
                return True
    return False


def record_invocation(cluster: str, skills: List[str], state: Dict) -> None:
    """Registra que se invocó este cluster con estas skills en el turno actual."""
    current = state.get("turn", 0)
    ts = int(time.time())
    state.setdefault("recent_clusters", []).append({
        "cluster": cluster,
        "turn": current,
        "ts": ts,
    })
    for skill in skills:
        state.setdefault("recent_skills", []).append({
            "skill": skill,
            "turn": current,
            "ts": ts,
        })


def filter_unrecent_skills(skills: List[str], state: Dict, dedup_turns: int = 5) -> List[str]:
    """Devuelve solo skills que NO se invocaron recientemente."""
    return [s for s in skills if not is_recently_invoked(s, state, dedup_turns)]


def cache_llm_result(prompt_hash: str, result: Dict, state: Dict, ttl: int = 3600) -> None:
    """Cachea resultado del LLM por TTL segundos (default 1h)."""
    state.setdefault("llm_cache", {})[prompt_hash] = {
        "result": result,
        "ts": int(time.time()),
        "ttl": ttl,
    }


def get_cached_llm_result(prompt_hash: str, state: Dict) -> Dict | None:
    """Recupera resultado cacheado si aún es válido (no expiró)."""
    entry = state.get("llm_cache", {}).get(prompt_hash)
    if not entry:
        return None
    age = int(time.time()) - entry.get("ts", 0)
    ttl = entry.get("ttl", 3600)
    # ttl=0 → expira al instante (testing). >= en lugar de > para garantizar expiración.
    if ttl == 0 or age >= ttl:
        return None
    return entry.get("result")


def increment_llm_counter(state: Dict, cost_usd: float = 0.0) -> None:
    """Incrementa contadores de uso del LLM (para tracking de coste)."""
    today = time.strftime("%Y-%m-%d")
    if state.get("llm_calls_today_date") != today:
        state["llm_calls_today"] = 0
        state["llm_calls_today_date"] = today
    state["llm_calls_today"] = int(state.get("llm_calls_today", 0)) + 1
    state["llm_total_calls"] = int(state.get("llm_total_calls", 0)) + 1
    state["llm_total_cost_usd"] = float(state.get("llm_total_cost_usd", 0.0)) + cost_usd


def activate_skill_gate(cluster: str, gate_skills: List[str], state: Dict) -> None:
    """Activa gate físico: bloquea Bash/Edit/Write hasta que se invoque skill del cluster."""
    state["skill_gate"] = {
        "cluster": cluster,
        "skills": gate_skills,
        "turn": state.get("turn", 0),
        "satisfied": False,
    }


def get_active_gate(state: Dict) -> Dict | None:
    """Devuelve gate activo si no está satisfecho ni expirado."""
    gate = state.get("skill_gate")
    if not gate or gate.get("satisfied"):
        return None
    # Gate expira al cambiar de turno (cada UserPromptSubmit nuevo)
    if state.get("turn", 0) > gate.get("turn", 0):
        state["skill_gate"] = None
        return None
    return gate


def satisfy_gate_if_match(invoked_skill: str, state: Dict) -> bool:
    """Si la skill invocada cierra el gate activo, lo marca satisfecho. Returns True si cerró."""
    gate = state.get("skill_gate")
    if not gate or gate.get("satisfied"):
        return False
    if invoked_skill in gate.get("skills", []):
        gate["satisfied"] = True
        state["skill_gate"] = gate
        return True
    return False


# === GATE GLOBAL SIMPLE (v3 — regla CEO 15-may EOD): ===
# "cualquier mensaje del usuario → invoco skill primero o no toco tools".
# Sin clusters, sin confidence, sin matices. Aplica a TODO turn no-trivial.

def reset_turn_skill_flags(state: Dict, needs_skill: bool = True) -> None:
    """Al inicio de cada turn nuevo: marcar si requiere skill + resetear flag invocada."""
    state["turn_needs_skill"] = bool(needs_skill)
    state["turn_skill_invoked"] = False
    state["turn_auto_satisfied_by_injection"] = False


def mark_skill_invoked_this_turn(state: Dict) -> None:
    """Al ejecutar tool Skill, marcar el turn como satisfecho."""
    state["turn_skill_invoked"] = True


def global_gate_blocks(state: Dict) -> bool:
    """¿El gate global debe bloquear la próxima tool bloqueable?

    Tres formas de NO bloquear:
      1. Turn no requiere skill (trivial / bypass / [force-tool] / [no-skill])
      2. Skill tool ya fue invocada en este turn (turn_skill_invoked=True)
      3. Context Injection cargó el SKILL.md en additionalContext del turn
         (turn_auto_satisfied_by_injection=True)
    """
    if not state.get("turn_needs_skill"):
        return False
    if state.get("turn_skill_invoked"):
        return False
    if state.get("turn_auto_satisfied_by_injection"):
        return False
    return True


def mark_auto_satisfied_by_injection(state: Dict) -> None:
    """Marca el turn como auto-satisfecho por Context Injection (17-may-2026).

    Equivalente a invocar Skill tool, pero implícito: el SKILL.md se cargó
    completo en additionalContext y el LLM lo lee como system context.
    """
    state["turn_skill_invoked"] = True
    state["turn_auto_satisfied_by_injection"] = True
