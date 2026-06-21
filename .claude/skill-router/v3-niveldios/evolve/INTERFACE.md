# Skill Router V3 — Evolve (Agent E)

**Pieza:** Auto-evolución del router. Detecta ghosts, cold clusters, gap queries,
false positives y gate friction desde el audit log JSONL (Agent B) y genera un
report markdown semanal con propuestas concretas para el CEO.

---

## Layout

```
evolve/
├── analyze.py              # detectores puros (5 funciones)
├── propose.py              # render markdown + persist + telegram
├── bin/router-evolve.sh    # CLI wrapper (cron + manual)
├── fixtures/               # mock data generator para tests
├── tests/                  # 16 tests pytest (T1..T7 + robustez)
├── reports/                # YYYY-WNN.md persistidos
├── conftest.py             # pytest sys.path bootstrap
├── INTERFACE.md            # ← este fichero
└── venv/                   # local, no global (rapidfuzz + pyyaml + pytest)
```

---

## Variables de entorno

| Variable | Default | Para qué |
|---|---|---|
| `SKILL_ROUTER_ROOT` | `~/.claude/skill-router` | Override root del router |
| `SKILL_ROUTER_AUDIT_LOG_DIR` | `$ROOT/v3-niveldios/audit/log` | Audit log JSONL (Agent B) |
| `SKILL_ROUTER_CLUSTERS_YAML` | `$ROOT/v2/clusters.yaml` | Cluster registry |
| `SKILL_ROUTER_SKILLS_DIR` | `~/.claude/skills` | Inventario skills instaladas |
| `SKILL_ROUTER_EVOLVE_REPORTS` | `evolve/reports` | Directorio destino |
| `TELEGRAM_BOT_TOKEN` | — | Token del bot OpenClaw (obligatorio `--send-telegram`) |
| `OPENCLAW_BOT_TOKEN` | — | Fallback alternativo si no hay `TELEGRAM_BOT_TOKEN` |
| `TELEGRAM_CHAT_ID` | `662454777` | Chat ID destino (CEO por defecto) |

---

## CLI manual

```bash
# Análisis y persistencia (sin telegram)
~/.claude/skill-router/v3-niveldios/evolve/bin/router-evolve.sh

# Ventana custom
~/.claude/skill-router/v3-niveldios/evolve/bin/router-evolve.sh --days 7

# Dry-run (print stdout, no persist, no telegram)
~/.claude/skill-router/v3-niveldios/evolve/bin/router-evolve.sh --dry-run

# Producción: persist + telegram al CEO
TELEGRAM_BOT_TOKEN=xxx ~/.claude/skill-router/v3-niveldios/evolve/bin/router-evolve.sh --send-telegram

# Forzar pese a tener <7 días de audit log
~/.claude/skill-router/v3-niveldios/evolve/bin/router-evolve.sh --force --dry-run
```

**Pre-condición del wrapper:** ≥7 ficheros en `audit/log/`. Si no, sale sin error
(silencioso). Forzar con `--force`.

---

## Integración cron

Slot sugerido (igual que `cks-weekly-retro-signal` del VPS): **domingo 21h UTC**.

### Opción A — `~/.local/share/cron/` (user-local, no requiere root)

```bash
# crontab -e
0 21 * * 0 TELEGRAM_BOT_TOKEN=$(cat ~/.claude/.secrets/openclaw-bot-token) \
  ~/.claude/skill-router/v3-niveldios/evolve/bin/router-evolve.sh --send-telegram \
  >> ~/.claude/skill-router/v3-niveldios/evolve/cron.log 2>&1
```

### Opción B — `/etc/cron.d/` (sistema, requiere root)

```cron
# /etc/cron.d/router-evolve
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

0 21 * * 0 ${USER} source ~/.claude/.secrets/env && \
  ~/.claude/skill-router/v3-niveldios/evolve/bin/router-evolve.sh --send-telegram \
  >> /var/log/router-evolve.log 2>&1
```

### Opción C — Hosted VPS (run alongside other system crons)

Crear skill `cks-router-evolve.sh` en `/data/.openclaw/workspace/scripts/`
ejecutando el CLI vía SSH o re-implementar el equivalente con el patrón
canónico de `run-skill.sh`. Owner: Agent F del dashboard (TenacitOS) consume
el report rendered.

---

## Dependencia con otros agentes

| Agent | Output que consumo | Qué pasa si no está |
|---|---|---|
| **B (audit)** | `audit/log/YYYY-MM-DD.jsonl` | Detectores devuelven listas vacías. `--force` permite ejecutar igual. |
| **C (embeddings)** | `embeddings.group_similar(prompts, threshold)` opcional | Fallback automático a RapidFuzz `token_set_ratio` (already installed). |
| **F (dashboard)** | — (Agent F me consume a mí) | El dashboard lee `evolve/reports/*.md` para mostrar tendencias. |
| **A (v2)** | — (read-only sobre `v2/clusters.yaml`) | Si v2 cambia, los detectores re-leen yaml en cada run. |

---

## Schema de entry JSONL (Agent B)

```json
{
  "ts": "ISO-8601",
  "session_id": "string",
  "hook_event": "UserPromptSubmit | PreToolUse | ...",
  "prompt_excerpt": "string (≤200 chars, scrubbed)",
  "cwd": "/path",
  "clusters_activated": [{"id": "string", "confidence": 0.X, "trigger": "string"}],
  "skills_suggested": ["string"] | [{"name": "...", "invoked": bool}],
  "skill_invoked_in_turn": "string | null",
  "tool_name": "string | null",
  "tool_blocked": bool,
  "bypass_used": "[force-tool] | null",
  "outcome": "string"
}
```

Tolerancia: líneas corruptas se saltan con WARN stderr. Campos ausentes →
detectores asumen vacío.

---

## Tests

```bash
cd ~/.claude/skill-router/v3-niveldios/evolve
./venv/bin/python -m pytest tests/ -v
```

Estado al cierre Agent E: **16/16 pass** (7 nombrados T1..T7 + 9 de robustez).

Cobertura:
- T1: `detect_ghosts` con audit mock + log vacío
- T2: `detect_cold_clusters` threshold low/high
- T3: `detect_gap_queries` agrupa + filtra por min_repetitions
- T4: `detect_false_positive_clusters` calcula ratio correcto
- T5: `render_report` markdown válido + datos explícitos
- T6: `persist_report` naming `YYYY-WNN.md` + overwrite same week
- T7: `send_telegram` con mock transport + sin token + trunca >4096

---

## Output esperado del cron semanal

1. **Fichero local:** `evolve/reports/YYYY-WNN.md` (~5 KB markdown).
2. **Telegram al CEO** (chat 662454777, Markdown, truncado a 3800 chars).
3. **Stderr log:** `[evolve] report → /path/to/file` + `[evolve] telegram ok status=200`.

Si Telegram falla, el report queda persistido igualmente y `cron.log` registra
el error sin tumbar el run.

---

## Anti-patrones

- ❌ NO ejecutar a mano `analyze.py` esperando ver report — sólo devuelve JSON.
  Para report markdown usar `propose.py` o el CLI wrapper.
- ❌ NO instalar dependencias en el Python global. Usar `venv` local.
- ❌ NO enviar Telegram durante tests. Usar `--dry-run` o el `transport` mock.
- ❌ NO confiar en que Agent C estará disponible — el fallback RapidFuzz es la
  vía canónica si no hay embeddings.
- ❌ NO modificar `clusters.yaml` desde aquí — esto es read-only. Si el report
  propone cambios, los aplica el CEO (manual) o un futuro Agent G (auto-apply
  con human-in-loop).

---

## Cierre

Agent E completo. Sin dependencia hard con B (acepta log vacío) y sin
dependencia hard con C (fallback fuzzy match). Funcional standalone.

CEO puede ver el primer report semanal el primer domingo con ≥7 días de
audit JSONL (Agent B en producción).
