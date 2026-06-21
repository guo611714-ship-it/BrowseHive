#!/usr/bin/env bash
# TDD test for install.sh — RED first, then GREEN.
# Each test asserts ONE behavior; on failure prints diff and exits non-zero.

set -uo pipefail

INSTALL_SH="$(cd "$(dirname "$0")/.." && pwd)/install.sh"
[[ -x "$INSTALL_SH" ]] || { echo "FAIL: install.sh not found or not executable at $INSTALL_SH"; exit 2; }

PASS=0; FAIL=0
section() { printf "\n\033[36m== %s ==\033[0m\n" "$*"; }
ok()      { PASS=$((PASS+1)); printf "  \033[32mPASS\033[0m %s\n" "$*"; }
nope()    { FAIL=$((FAIL+1)); printf "  \033[31mFAIL\033[0m %s\n" "$*"; }

make_sandbox() {
  local sb; sb="$(mktemp -d)"
  mkdir -p "$sb/home/.claude/skill-router/v2"
  # Fake trigger_v2.py so install.sh's existence check passes
  cat > "$sb/home/.claude/skill-router/v2/trigger_v2.py" <<'PY'
#!/usr/bin/env python3
print("{}")
PY
  chmod +x "$sb/home/.claude/skill-router/v2/trigger_v2.py"
  echo "$sb"
}

run_install() {
  local home="$1"
  HOME="$home" ROUTER_DIR="$home/.claude/skill-router" bash "$INSTALL_SH" >"$home/.out" 2>"$home/.err"
  echo $?
}

# ---- T1: fresh install creates settings.json with both hooks -----------------
section "T1: fresh install — creates settings.json with UserPromptSubmit + PreToolUse"
SB=$(make_sandbox)
RC=$(run_install "$SB/home")
if [[ "$RC" != "0" ]]; then
  nope "install.sh exit non-zero (rc=$RC). stderr:"; cat "$SB/home/.err"
else
  ok "install.sh exited 0"
fi
if [[ -f "$SB/home/.claude/settings.json" ]]; then
  ok "settings.json created"
else
  nope "settings.json NOT created"
fi
if python3 -c "import json,sys; d=json.load(open('$SB/home/.claude/settings.json')); assert 'UserPromptSubmit' in d.get('hooks',{}); assert 'PreToolUse' in d.get('hooks',{})" 2>/dev/null; then
  ok "both hooks present in settings.json"
else
  nope "hooks missing from settings.json. content:"; cat "$SB/home/.claude/settings.json" 2>/dev/null
fi

# ---- T2: idempotent — second run does NOT duplicate hooks --------------------
section "T2: idempotent — second run doesn't duplicate hooks"
run_install "$SB/home" >/dev/null
COUNT=$(python3 -c "
import json
d = json.load(open('$SB/home/.claude/settings.json'))
n_ups = len(d.get('hooks',{}).get('UserPromptSubmit', []))
n_pre = len(d.get('hooks',{}).get('PreToolUse', []))
print(f'{n_ups},{n_pre}')
")
if [[ "$COUNT" == "1,1" ]]; then
  ok "still 1 entry per event after re-run ($COUNT)"
else
  nope "duplicates created. counts=$COUNT (expected 1,1)"
fi

# ---- T3: preserves existing unrelated config in settings.json ----------------
section "T3: preserves unrelated keys in settings.json"
SB2=$(make_sandbox)
cat > "$SB2/home/.claude/settings.json" <<'JSON'
{
  "theme": "dark",
  "permissions": {"allow": ["Bash(ls *)"]},
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "/some/other/hook.sh"}]}
    ]
  }
}
JSON
run_install "$SB2/home" >/dev/null
if python3 -c "
import json
d = json.load(open('$SB2/home/.claude/settings.json'))
assert d.get('theme') == 'dark', 'theme lost'
assert 'Bash(ls *)' in d.get('permissions',{}).get('allow',[]), 'permissions lost'
ups = d['hooks']['UserPromptSubmit']
assert len(ups) == 2, f'expected 2 UPS entries (existing + ours), got {len(ups)}'
assert any('/some/other/hook.sh' in str(h) for h in ups), 'existing hook removed'
assert any('skill-router/v2/trigger_v2.py' in str(h) for h in ups), 'router hook not added'
" 2>/dev/null; then
  ok "preserved theme + permissions + existing unrelated hook + added router hook"
else
  nope "config corruption. content:"; cat "$SB2/home/.claude/settings.json"
fi

# ---- T4: prefers settings.local.json if present ------------------------------
section "T4: writes to settings.local.json when present (vs settings.json)"
SB3=$(make_sandbox)
echo '{}' > "$SB3/home/.claude/settings.local.json"
echo '{"keep":"this"}' > "$SB3/home/.claude/settings.json"
run_install "$SB3/home" >/dev/null
if grep -q "trigger_v2.py" "$SB3/home/.claude/settings.local.json" && ! grep -q "trigger_v2.py" "$SB3/home/.claude/settings.json"; then
  ok "wrote to settings.local.json; left settings.json untouched"
else
  nope "wrong target file written"
fi

# ---- T5: fails fast if trigger_v2.py missing ---------------------------------
section "T5: fails with non-zero exit when trigger_v2.py missing"
SB4=$(mktemp -d)
mkdir -p "$SB4/home/.claude"
RC=$(HOME="$SB4/home" ROUTER_DIR="$SB4/home/.claude/skill-router" bash "$INSTALL_SH" >/dev/null 2>"$SB4/err"; echo $?)
if [[ "$RC" != "0" ]]; then
  ok "exited non-zero (rc=$RC) on missing trigger"
else
  nope "should fail when trigger absent, but exited 0"
fi
if grep -qiE "trigger.*not found|not found.*trigger" "$SB4/err" 2>/dev/null; then
  ok "stderr explains missing trigger"
else
  nope "stderr unclear. content:"; cat "$SB4/err"
fi

# ---- T6: state files initialized ---------------------------------------------
section "T6: state.json and state/gate_grace.json initialized"
if [[ -f "$SB/home/.claude/skill-router/v2/state.json" ]] && [[ -f "$SB/home/.claude/skill-router/v2/state/gate_grace.json" ]]; then
  ok "both state files exist"
else
  nope "state files missing"
fi
if python3 -c "import json; json.load(open('$SB/home/.claude/skill-router/v2/state.json'))" 2>/dev/null; then
  ok "state.json is valid JSON"
else
  nope "state.json not valid JSON"
fi

# ---- Summary -----------------------------------------------------------------
section "Summary"
printf "  Passed: \033[32m%d\033[0m   Failed: \033[31m%d\033[0m\n" "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1

# ---- T7 (added post-RED, real failing test): handles missing ~/.claude/ dir ---
# Discovered during honest TDD review: install.sh assumes $HOME/.claude exists.
echo
echo "== T7 (true RED): handles missing ~/.claude/ parent dir ==" >&2
SB5=$(mktemp -d)
mkdir -p "$SB5/home"  # NO .claude subdir
mkdir -p "$SB5/home/.claude/skill-router/v2"
cat > "$SB5/home/.claude/skill-router/v2/trigger_v2.py" <<'PY'
#!/usr/bin/env python3
print("{}")
PY
chmod +x "$SB5/home/.claude/skill-router/v2/trigger_v2.py"
# Now nuke .claude/ to simulate fresh user without Claude Code dir
rm -rf "$SB5/home/.claude"
# Recreate JUST the router dir under it to simulate npx skills add having created it
mkdir -p "$SB5/home/.claude/skill-router/v2"
cat > "$SB5/home/.claude/skill-router/v2/trigger_v2.py" <<'PY'
#!/usr/bin/env python3
print("{}")
PY
chmod +x "$SB5/home/.claude/skill-router/v2/trigger_v2.py"
# But no settings.json AND no .claude/ pre-existing config dir markers
RC=$(HOME="$SB5/home" ROUTER_DIR="$SB5/home/.claude/skill-router" bash "$INSTALL_SH" >"$SB5/out" 2>"$SB5/err"; echo $?)
if [[ "$RC" == "0" ]] && [[ -f "$SB5/home/.claude/settings.json" ]]; then
  echo "  PASS T7: works with fresh ~/.claude/ (no pre-existing settings)"
else
  echo "  FAIL T7: rc=$RC, settings exists? $(test -f "$SB5/home/.claude/settings.json" && echo yes || echo no)"
  cat "$SB5/err"
  exit 1
fi
