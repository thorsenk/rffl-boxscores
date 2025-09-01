#!/usr/bin/env bash
set -euo pipefail

# Safe repo audit that captures rich diagnostics to files while printing
# only small, truncated summaries to stdout to avoid chat payload limits.

OUT_DIR="build/audit"
mkdir -p "$OUT_DIR"

ts() { date -Iseconds; }

section() {
  echo
  echo "===== $* ====="
}

capture() {
  # usage: capture <label> -- <cmd ...>
  local label=$1; shift
  if [[ "$1" == "--" ]]; then shift; fi
  local file="$OUT_DIR/${label// /_}.log"
  {
    echo "[$(ts)] $label"
    echo "cmd: $*"
    echo
    # shellcheck disable=SC2068
    $@ 2>&1
  } | tee "$file" >/dev/null

  # Print a small excerpt to stdout (head + tail) to stay well under limits.
  section "$label (summary)"
  if [[ -s "$file" ]]; then
    echo "--- head (first 120 lines) ---"
    head -n 120 "$file" || true
    echo "--- tail (last 30 lines) ---"
    tail -n 30 "$file" || true
  else
    echo "(no output)"
  fi
  echo "↳ full log: $file"
}

main() {
  section "Environment"
  echo "timestamp: $(ts)"
  echo "uname: $(uname -a || true)"
  echo "shell: ${SHELL:-unknown}"
  echo "python: $(python --version 2>&1 || true)"
  echo "pip: $(pip --version 2>&1 || true)"

  capture "pip_list" -- bash -lc 'pip list --format=freeze || true'

  section "Git status"
  echo "branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo none)"
  echo "remote:"
  git remote -v 2>/dev/null || true

  capture "git_status" -- git status -sb || true
  capture "git_recent_log" -- bash -lc 'git log --oneline -n 30 || true'

  # Try diff vs upstream; fallback to last commit.
  if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
    capture "git_diff_stat_upstream" -- bash -lc 'git diff --stat @{u}...HEAD || true'
  else
    capture "git_diff_stat_last" -- bash -lc 'git diff --stat HEAD~1..HEAD || true'
  fi

  # File inventory (truncated)
  capture "files_list" -- bash -lc 'rg --files -n --hidden -g "!venv" -g "!.venv" -g "!node_modules" | sort || true'

  # TODOs/FIXMEs
  capture "todo_scan" -- bash -lc 'rg -n "TODO|FIXME|HACK|BUG" -S || true'

  # Python tests (unit only)
  if command -v pytest >/dev/null 2>&1; then
    capture "pytest" -- pytest -q || true
  fi

  section "Done"
  echo "All logs saved under: $OUT_DIR"
}

main "$@"

