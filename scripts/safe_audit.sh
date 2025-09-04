#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="build/audit"
mkdir -p "$OUT_DIR"

# Collect core diagnostics; never fail the whole audit
{
  python -m pip list --format=freeze
} >"$OUT_DIR/pip_list.log" 2>&1 || true

{
  git status --porcelain=v1
} >"$OUT_DIR/git_status.log" 2>&1 || true

{
  git log -n 50 --pretty=oneline
} >"$OUT_DIR/git_recent_log.log" 2>&1 || true

# Lint/format and CLI surface
{
  flake8
} >"$OUT_DIR/flake8.log" 2>&1 || true

{
  black --check .
} >"$OUT_DIR/black_check.log" 2>&1 || true

{
  python -m rffl_boxscores.cli --help
} >"$OUT_DIR/cli_help.log" 2>&1 || true

echo "Audit complete. See $OUT_DIR/"
