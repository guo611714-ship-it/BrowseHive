# Audit V3 — Interface para integradores

Documento canónico de integración del bloque **Observabilidad + Audit Log** del skill-router V3.

Audiencia: coordinator y otros Agents del proyecto V3 (especialmente Agent D que consume el JSONL).

---

## 1. Quick reference

```python
# Desde trigger_v2.py o cualquier hook
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".claude" / "skill-router" / "v3-niveldios" / "audit"))
from logger import log_decision

log_decision({
    "session_id": session_id,
    "hook_event": "UserPromptSubmit",   # | "PreToolUse" | "PostToolUse"
    "prompt_excerpt": user_prompt,       # se trunca a 200 chars + scrub PII automático
    "cwd": str(Path.cwd()),
    "clusters_activated": [{"id": "marketing", "confidence": 0.92, "trigger": "keyword"}],
    "skills_suggested": ["marketing-skills:copywriting"],
    "skill_invoked_in_turn": None,       # rellenar en PostToolUse si LLM llamó Skill tool
    "tool_name": None,                   # rellenar en PreToolUse/PostToolUse
    "tool_blocked": False,               # True si gate bloqueó
    "bypass_used": None,                 # "[raw]" | "[force-tool]" | "[no-skill]" | "[skip-cluster:X]"
    "outcome": "tool_executed",          # ver tabla abajo
})
```

Retorna `bool` (True OK, False fail). **NUNCA lanza** — si la escritura falla, loguea error a stderr y devuelve False.

---

## 2. Schema JSONL canónico

Cada línea del log es un objeto JSON con estos campos:

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ts` | string ISO8601 UTC | sí | Auto-rellenado si no pasa (formato `2026-05-17T11:00:00Z`) |
| `session_id` | string | sí | ID de la sesión Claude Code (env `CLAUDE_SESSION_ID` o similar) |
| `hook_event` | string | sí | `UserPromptSubmit` \| `PreToolUse` \| `PostToolUse` \| `SessionStart` \| `SessionEnd` |
| `prompt_excerpt` | string | recomendado | Primeros 200 chars del prompt user. **Se trunca y se scrubean tokens automáticamente** |
| `cwd` | string | sí | Working directory del hook (`os.getcwd()`) |
| `clusters_activated` | array | sí | `[{id, confidence, trigger}]` — qué clusters detectó el router |
| `skills_suggested` | array[str] | sí | Skills inyectadas en el reminder |
| `skill_invoked_in_turn` | string \| null | en PostToolUse | Nombre de la skill que el LLM llamó vía Skill tool (`null` si no llamó) |
| `tool_name` | string \| null | en PreToolUse/PostToolUse | Nombre del tool ejecutado (`Bash`, `Edit`, `Write`, etc.) |
| `tool_blocked` | bool | sí | `True` si el gate bloqueó la ejecución del tool |
| `bypass_used` | string \| null | sí | Token bypass usado por el CEO (ver tabla §3) |
| `outcome` | string | sí | Resultado final del turn (ver tabla §4) |

### Sub-objeto `clusters_activated[i]`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string | ID del cluster (`marketing`, `engineering`, `cks`, etc.) |
| `confidence` | float [0,1] | Confianza del match (1.0 = keyword exacto, <1.0 = semántico) |
| `trigger` | string | `keyword` \| `path` \| `command` \| `semantic` |

---

## 3. Bypass tokens (valores de `bypass_used`)

| Token | Significado |
|---|---|
| `[raw]` | CEO desactiva router para este prompt completo |
| `[no-skill]` | CEO permite ejecutar sin pasar por skill sugerida |
| `[force-tool]` | CEO fuerza ejecución de tool aunque gate quiera bloquear |
| `[skip-cluster:X]` | CEO desactiva un cluster específico para este prompt |
| `null` | No se usó bypass (caso normal) |

---

## 4. Outcomes (valores de `outcome`)

| Outcome | Cuándo |
|---|---|
| `tool_executed` | Tool corrió sin gate intervention |
| `tool_blocked` | Gate bloqueó la ejecución |
| `skill_invoked_then_tool` | LLM llamó Skill tool ANTES del tool (caso ideal) |
| `warning_grace` | Gate dio warning + dejó pasar (modo no-strict / grace period) |
| `bypass_executed` | Tool corrió porque hubo bypass |
| `no_op` | Hook se ejecutó pero no hizo nada (prompt trivial, etc.) |

---

## 5. Storage layout

```
~/.claude/skill-router/v3-niveldios/audit/
├── log/
│   ├── 2026-05-17.jsonl     ← 1 fichero por día (UTC)
│   ├── 2026-05-18.jsonl
│   └── ...                  ← retención 90 días (auto-prune en cada write)
├── logger.py
├── stats.py
├── bin/router-stats         ← ejecutable bash
├── tests/
└── INTERFACE.md
```

- **Rotación:** automática por nombre de fichero (`YYYY-MM-DD.jsonl`)
- **Retención:** 90 días, auto-prune en cada `log_decision()` (cheap, idempotente)
- **Concurrencia:** `fcntl.LOCK_EX` (POSIX) para append atómico — safe entre hooks paralelos
- **Tamaño esperado:** ~50-200 KB/día según tráfico, ~5-20 MB total tras 90d

---

## 6. PII safety (importante)

Antes de escribir, el logger:

1. **Trunca `prompt_excerpt` a 200 chars** (no se loguea el prompt completo del CEO).
2. **Scrubea secretos visibles** vía regex (sustituye por `[REDACTED]`):
   - JWT (`ey...`)
   - Bearer tokens
   - API keys (`sk-*`, `ghp_*`, `vcp_*`, `github_pat_*`, `AIza*`)
   - Slack tokens (`xox*`)
   - Patrones `api_key=...`

Esto cumple con la regla #8 del CLAUDE.md ("Secretos nunca en git" — y por extensión, ni en logs locales que se mueven entre Mac y VPS).

---

## 7. Queries útiles (jq + bash)

### Top clusters últimos 7 días
```bash
cat ~/.claude/skill-router/v3-niveldios/audit/log/2026-05-*.jsonl | \
  jq -r '.clusters_activated[]? | .id' | sort | uniq -c | sort -rn | head -10
```

### Ghost skills (sugeridas, 0 invocaciones)
```bash
router-stats skills --days 30 | grep GHOST
```

### Prompts que el router no entiende (gaps)
```bash
router-stats gaps --days 14
```

### Hit-rate diario (% de prompts con cluster activado)
```bash
for f in ~/.claude/skill-router/v3-niveldios/audit/log/*.jsonl; do
  date=$(basename "$f" .jsonl)
  total=$(grep -c UserPromptSubmit "$f")
  with_cluster=$(grep UserPromptSubmit "$f" | jq -r 'select(.clusters_activated | length > 0)' | wc -l)
  echo "$date  $with_cluster / $total"
done
```

### Bypass usage frequency
```bash
cat ~/.claude/skill-router/v3-niveldios/audit/log/*.jsonl | \
  jq -r 'select(.bypass_used) | .bypass_used' | sort | uniq -c
```

---

## 8. CLI cheatsheet

```bash
router-stats summary               # vista general 7d
router-stats summary --days 30     # último mes
router-stats clusters              # tabla por cluster
router-stats skills --days 30      # ghost detection
router-stats gaps --days 14        # prompts sin cluster (nuevos cluster candidates)
router-stats gate                  # blocked + bypass + outcomes
```

El binario `router-stats` vive en `~/.claude/skill-router/v3-niveldios/audit/bin/`. Crear symlink en `~/.local/bin/` o `~/bin/` para uso global.

---

## 9. Integración recomendada en `trigger_v2.py`

El logger es **independiente** del `write_log()` actual de V2 (que usa `log.jsonl` flat sin rotación). Recomendación para coordinator:

**Patrón aditivo (no breaking):**

```python
# Mantener write_log() V2 intacto
# Añadir llamada paralela al audit logger V3:

import sys
sys.path.insert(0, str(ROUTER_V2.parent / "v3-niveldios" / "audit"))
try:
    from logger import log_decision as audit_log
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False

def write_log(entry: dict) -> None:
    """Legacy V2 log (no tocar)."""
    # ... código V2 actual ...

def write_audit(entry_v3: dict) -> None:
    """V3 audit log (con rotación + retención + PII scrub)."""
    if AUDIT_AVAILABLE:
        audit_log(entry_v3)
```

Esto garantiza zero regression sobre V2 y permite cutover incremental.

---

## 10. Para Agent D (consumer del JSONL)

Si vas a leer los logs desde otro componente:

```python
from pathlib import Path
import json
from datetime import datetime, timezone

LOG_DIR = Path.home() / ".claude/skill-router/v3-niveldios/audit/log"

def read_recent(days: int = 7):
    """Iterator de entries de últimos N días."""
    for f in sorted(LOG_DIR.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)
```

Schema garantizado estable en V3 (no se removerán campos; sólo se añadirán con default backwards-compatible).

---

## 11. Tests

Suite pytest en `tests/`:

```bash
cd ~/.claude/skill-router/v3-niveldios/audit
./.venv/bin/pytest tests/ -v
```

Tests cubren:
- T1: logger escribe JSONL válido
- T2: rotación diaria por fecha
- T3: retención 90 días
- T4: stats parsea 100 entries fake
- T5: gaps detection
- T6: ghost detection skills
- T7: CLI subcommands retornan exit 0

---

## 12. Contacto / changelog

- v1.0 (2026-05-17): Schema inicial, logger + stats + bin + tests + INTERFACE.
- Autor: Agent observabilidad del proyecto skill-router V3 niveldios.
- Próximo bloque que consume este JSONL: **Agent D** (TBD).
