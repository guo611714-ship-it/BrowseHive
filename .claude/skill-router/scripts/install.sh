#!/usr/bin/env bash
# install.sh — wire claude-skill-router hooks into Claude Code settings.
# Idempotent: safe to re-run; skips entries already present.

set -euo pipefail

ROUTER_DIR="${ROUTER_DIR:-$HOME/.claude/skill-router}"
TRIGGER="$ROUTER_DIR/v2/trigger_v2.py"
SETTINGS_LOCAL="$HOME/.claude/settings.local.json"
SETTINGS_GLOBAL="$HOME/.claude/settings.json"

err() { printf "\033[31m[install]\033[0m %s\n" "$*" >&2; }
ok()  { printf "\033[32m[install]\033[0m %s\n" "$*"; }
inf() { printf "\033[36m[install]\033[0m %s\n" "$*"; }

# --- 1. Sanity checks ---------------------------------------------------------
command -v python3 >/dev/null 2>&1 || { err "python3 not found in PATH"; exit 1; }
python3 -c "import yaml" 2>/dev/null || {
  err "pyyaml not installed. Run: pip install pyyaml"; exit 1;
}

if [[ ! -f "$TRIGGER" ]]; then
  err "trigger_v2.py not found at $TRIGGER"
  err "Did you run 'npx skills add David-CKS/claude-skill-router@claude-skill-router -g -y'?"
  exit 1
fi
chmod +x "$TRIGGER" 2>/dev/null || true

# --- 2. Pick target settings file --------------------------------------------
if [[ -f "$SETTINGS_LOCAL" ]]; then
  TARGET="$SETTINGS_LOCAL"
elif [[ -f "$SETTINGS_GLOBAL" ]]; then
  TARGET="$SETTINGS_GLOBAL"
else
  TARGET="$SETTINGS_GLOBAL"
  echo '{}' > "$TARGET"
  inf "Created empty $TARGET"
fi
inf "Target settings: $TARGET"

# --- 3. Merge hooks (idempotent, via python+json) -----------------------------
python3 - "$TARGET" "$TRIGGER" <<'PY'
import json, sys
from pathlib import Path

target = Path(sys.argv[1])
trigger = sys.argv[2]
data = json.loads(target.read_text() or "{}")
hooks = data.setdefault("hooks", {})

def already_wired(events, cmd_substr):
    for block in events:
        for h in block.get("hooks", []):
            if cmd_substr in (h.get("command") or ""):
                return True
    return False

for event in ("UserPromptSubmit", "PreToolUse"):
    arr = hooks.setdefault(event, [])
    if already_wired(arr, "skill-router/v2/trigger_v2.py"):
        print(f"[install] hook {event}: already wired (skip)")
        continue
    arr.append({
        "hooks": [{
            "type": "command",
            "command": f"{trigger} --hook {event}"
        }]
    })
    print(f"[install] hook {event}: added")

target.write_text(json.dumps(data, indent=2) + "\n")
PY

# --- 4. Initialize state dirs -------------------------------------------------
mkdir -p "$ROUTER_DIR/v2/state"
[[ -f "$ROUTER_DIR/v2/state.json" ]] || echo '{}' > "$ROUTER_DIR/v2/state.json"
[[ -f "$ROUTER_DIR/v2/state/gate_grace.json" ]] || echo '{}' > "$ROUTER_DIR/v2/state/gate_grace.json"

# --- 5. Report optional features ---------------------------------------------
ok "Router hooks wired."
[[ -d "$ROUTER_DIR/v3-niveldios/audit" ]]     && inf "Optional: audit log enabled ($ROUTER_DIR/v3-niveldios/audit/log/)"
[[ -d "$ROUTER_DIR/v3-niveldios/dashboard" ]] && inf "Optional: dashboard available  — bash $ROUTER_DIR/v3-niveldios/dashboard/bin/router-dashboard start  → http://127.0.0.1:9300"
[[ -d "$ROUTER_DIR/v3-niveldios/evolve" ]]    && inf "Optional: weekly evolve report — bash $ROUTER_DIR/v3-niveldios/evolve/bin/router-evolve.sh --dry-run"
[[ -d "$ROUTER_DIR/v3-niveldios/embeddings" ]] && inf "Optional: embeddings fallback — pip install sentence-transformers faiss-cpu && python3 $ROUTER_DIR/v3-niveldios/embeddings/build_index.py"

ok "Done. Restart Claude Code (or open a new session) to activate the router."
