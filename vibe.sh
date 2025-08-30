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
