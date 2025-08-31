#!/usr/bin/env bash
# scripts/auto_commit.sh — lightweight auto-commit loop for solo dev + agent flow
# Usage examples:
#   ./scripts/auto_commit.sh                 # commit every 60s when changes exist
#   INTERVAL=30 ./scripts/auto_commit.sh     # custom interval (seconds)
#   PUSH=1 ./scripts/auto_commit.sh          # also push after committing

set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "❌ Not inside a git repository" >&2
  exit 1
fi

interval="${INTERVAL:-60}"
push_flag="${PUSH:-0}"

echo "🔁 Auto-commit loop: interval=${interval}s push=${push_flag} (Ctrl+C to stop)"

while true; do
  # Skip if merge conflicts present
  if git diff --name-only --diff-filter=U | grep -q . ; then
    echo "⚠️  Unresolved merge conflicts detected. Skipping commit."
    sleep "$interval"
    continue
  fi

  # Stage any changes (tracked + untracked)
  git add -A >/dev/null 2>&1 || true

  # Commit only if something is staged
  if ! git diff --cached --quiet; then
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
    ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    changes="$(git diff --cached --name-status | sed -e 's/^/  /' | head -n 20)"
    msg="auto: ${ts} on ${branch} [solo-vibe+agent]"
    git commit -m "$msg" -m "$changes" || true
    echo "✅ Committed: $msg"

    if [ "$push_flag" = "1" ]; then
      git push || echo "⚠️  Push failed; will retry on next cycle"
    fi
  fi

  sleep "$interval"
done

