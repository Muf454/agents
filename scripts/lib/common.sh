#!/usr/bin/env bash
# Shared by the toolkit scripts and their copies in .ai/bin/.
set -euo pipefail
AI_BIN=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ai_die() {
  printf 'Error: %s\n' "$*" >&2
  # Last error for the pipeline/notifications; best effort, never fatal.
  [[ -d .ai/local ]] && printf '%s\n' "$*" > .ai/local/last-error 2>/dev/null || true
  # A reported stop is not a crash: drop ai-pipeline's liveness marker (see ai-watchdog).
  [[ -z "${AI_PIPELINE_MARKER:-}" ]] || rm -f -- "$AI_PIPELINE_MARKER"
  exit 1
}

# Optional per-user settings: ${XDG_CONFIG_HOME:-~/.config}/ai-toolkit/config with
# KEY=value lines. Only known keys are read (never sourced); environment wins.
ai_config() {
  local file="${XDG_CONFIG_HOME:-$HOME/.config}/ai-toolkit/config" line key value
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^(AI_[A-Z_]+)=(.*)$ ]] || continue
    key=${BASH_REMATCH[1]} value=${BASH_REMATCH[2]}
    case "$key" in AI_NOTIFY_CMD|AI_LIMIT_RETRY|AI_LIMIT_MAX_WAIT|AI_MODEL|AI_REVIEW_MODEL|AI_REVIEW_EFFORT) ;; *) continue ;; esac
    [[ -z "${!key+x}" ]] || continue
    if [[ "$value" =~ ^\"(.*)\"$ || "$value" =~ ^\'(.*)\'$ ]]; then value=${BASH_REMATCH[1]}; fi
    printf -v "$key" '%s' "$value"
    export "${key?}"
  done < "$file"
}
ai_config

# Codex review model/effort: reviews are where a stronger model pays off most.
# AI_REVIEW_MODEL (default: Codex's own default) and AI_REVIEW_EFFORT (default high).
ai_review_args() {
  local effort=${AI_REVIEW_EFFORT:-high}
  [[ "$effort" =~ ^(low|medium|high|xhigh|max)$ ]] || ai_die "Invalid AI_REVIEW_EFFORT: $effort"
  AI_REVIEW_ARGS=(-c "model_reasoning_effort=\"$effort\"")
  if [[ -n "${AI_REVIEW_MODEL:-}" ]]; then
    [[ "$AI_REVIEW_MODEL" =~ ^[A-Za-z0-9._-]+$ ]] || ai_die "Invalid AI_REVIEW_MODEL: $AI_REVIEW_MODEL"
    AI_REVIEW_ARGS+=(--model "$AI_REVIEW_MODEL")
  fi
}

# Notification hook: AI_NOTIFY_CMD runs via bash with the message as $1
# (e.g. curl -s -d "$1" ntfy.sh/<topic>). Failures never affect the workflow.
ai_notify() {
  [[ -n "${AI_NOTIFY_CMD:-}" ]] || return 0
  local project
  project=$(basename -- "${AI_ROOT:-$PWD}")
  timeout 20 bash -c "$AI_NOTIFY_CMD" ai-notify "[$project] $*" </dev/null >/dev/null 2>&1 || true
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
  ai_notify "Paused: $agent usage limit reached. Resuming around $until."
  ${AI_SLEEP:-sleep} "$wait"
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
ai_guard_verify() {
  local actual
  actual=$(ai_guard_digest) || ai_die 'Approved workflow gate is missing or unsafe; inspect changes.'
  [[ "$actual" == "$AI_APPROVED_GATE" ]] || \
    ai_die 'Approved workflow gate changed during this run. Stop, inspect the diff, and explicitly reapprove before resuming.'
}
ai_lock() {
  # One writer/reviewer per checkout. Kernel releases locks on exit or crash.
  # ai-pipeline holds this lock for its whole run; its direct children skip it.
  if [[ -n "${AI_LOCK_HELD:-}" && "$AI_LOCK_HELD" == "$PPID" ]]; then return 0; fi
  exec 9>.ai/local/workflow.lock
  flock -n 9 || ai_die 'Another runner/reviewer owns this checkout.'
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
