# vibe.sh — quick aliases for rffl-boxscores
# Usage: source ./vibe.sh

# Load local env if present (LEAGUE, ESPN_S2, SWID)
[ -f ./.env ] && . ./.env

# Export season data
bs() {
  # usage: bs <year> [start_week] [end_week] [out_path]
  local year=$1
  local start_week=$2
  local end_week=$3
  local out_path=$4
  
  local cmd="rffl-bs export --league ${LEAGUE:?set LEAGUE or source .env} --year $year"
  
  [ -n "$start_week" ] && [ "$start_week" -gt 0 ] && cmd="$cmd --start-week $start_week"
  [ -n "$end_week" ] && [ "$end_week" -gt 0 ] && cmd="$cmd --end-week $end_week"
  [ -n "$out_path" ] && cmd="$cmd --out $out_path"
  
  eval $cmd
}

# Validate a season file
bsv() {
  # usage: bsv <year>
  rffl-bs validate "validated_boxscores_${1:?year}.csv"
}

# Validate RFFL lineup compliance
bsl() {
  # usage: bsl <year>
  rffl-bs validate-lineup "validated_boxscores_${1:?year}.csv"
}

# Playoffs only (modern seasons)
bsp() {
  # usage: bsp <year>
  bs "${1:?year}" 15 17
}

# Auto-commit helper (optional)
autocommit() {
  # usage: autocommit [interval_seconds] [push]
  # example: autocommit 30 1  # every 30s and push
  local interval=${1:-60}
  local push=${2:-0}
  mkdir -p .git
  INTERVAL=$interval PUSH=$push nohup bash ./scripts/auto_commit.sh >/dev/null 2>&1 &
  echo $! > .git/.auto_commit.pid
  echo "🔁 Auto-commit started (interval=${interval}s, push=${push}). To stop: acstop"
}

acstop() {
  # usage: acstop
  if [ -f .git/.auto_commit.pid ]; then
    local pid
    pid=$(cat .git/.auto_commit.pid || true)
    if [ -n "$pid" ]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
    rm -f .git/.auto_commit.pid
    echo "🛑 Auto-commit stopped"
  else
    echo "ℹ️  No auto-commit PID file (.git/.auto_commit.pid)."
  fi
}

withac() {
  # usage: withac [--interval N] [--push] -- <command ...>
  bash ./scripts/with_autocommit.sh "$@"
}

autocommit_once() {
  # usage: autocommit_once [push]
  # Commits the next change then exits.
  local push=${1:-0}
  mkdir -p .git
  ONCE=1 PUSH=$push nohup bash ./scripts/auto_commit.sh >/dev/null 2>&1 &
  echo $! > .git/.auto_commit.pid
  echo "🔁 Auto-commit will capture the next change (push=${push}). To stop: acstop"
}

autocommit_idle() {
  # usage: autocommit_idle <idle_minutes> [push]
  # Auto-stops after idle_minutes with no commits.
  local idle=${1:?idle_minutes}
  local push=${2:-0}
  mkdir -p .git
  MAX_IDLE_MINUTES=$idle PUSH=$push nohup bash ./scripts/auto_commit.sh >/dev/null 2>&1 &
  echo $! > .git/.auto_commit.pid
  echo "🔁 Auto-commit started (idle-stop=${idle}m, push=${push}). To stop: acstop"
}

# Run a safe, truncated audit and save full logs under build/audit
audit() {
  # usage: audit
  if [ ! -x scripts/safe_audit.sh ]; then
    chmod +x scripts/safe_audit.sh 2>/dev/null || true
  fi
  bash scripts/safe_audit.sh "$@"
}

# Print only the first N lines of a file (default 200)
pview() {
  # usage: pview <file> [lines]
  local file=${1:?file}
  local lines=${2:-200}
  echo "--- ${file} (first ${lines} lines) ---"
  sed -n "1,${lines}p" "$file" 2>/dev/null || head -n "$lines" "$file" 2>/dev/null || true
}
