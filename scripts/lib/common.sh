#!/usr/bin/env bash
# Shared by the toolkit scripts and their copies in .ai/bin/.
set -euo pipefail
AI_BIN=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ai_die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
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
roots = ('.ai/validate', '.ai/bin', '.ai/prompts',
         '.ai/permissions.allow', '.claude/settings.json')
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
                if name != '.claude/settings.json' or path != root:
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
