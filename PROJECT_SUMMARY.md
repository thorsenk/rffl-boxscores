## 🌀 Vibe Mode (optional)

Save this snippet as `vibe.sh` in the repo root, then run `source ./vibe.sh` in any new shell (or paste the functions into your `~/.zshrc`).

```bash
# vibe.sh — quick aliases for rffl-boxscores
# Usage: source ./vibe.sh

# Load local env if present (LEAGUE, ESPN_S2, SWID)
[ -f ./.env ] && . ./.env

# Export season data
bs() {
  # usage: bs <year> [start_week] [end_week] [out_path]
  rffl-bs export \
    --league "${LEAGUE:?set LEAGUE or source .env}" \
    --year   "${1:?year}" \
    ${2:+--start-week "$2"} \
    ${3:+--end-week "$3"} \
    ${4:+--out "$4"}
}

# Validate a season file
bsv() {
  # usage: bsv <year>
  rffl-bs validate "validated_boxscores_${1:?year}.csv"
}

# Playoffs only (modern seasons)
bsp() {
  # usage: bsp <year>
  bs "${1:?year}" 15 17
}
```

**Tips**
- Put your league id in `.env`:  
  ```bash
  echo 'export LEAGUE=323196' >> .env
  ```
- Private league? Also add `ESPN_S2` and `SWID` to `.env`, then `source .env`.
- If `rffl-bs` isn’t found, ensure your virtualenv is active or run:  
  `python -m rffl_boxscores.cli --help`
