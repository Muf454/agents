#!/usr/bin/env bash
# Shared by the toolkit scripts and their copies in .ai/bin/.
set -euo pipefail
AI_BIN=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Remove the liveness marker only if this process owns it (a rejected second process
# must never erase a live pipeline's marker).
ai_drop_marker() {
  [[ -n "${AI_PIPELINE_MARKER:-}" && "$(cat -- "$AI_PIPELINE_MARKER" 2>/dev/null)" == "$$" ]] || return 0
  rm -f -- "$AI_PIPELINE_MARKER"
}
ai_die() {
  printf 'Error: %s\n' "$*" >&2
  # Last error for the pipeline/notifications; best effort, never fatal.
  [[ -d .ai/local ]] && printf '%s\n' "$*" > .ai/local/last-error 2>/dev/null || true
  if [[ -n "${AI_PIPELINE_MARKER:-}" ]]; then
    # The pipeline shell itself is stopping for good: say so unless stop() already did.
    [[ -n "${AI_STOP_NOTIFIED:-}" ]] || ai_notify "⛔ STOPPED, needs you: $*"
    AI_STOP_NOTIFIED=1
    # A reported stop is not a crash: drop ai-pipeline's liveness marker (see ai-watchdog).
    ai_drop_marker
  fi
  # Tells ai-watchdog this stop was announced (written after last-error, so it is newer).
  [[ -z "${AI_STOP_NOTIFIED:-}" ]] || touch .ai/local/last-error.notified 2>/dev/null || true
  exit 1
}

# Optional per-user settings: ${XDG_CONFIG_HOME:-~/.config}/ai-toolkit/config with
# KEY=value lines. Only known keys are read (never sourced); environment wins.
ai_config() {
  # A recovery resume runs with the approved run's settings only (restored by ai-recover).
  [[ -z "${AI_SETTINGS_FROM_MANIFEST:-}" ]] || return 0
  local file="${XDG_CONFIG_HOME:-$HOME/.config}/ai-toolkit/config" line key value
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^(AI_[A-Z_]+)=(.*)$ ]] || continue
    key=${BASH_REMATCH[1]} value=${BASH_REMATCH[2]}
    case "$key" in AI_NOTIFY_CMD|AI_LIMIT_RETRY|AI_LIMIT_MAX_WAIT|AI_MODEL|AI_REVIEW_MODEL|AI_REVIEW_EFFORT|AI_RECHECK_EFFORT|AI_AUTO_RECOVER|AI_RECOVER_MAX|AI_REVIEWER|AI_CLAUDE_REVIEW_MODEL|AI_CLAUDE_REVIEW_EFFORT|AI_DIAGNOSIS_MODEL|AI_SUPERVISE|AI_SUPERVISE_PLAN_ROUNDS|AI_SUPERVISE_ESCALATE_ROUND|AI_SUPERVISE_ESCALATE_MODEL) ;; *) continue ;; esac
    [[ -z "${!key+x}" ]] || continue
    if [[ "$value" =~ ^\"(.*)\"$ || "$value" =~ ^\'(.*)\'$ ]]; then value=${BASH_REMATCH[1]}; fi
    printf -v "$key" '%s' "$value"
    export "${key?}"
  done < "$file"
}
ai_config

# Supervisor settings: defaults, validation, and export of the validated values so child
# scripts never see a raw or unset value. Call before any agent runs.
ai_supervise_settings() {
  AI_SUPERVISE=${AI_SUPERVISE-1}
  AI_SUPERVISE_PLAN_ROUNDS=${AI_SUPERVISE_PLAN_ROUNDS-3}
  AI_SUPERVISE_ESCALATE_ROUND=${AI_SUPERVISE_ESCALATE_ROUND-3}
  AI_SUPERVISE_ESCALATE_MODEL=${AI_SUPERVISE_ESCALATE_MODEL-claude-fable-5-1}
  [[ "$AI_SUPERVISE" =~ ^[01]$ ]] || ai_die "Invalid AI_SUPERVISE: $AI_SUPERVISE (0 or 1)"
  [[ "$AI_SUPERVISE_PLAN_ROUNDS" =~ ^[0-9]$ ]] || \
    ai_die "Invalid AI_SUPERVISE_PLAN_ROUNDS: $AI_SUPERVISE_PLAN_ROUNDS (0-9)"
  [[ "$AI_SUPERVISE_ESCALATE_ROUND" =~ ^[1-9]$ ]] || \
    ai_die "Invalid AI_SUPERVISE_ESCALATE_ROUND: $AI_SUPERVISE_ESCALATE_ROUND (1-9)"
  [[ "$AI_SUPERVISE_ESCALATE_MODEL" =~ ^[A-Za-z0-9._:-]{1,64}$ ]] || \
    ai_die "Invalid AI_SUPERVISE_ESCALATE_MODEL: $AI_SUPERVISE_ESCALATE_MODEL"
  export AI_SUPERVISE AI_SUPERVISE_PLAN_ROUNDS AI_SUPERVISE_ESCALATE_ROUND AI_SUPERVISE_ESCALATE_MODEL
}

# Codex review model/effort: reviews are where a stronger model pays off most.
# AI_REVIEW_MODEL (default: Codex's own default) and AI_REVIEW_EFFORT (default high).
# Optional arguments name another effort setting and its default (re-check: AI_RECHECK_EFFORT medium).
ai_review_args() {
  local setting=${1:-AI_REVIEW_EFFORT} effort
  effort=${!setting:-${2:-high}}
  [[ "$effort" =~ ^(low|medium|high|xhigh|max)$ ]] || ai_die "Invalid $setting: $effort"
  AI_REVIEW_ARGS=(-c "model_reasoning_effort=\"$effort\"")
  if [[ -n "${AI_REVIEW_MODEL:-}" ]]; then
    [[ "$AI_REVIEW_MODEL" =~ ^[A-Za-z0-9._-]+$ ]] || ai_die "Invalid AI_REVIEW_MODEL: $AI_REVIEW_MODEL"
    AI_REVIEW_ARGS+=(--model "$AI_REVIEW_MODEL")
  fi
}

# Notification hook: AI_NOTIFY_CMD runs via bash with the message as $1
# (e.g. curl -s -d "$1" ntfy.sh/<topic>). Failures never affect the workflow.
ai_notify() {
  local project
  project=$(basename -- "${AI_ROOT:-$PWD}")
  if [[ -n "${AI_NOTIFY_CMD:-}" ]]; then
    timeout 20 bash -c "$AI_NOTIFY_CMD" ai-notify "[$project] $*" </dev/null >/dev/null 2>&1 || true
  fi
  # Kept locally as well (read by ai-dashboard), also when nothing is sent.
  ai_notify_log "[$project] $*"
}

# Usage-limit pause: wait until the provider's reset (or AI_LIMIT_RETRY seconds when
# unknown), bounded by AI_LIMIT_MAX_WAIT total seconds per command. AI_SLEEP is for tests.
AI_WAITED=0
ai_limit_pause() {
  local agent=$1 reset=$2 now wait until
  local max=${AI_LIMIT_MAX_WAIT:-28800} retry=${AI_LIMIT_RETRY:-1800}
  now=$(date +%s)
  if (( reset > now )); then wait=$(( reset - now + 60 )); else wait=$retry; fi
  (( AI_WAITED + wait <= max )) || \
    ai_die "$agent usage limit: the reset is beyond the ${max}s wait budget. Rerun after it resets."
  until=$(date -d "@$(( now + wait ))" '+%a %H:%M')
  printf '%s usage limit reached; pausing %ss (until %s), then resuming.\n' "$agent" "$wait" "$until"
  # Pauses go to an ignored local log: touching tracked files would dirty the checkpoint.
  [[ -d .ai/local ]] && printf '%s paused %ss: %s usage limit (resume ~%s)\n' \
    "$(date -u +%FT%TZ)" "$wait" "$agent" "$until" >> .ai/local/pauses.log
  ai_notify "⏸ PAUSED: $agent usage limit reached. Resumes by itself around $until."
  ai_observe pause "$agent until $until"
  ${AI_SLEEP:-sleep} "$wait"
  ai_observe resume
  AI_WAITED=$(( AI_WAITED + wait ))
}
ai_root() {
  AI_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ai_die 'Run inside a Git project.'
  cd -- "$AI_ROOT"
  [[ -d .ai && ! -L .ai ]] || ai_die 'Missing/unsafe .ai directory; run setup-project.'
  python3 "$AI_BIN/lib/workflow.py" paths "$AI_ROOT"
  mkdir -p .ai/local
}
ai_helper() { python3 "$AI_BIN/lib/workflow.py" "$@"; }
ai_guard_digest() {
  # Inline verifier is loaded before Claude starts. Never ask a potentially
  # modified project helper to verify its own integrity.
  python3 -I - <<'PY'
import hashlib
from pathlib import Path
import stat
import sys

digest = hashlib.sha256()
roots = ('.ai/validate', '.ai/ci-setup', '.ai/bin', '.ai/prompts',
         '.ai/permissions.allow', '.claude/settings.json',
         '.github/workflows/ai-validate.yml')
optional = ('.claude/settings.json', '.github/workflows/ai-validate.yml')
try:
    for name in roots:
        root = Path(name)
        for parent in (root, *root.parents):
            if parent.is_symlink():
                raise ValueError(f'Protected workflow path is a symlink: {parent}')
        paths = [root]
        if root.is_dir():
            paths += sorted(root.rglob('*'))
        for path in paths:
            digest.update(str(path).encode() + b'\0')
            if not path.exists():
                if name not in optional or path != root:
                    raise ValueError(f'Missing protected workflow path: {path}')
                digest.update(b'absent\0')
                continue
            mode = path.lstat().st_mode
            digest.update(str(mode).encode() + b'\0')
            if stat.S_ISREG(mode):
                digest.update(path.read_bytes())
            elif not stat.S_ISDIR(mode):
                raise ValueError(f'Protected workflow path is not a regular file/directory: {path}')
            digest.update(b'\0')
    print(digest.hexdigest())
except (OSError, ValueError) as error:
    print(f'Error: {error}', file=sys.stderr)
    sys.exit(1)
PY
}
# Never run a project helper after the approved gate changed: AI_GATE_BROKEN (a plain shell
# variable, never exported, never set inside a command substitution) makes the observation
# and notification-log helpers below skip themselves for the rest of this shell.
# Usage: ai_gate_check GATE. An unreadable digest counts as broken.
ai_gate_check() {
  local actual
  if actual=$(ai_guard_digest 2>/dev/null) && [[ "$actual" == "$1" ]]; then return 0; fi
  AI_GATE_BROKEN=1
  return 1
}
ai_guard_verify() {
  local actual
  actual=$(ai_guard_digest) || { AI_GATE_BROKEN=1; ai_die 'Approved workflow gate is missing or unsafe; inspect changes.'; }
  [[ "$actual" == "$AI_APPROVED_GATE" ]] || { AI_GATE_BROKEN=1
    ai_die 'Approved workflow gate changed during this run. Stop, inspect the diff, and explicitly reapprove before resuming.'; }
}
# Dashboard records (best effort, never fatal); skipped once the gate is known bad.
ai_observe() {
  [[ -z "${AI_GATE_BROKEN:-}" ]] || return 0
  ai_helper observe "$@" || true
}
ai_notify_log() {
  [[ -z "${AI_GATE_BROKEN:-}" ]] || return 0
  python3 -B "$AI_BIN/lib/workflow.py" notify-log "${AI_ROOT:-$PWD}" "$1" 2>/dev/null || true
}
# Host-side dependency install (FL-01): run .ai/ci-setup when deps-status says stale.
# Usage: ai_deps EXPECTED_GATE LIMIT_SECONDS. Returns 1 with AI_DEPS_ERROR set (every
# message starts with "Dependency setup", which ai-recover always escalates). The installer
# may only add ignored files: the gate and the tree snapshot must be unchanged afterwards,
# checked after every exit and reported before the exit status. Writes no tracked file.
ai_deps() {
  local gate=$1 limit=$2 status before after code log started
  AI_DEPS_ERROR=''
  if ! status=$(ai_helper deps-status 2>&1); then
    AI_DEPS_ERROR="Dependency setup (.ai/ci-setup): ${status#Error: }"; return 1
  fi
  [[ "$status" == stale* ]] || return 0
  printf 'Dependency setup (.ai/ci-setup): %s\n' "${status#stale }"
  if ! [[ "$limit" =~ ^-?[0-9]+$ ]] || (( limit <= 0 )); then
    AI_DEPS_ERROR='Dependency setup (.ai/ci-setup) not run: run time limit reached.'; return 1
  fi
  if ! before=$(ai_helper tree-snapshot 2>&1); then
    AI_DEPS_ERROR="Dependency setup: cannot snapshot the checkout: ${before#Error: }"; return 1
  fi
  log=$(mktemp .ai/local/deps-XXXXXXXX.log)
  started=$SECONDS
  set +e
  timeout --signal=TERM --kill-after=10s "$limit" bash .ai/ci-setup < /dev/null > "$log" 2>&1
  code=$?
  set -e
  if ! ai_gate_check "$gate"; then
    AI_DEPS_ERROR="Dependency setup (.ai/ci-setup) changed the approved workflow gate; see $log"
  elif ! after=$(ai_helper tree-snapshot 2>&1) || [[ "$after" != "$before" ]]; then
    AI_DEPS_ERROR="Dependency setup changed project files (.ai/ci-setup must only install ignored dependencies); see $log"
  elif (( code != 0 )); then
    AI_DEPS_ERROR="Dependency setup (.ai/ci-setup) failed (exit $code"
    (( code != 124 && code != 137 )) || AI_DEPS_ERROR+=", timeout after ${limit}s"
    AI_DEPS_ERROR+="); see $log"
  elif ! after=$(ai_helper deps-record 2>&1); then
    AI_DEPS_ERROR="Dependency setup: cannot record the stamp: ${after#Error: }"
  fi
  if [[ -n "$AI_DEPS_ERROR" ]]; then
    tail -n 5 -- "$log" | sed 's/^/  | /'
    return 1
  fi
  printf 'Dependencies installed in %ss (log %s).\n' "$(( SECONDS - started ))" "$log"
}
ai_lock() {
  # One writer/reviewer per checkout. Kernel releases locks on exit or crash.
  # ai-pipeline holds this lock for its whole run; its direct children skip it.
  if [[ -n "${AI_LOCK_HELD:-}" && "$AI_LOCK_HELD" == "$PPID" ]]; then return 0; fi
  # ai-pipeline <-> ai-recover hand over by exec: same PID, lock still held on fd 9.
  if [[ "${AI_LOCK_HELD:-}" == "$$" && -e /proc/$$/fd/9 ]] && flock -n 9; then return 0; fi
  exec 9>.ai/local/workflow.lock
  if ! flock -n 9; then
    # A second recovery must not overwrite the real stop reason in last-error.
    [[ -z "${AI_LOCK_QUIET:-}" ]] || { printf '%s\n' 'Another runner owns this checkout; nothing to recover.' >&2; exit 1; }
    ai_die 'Another runner/reviewer owns this checkout.'
  fi
}
ai_branch() {
  local branch
  branch=$(git symbolic-ref --quiet --short HEAD) || ai_die 'Detached HEAD; use a feature branch.'
  case "$branch" in main|master|develop|development|production|release|release/*)
    ai_die "Refusing autonomous implementation on protected branch: $branch" ;;
  esac
  [[ "$branch" == "$AI_START_BRANCH" ]] || ai_die 'Branch changed during the run.'
}
ai_log() {
  # Arguments are toolkit-controlled concise values, not raw model output.
  printf '| %s | runner | %s | %s | %s | %s | %s |\n' \
    "$(date -u +%FT%TZ)" "$1" "$2" "$3" \
    "$(git rev-parse --short HEAD 2>/dev/null || printf none)" "$4" >> .ai/run-log.md
}
