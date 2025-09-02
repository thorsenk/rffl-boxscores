#!/usr/bin/env bash
set -euo pipefail

# Organize existing season CSVs into data/seasons/<year>/ with canonical names.
# - Moves h2h_<year>.csv -> data/seasons/<year>/h2h.csv
# - Prefers validated_boxscores_<year>_filled.csv -> data/seasons/<year>/boxscores.csv
#   (falls back to validated_boxscores_<year>.csv if _filled not present)
# Overwrites existing target files to keep a single clean copy.

shopt -s nullglob

ROOT_DIR=$(dirname "$0")/..
cd "$ROOT_DIR"

mkdir -p data/seasons

echo "🔧 Organizing season data into data/seasons/<year>/ ..."

move_file() {
  local src="$1"
  local dst="$2"
  [ -f "$src" ] || return 0
  mkdir -p "$(dirname "$dst")"
  mv -f "$src" "$dst"
  echo "→ Moved $src -> $dst"
}

# Handle H2H weekly files first: h2h_YYYY_wkN.csv
for f in h2h_*_wk*.csv; do
  base=${f#h2h_}
  base=${base%.csv}
  y=${base%%_wk*}
  wk=${base#*_wk}
  [ -n "$y" ] || continue
  [ -n "$wk" ] || continue
  move_file "$f" "data/seasons/$y/weeks/$wk/h2h.csv"
done

# Handle H2H season files: h2h_YYYY.csv
for f in h2h_*.csv; do
  # skip weekly patterns (handled above)
  [[ "$f" == *_wk*.csv ]] && continue
  y=${f#h2h_}
  y=${y%.csv}
  [ -n "$y" ] || continue
  move_file "$f" "data/seasons/$y/h2h.csv"
done

# Handle boxscores (prefer _filled)
for f in validated_boxscores_*_filled.csv; do
  y=${f#validated_boxscores_}
  y=${y%_filled.csv}
  [ -n "$y" ] || continue
  move_file "$f" "data/seasons/$y/boxscores.csv"
done

for f in validated_boxscores_*.csv; do
  # Skip the ones already handled above (_filled)
  if [[ "$f" == *_filled.csv ]]; then
    continue
  fi
  # Skip validation reports
  if [[ "$f" == *_validation_report.csv ]] || [[ "$f" == *_lineup_validation_report.csv ]]; then
    continue
  fi
  y=${f#validated_boxscores_}
  y=${y%.csv}
  [ -n "$y" ] || continue
  # Only move if no boxscores.csv exists yet for this year
  if [ ! -f "data/seasons/$y/boxscores.csv" ]; then
    move_file "$f" "data/seasons/$y/boxscores.csv"
  else
    echo "ℹ️  Skipping $f (boxscores.csv already exists for $y)"
  fi
done

# Move validation reports to per-season reports folder
for f in validated_boxscores_*_validation_report.csv validated_boxscores_*_lineup_validation_report.csv; do
  [ -f "$f" ] || continue
  y=${f#validated_boxscores_}
  y=${y%_validation_report.csv}
  y=${y%_lineup_validation_report.csv}
  mkdir -p "data/seasons/$y/reports"
  mv -f "$f" "data/seasons/$y/reports/$f"
  echo "→ Moved $f -> data/seasons/$y/reports/$f"
done

# Repair any prior misplaced directories created by earlier runs
for bad in data/seasons/*_wk*/h2h.csv; do
  [ -f "$bad" ] || continue
  dir=$(dirname "$bad")
  leaf=$(basename "$dir")        # e.g., 2018_wk1
  y=$(basename $(dirname "$dir")) # parent folder name before fix, but may be wrong
  y=${leaf%%_wk*}
  wk=${leaf#*_wk}
  mkdir -p "data/seasons/$y/weeks/$wk"
  mv -f "$bad" "data/seasons/$y/weeks/$wk/h2h.csv"
  rmdir -p "$dir" 2>/dev/null || true
  echo "→ Repaired weekly h2h to data/seasons/$y/weeks/$wk/h2h.csv"
done

for bad in data/seasons/*_validation_report/boxscores.csv data/seasons/*_lineup_validation_report/boxscores.csv; do
  [ -f "$bad" ] || continue
  pdir=$(dirname "$bad")
  leaf=$(basename "$pdir")
  y=${leaf%%_*}
  kind=${leaf#*_}
  outname="validated_boxscores_${y}_${kind}.csv"
  mkdir -p "data/seasons/$y/reports"
  mv -f "$bad" "data/seasons/$y/reports/$outname"
  rmdir -p "$pdir" 2>/dev/null || true
  echo "→ Repaired report to data/seasons/$y/reports/$outname"
done

echo "✅ Done organizing."
