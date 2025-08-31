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
# Optional behavior controls
# ONCE=1           -> exit after the first successful commit
# MAX_IDLE_MINUTES -> auto-exit if no commits after N minutes (default: 0 = never)
# BACKOFF=1        -> exponential backoff when no changes (reduces polling)
once_flag="${ONCE:-0}"
max_idle_min="${MAX_IDLE_MINUTES:-0}"
backoff_flag="${BACKOFF:-1}"
backoff_start="${BACKOFF_START:-15}"
backoff_max="${BACKOFF_MAX:-300}"
current_sleep="$interval"
last_commit_ts="$(date +%s)"

echo "🔁 Auto-commit loop: interval=${interval}s push=${push_flag} once=${once_flag} idle=${max_idle_min}m backoff=${backoff_flag} (Ctrl+C to stop)"

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

    last_commit_ts="$(date +%s)"
    # reset backoff after a commit
    current_sleep="$interval"

    if [ "$push_flag" = "1" ]; then
      git push || echo "⚠️  Push failed; will retry on next cycle"
    fi

    # Exit if only one commit requested
    if [ "$once_flag" = "1" ]; then
      echo "🛑 ONCE=1 set: exiting after first commit"
      exit 0
    fi
  fi

  # Auto-exit after idle time with no commits
  if [ "$max_idle_min" != "0" ]; then
    now_ts="$(date +%s)"
    idle_sec=$(( now_ts - last_commit_ts ))
    if [ "$idle_sec" -ge $(( max_idle_min * 60 )) ]; then
      echo "🛑 No commits for ${max_idle_min} minutes. Exiting."
      exit 0
    fi
  fi

  # Backoff sleep to reduce polling when idle
  if [ "$backoff_flag" = "1" ]; then
    sleep "$current_sleep"
    # increase sleep up to max if nothing committed
    if [ "$current_sleep" -lt "$backoff_max" ]; then
      current_sleep=$(( current_sleep * 2 ))
      if [ "$current_sleep" -lt "$backoff_start" ]; then
        current_sleep="$backoff_start"
      fi
      if [ "$current_sleep" -gt "$backoff_max" ]; then
        current_sleep="$backoff_max"
      fi
    fi
  } else {
    sleep "$interval"
  fi
done
