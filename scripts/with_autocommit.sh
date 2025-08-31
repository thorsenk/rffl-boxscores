#!/usr/bin/env bash
# scripts/with_autocommit.sh — run any dev command alongside auto-commit loop
# Usage:
#   scripts/with_autocommit.sh [--interval N] [--push] -- <your dev command ...>
# Examples:
#   bash scripts/with_autocommit.sh -- uvicorn app:app --reload
#   bash scripts/with_autocommit.sh --interval 30 --push -- npm run dev

set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "❌ Not inside a git repository" >&2
  exit 1
fi

interval=60
push_flag=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval)
      interval=${2:-60}
      shift 2
      ;;
    --push)
      push_flag=1
      shift 1
      ;;
    --)
      shift
      break
      ;;
    *)
      # treat the rest as command if no -- provided
      break
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 [--interval N] [--push] -- <command ...>" >&2
  exit 2
fi

cmd=("$@")

start_autocommit() {
  mkdir -p .git
  INTERVAL=$interval PUSH=$push_flag nohup bash ./scripts/auto_commit.sh >/dev/null 2>&1 &
  ac_pid=$!
  echo "$ac_pid" > .git/.auto_commit.pid
  echo "🔁 Auto-commit started (pid=$ac_pid, interval=${interval}s, push=${push_flag})"
}

stop_autocommit() {
  if [[ -f .git/.auto_commit.pid ]]; then
    ac_pid=$(cat .git/.auto_commit.pid || true)
    if [[ -n "${ac_pid:-}" ]];
    then
      kill "${ac_pid}" >/dev/null 2>&1 || true
    fi
    rm -f .git/.auto_commit.pid
  fi
}

cleanup() {
  stop_autocommit
}

trap cleanup INT TERM EXIT

start_autocommit

"${cmd[@]}"
status=$?

cleanup

exit $status

