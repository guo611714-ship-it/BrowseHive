# Skill Router V2

Hook system que matchea cada `UserPromptSubmit` y `PreToolUse` contra un catálogo
de clusters semánticos (Gemini Flash + regex fallback) y sugiere/exige skills
relevantes antes de tocar Bash/Edit/Write.

Vive en `~/.claude/skill-router/v2/` y se enchufa en `~/.claude/settings.json`:

```json
"hooks": {
  "UserPromptSubmit": [{"hooks": [{"type": "command",
    "command": "/Users/<you>/.claude/skill-router/v2/trigger_v2.py --hook UserPromptSubmit"}]}],
  "PreToolUse": [{"hooks": [{"type": "command",
    "command": "/Users/<you>/.claude/skill-router/v2/trigger_v2.py --hook PreToolUse"}]}]
}
```

## Componentes

| Fichero | Rol |
|---|---|
| `trigger_v2.py` | Entrada del hook. Lee stdin → matchea → escribe JSON al stdout. |
| `clusters.yaml` | Catálogo canónico de 20+ clusters (skills + triggers + gates). |
| `llm_match.py` | Cliente Gemini Flash 2.0 con cache 1h por prompt-hash. |
| `state.py` | Persistencia anti-spam + cache LLM + gate state. |
| `marketplace.py` | Auto-detección skills instaladas (~/.claude/skills/ + plugins/cache/). |
| `state.json` | Estado runtime (turn counter, recent skills/clusters, cache). |
| `state/gate_grace.json` | Grace counter per-session+cluster para gate C2. |
| `log.jsonl` | Append-only log JSON estructurado de cada hook. |
| `tests/` | Tests unitarios + E2E Fase 1 (`test_phase1_e2e.py`). |

## Fase 1 quirúrgica (17-may-2026)

### Clusters añadidos

- `code_implementation` — paths `src/app/**/*.tsx`, `src/components/**`, etc. Gate suave.
- `commit_push_pr` — commands `git commit`, `git push`, `gh pr create|merge`. Gate hard.
- `agent_dispatch_bg` — `tool_match` para Agent con `run_in_background=true`. Gate hard.

### PreToolUse extendido (campos `tool_input`)

- `tool_input.file_path` → matchea contra `cluster.paths[]`
- `tool_input.command` → matchea contra `cluster.commands[]`
- `tool_name` + `tool_input.<criterio>` → matchea contra `cluster.tool_match[]`

### Gate grace period C2

Cuando un cluster con `gate: true` se activa por tool call (path/command/tool_match):
1. **1ª llamada:** Warning + `permissionDecision: allow` (cortesía).
2. **2ª+ llamada del mismo cluster sin invocar skill del cluster:** `permissionDecision: deny`.
3. **Invocar skill del cluster:** `_grace_clear()` borra el counter; siguientes calls del mismo cluster reabren el ciclo.
4. **TTL configurable:** `settings.gate_grace_ttl_seconds` (default 300s, 5 min).

Bypass: `[force-tool]` al inicio del prompt del usuario desactiva needs_skill en el turn.

### Reminders operativos

Cada cluster puede declarar `gate_reminder: |` en el YAML. Texto multilinea que se
inyecta tras el listado de skills (en UserPromptSubmit Y en PreToolUse), recordando
memorias críticas: kommo SOLO LECTURA, disciplina de secretos, etc.

### Multi-proyecto: `clusters.local.yaml`

Si en el `cwd` (o cualquier ancestor bajo HOME) existe el fichero:

```
<repo>/.claude/skill-router/clusters.local.yaml
```

…sus clusters se MERGEAN al base. Reglas:
- Mismo `id` → reemplaza completo (local wins).
- `id` nuevo → añade.
- `settings` puntuales pueden sobrescribirse (e.g., `gate_grace_ttl_seconds`).

Ejemplo: `~/Desktop/OPENCLAW/.claude/skill-router/clusters.local.yaml` añade
`vps_ssh` (gate hard sobre `ssh root@your.vps.ip`),
`openclaw_config_edit` (soft sobre `config/SOUL.*.md`),
`openclaw_adr` (soft sobre `docs/decisiones/ADR-*.md`).

## Comandos útiles

```bash
# Estado del router (clusters cargados, API key, settings, sources)
python3 ~/.claude/skill-router/v2/trigger_v2.py --status

# Forzar reset del grace (debug)
rm -f ~/.claude/skill-router/v2/state/gate_grace.json

# Tail logs
tail -f ~/.claude/skill-router/v2/log.jsonl | jq .

# Tests E2E Fase 1
python3 ~/.claude/skill-router/v2/tests/test_phase1_e2e.py
python3 ~/.claude/skill-router/v2/tests/test_phase1_e2e.py --verbose
```

## Bypass strings (prompt usuario)

| String | Efecto |
|---|---|
| `[raw]` (al inicio) | Skip total del router para este prompt. |
| `[no-skill]` | Marca turn como `needs_skill=False` — no exige skill. |
| `[force-tool]` (al inicio) | Permite tools directas, sin gate global. (Cluster-gate sigue activo pero solo warning, no deny.) |
| `[skip-cluster:<name>]` | Ignora la activación del cluster `<name>` para este prompt. |

Variables de entorno:
- `SKILL_ROUTER_OFF=1` → bypass completo.
- `SKILL_ROUTER_VERSION=1` → vuelve a router V1 (regex puro).
- `GEMINI_API_KEY=...` → cliente LLM (también detecta `.env` files).

## Backups y rollback

Cada cambio sustancial crea un backup en `~/.claude/skill-router/v2.bak-YYYY-MM-DD-HHMMSS/`.

Para rollback:
```bash
cp ~/.claude/skill-router/v2.bak-<TIMESTAMP>/{trigger_v2.py,clusters.yaml} \
   ~/.claude/skill-router/v2/
```
