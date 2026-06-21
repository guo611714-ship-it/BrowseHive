#!/usr/bin/env bash
# Skill Router V3 — router-evolve CLI wrapper.
#
# Uso:
#   router-evolve                    # analiza últimos 14d, persiste report, NO envía Telegram
#   router-evolve --days 7            # ventana 7d
#   router-evolve --dry-run           # solo print, no persist
#   router-evolve --send-telegram     # persiste + envía Telegram al CEO
#
# Variables env:
#   TELEGRAM_BOT_TOKEN  Token del bot (obligatorio si --send-telegram)
#   TELEGRAM_CHAT_ID    Chat ID destino (default 662454777 = David)
#   SKILL_ROUTER_ROOT   Override root (default ~/.claude/skill-router)
#
# Cron sugerido (domingo 21h):
#   0 21 * * 0 ~/.claude/skill-router/v3-niveldios/evolve/bin/router-evolve.sh --send-telegram >> /tmp/router-evolve.log 2>&1

set -euo pipefail

EVOLVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V3_ROOT="$(cd "$EVOLVE_DIR/.." && pwd)"
AUDIT_LOG_DIR="${SKILL_ROUTER_AUDIT_LOG_DIR:-$V3_ROOT/audit/log}"
VENV_PY="$EVOLVE_DIR/venv/bin/python3"
PY="${VENV_PY}"
if [[ ! -x "$PY" ]]; then
    PY="$(command -v python3)"
fi

# Pre-condición: ≥7 días de audit log (o --force)
require_min_days=7
have_days=0
if [[ -d "$AUDIT_LOG_DIR" ]]; then
    have_days="$(find "$AUDIT_LOG_DIR" -maxdepth 1 -name '*.jsonl' -type f 2>/dev/null | wc -l | tr -d ' ')"
fi

# Permite --force para saltarse la pre-condición
force=false
forwarded_args=()
for arg in "$@"; do
    case "$arg" in
        --force)
            force=true
            ;;
        *)
            forwarded_args+=("$arg")
            ;;
    esac
done

if [[ "$force" != "true" ]] && (( have_days < require_min_days )); then
    echo "[router-evolve] WARN: solo $have_days días de audit log (mínimo $require_min_days). Usa --force para forzar." >&2
    echo "[router-evolve] Saliendo sin generar report." >&2
    exit 0
fi

exec "$PY" "$EVOLVE_DIR/propose.py" "${forwarded_args[@]}"
