# RFFL Boxscores

A clean ESPN fantasy football boxscore exporter and validator CLI tool.

## Features

- **Export**: Fetch ESPN fantasy football boxscores and export to CSV format
- **Validate**: Verify data consistency and completeness
- **Validate Lineup**: Check RFFL lineup compliance (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K)
- **Clean Data**: Normalized slot positions, injury status, and bye week information
- **Flexible**: Support for public and private leagues with cookie authentication
 - **Design Notes**: See `RFFL.md` for Enhanced Matchup Box Scores logic (normalization, rounding, validations, and the `--fill-missing-slots` option).

## Installation

### From Source

```bash
# Clone or download the project
cd rffl-boxscores

# Install in development mode
pip install -e .
```

### Dependencies

The tool requires Python 3.9+ and the following packages:
- `espn_api>=0.39.1` - ESPN API client
- `pandas>=2.2.0` - Data manipulation
- `python-dateutil>=2.9.0` - Date utilities
- `typer>=0.9.0` - CLI framework

## Usage

### Data Layout

Clean, canonical outputs are organized by season under `data/seasons/<year>/`:

- 2019+ full boxscores: `data/seasons/<year>/boxscores.csv`
- Pre‑2019 H2H only: `data/seasons/<year>/h2h.csv`
- Optional weekly H2H: `data/seasons/<year>/weeks/<N>/h2h.csv`
- Draft results: `data/seasons/<year>/draft.csv`
- Any validation reports (if generated): `data/seasons/<year>/reports/`

The vibe helpers write to these locations by default and overwrite existing files to avoid clutter.

### Export Boxscores

#### Public League (No Authentication Required)

```bash
# Raw CLI
rffl-bs export --league 323196 --year 2024 --fill-missing-slots --out data/seasons/2024/boxscores.csv

# Recommended via vibe helper (auto-validates and overwrites clean file)
source ./vibe.sh
bs 2024
```

#### Private League (Cookie Authentication Required)

```bash
# Set environment variables
export ESPN_S2="your_espn_s2_cookie_value"
export SWID="{your_swid_cookie_value}"

# Export with environment variables
rffl-bs export --league 323196 --year 2023

# Or pass cookies directly
rffl-bs export --league 323196 --year 2023 --espn-s2 "your_cookie" --swid "your_cookie"
```

#### Custom Options

```bash
# Specify output file
rffl-bs export --league 323196 --year 2024 --out "my_boxscores.csv"

# Export specific weeks
rffl-bs export --league 323196 --year 2024 --start-week 1 --end-week 10 --fill-missing-slots --out data/seasons/2024/boxscores.csv
```

### Export H2H Results (pre‑2019 friendly)

For older seasons (pre‑2019) where ESPN’s per‑player boxscores may be incomplete, export simplified head‑to‑head matchup results:

```bash
# Full season H2H results
rffl-bs h2h --league 323196 --year 2018 --out data/seasons/2018/h2h.csv

# Specific week range
rffl-bs h2h --league 323196 --year 2018 --start-week 1 --end-week 13 --out data/seasons/2018/h2h.csv

# Custom output filename
source ./vibe.sh
h2h 2018
```

Output columns: `week, matchup, home_team, away_team, home_score, away_score, winner, margin`.

### Export Draft Results

Export draft results (snake or auction) to the canonical location:

```bash
# Raw CLI
rffl-bs draft --league 323196 --year 2024 --out data/seasons/2024/draft.csv

# Recommended via vibe helper
source ./vibe.sh
draft 2024
```

### Validate Exported Data

```bash
# Basic validation
rffl-bs validate validated_boxscores_2024.csv

# With tolerance for floating point differences
rffl-bs validate validated_boxscores_2024.csv --tolerance 0.02
```

### Validate RFFL Lineup Compliance

```bash
# Check lineup compliance (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K)
rffl-bs validate-lineup validated_boxscores_2024.csv

# Generate detailed report
rffl-bs validate-lineup validated_boxscores_2024.csv --out lineup_report.csv
```

The lineup validation checks for:
- **Position Counts**: Exactly 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K
- **FLEX Eligibility**: FLEX slot only contains RB, WR, or TE players
- **Duplicate Players**: No player appears twice in starters
- **Position-Slot Matching**: QB slot only has QBs, K slot only has Ks, etc.

## Output Format

The exported CSV contains the following columns:

| Column | Description |
|--------|-------------|
| `week` | NFL week number |
| `matchup` | Matchup number within the week |
| `team_abbrev` | Team abbreviation |
| `team_proj_total` | Team's projected total points |
| `team_actual_total` | Team's actual total points |
| `slot` | Player's roster slot (QB, RB, WR, TE, FLEX, D/ST, K, Bench, IR) |
| `slot_type` | Whether player is "starters" or "bench" |
| `player_name` | Player's name |
| `position` | Player's position |
| `injured` | Whether player is injured |
| `injury_status` | Injury status (ACTIVE, QUESTIONABLE, etc.) |
| `bye_week` | Whether player is on bye week |
| `projected_points` | Player's projected fantasy points |
| `actual_points` | Player's actual fantasy points |

## Data Validation

The validation command checks for:

1. **Projection Mismatches**: Differences between sum of starter projections and team projection total
2. **Actual Mismatches**: Differences between sum of starter actuals and team actual total  
3. **Starter Count**: Ensures exactly 9 starters per team (standard fantasy football format)

### Validation Report

If issues are found, a detailed report is generated with:
- Week, matchup, and team information
- Specific issue type (proj_mismatch, actual_mismatch, starter_count)
- Difference values and counts

## Lineup Validation

The lineup validation command checks for RFFL compliance:

1. **Count Mismatches**: Wrong number of players in required positions
2. **FLEX Ineligible**: Non-RB/WR/TE players in FLEX slot
3. **Duplicate Players**: Same player starting multiple times
4. **Invalid Position in Slot**: Wrong position type in specific slots

### Lineup Validation Report

If lineup issues are found, a detailed report is generated with:
- Week, matchup, and team information
- Issue type and description
- Specific player and position details

## Getting ESPN Cookies

For private leagues, you need to obtain ESPN authentication cookies:

1. Log into ESPN Fantasy Football in your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage → Cookies → espn.com
4. Copy the values for:
   - `ESPN_S2` (long string)
   - `SWID` (format: `{...}`)

## Examples

### Complete Workflow

```bash
# 1. Export current season data (clean, canonical location)
source ./vibe.sh
bs 2024

# 2. Optional: additional validation on the produced file
rffl-bs validate data/seasons/2024/boxscores.csv

# 3. Check lineup compliance
rffl-bs validate-lineup validated_boxscores_2024.csv

# 4. Check for any issues
cat validated_boxscores_2024_validation_report.csv
cat validated_boxscores_2024_lineup_validation_report.csv
```

### Multiple Seasons

```bash
# Export multiple seasons
source ./vibe.sh
for year in 2022 2023 2024; do
  bs $year
done

# H2H for older seasons
for year in 2016 2017 2018; do
  h2h $year
done
```

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
```

**Tips**
- Put your league id in `.env`:  
  ```bash
  echo 'export LEAGUE=323196' >> .env
  ```
- Private league? Also add `ESPN_S2` and `SWID` to `.env`, then `source .env`.
- If `rffl-bs` isn't found, ensure your virtualenv is active or run:  
  `python -m rffl_boxscores.cli --help`

## Error Handling

The tool includes robust error handling for:
- Invalid league IDs
- Network connectivity issues
- Missing authentication for private leagues
- Data inconsistencies in ESPN's API responses

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Agent Notes

- Env precedence: CLI flags > real environment > `.env` (auto-loaded).
- League default: if `--league` is omitted, the tool uses `$LEAGUE`.
- Exit codes: non-zero on export/validation errors for easy agent checks.
- Stable outputs: CSV columns and ordering are deterministic.
 - Command reference: see `AGENTS.md` for all CLI, vibe helpers, and scripts.

### Optional: Auto-Commit Loop

- Start a lightweight auto-commit loop that commits any staged/unstaged changes
  at an interval (default 60s). Useful for solo‑vibecoding + agent sessions.

```bash
# start with defaults (every 60s, no push)
bash ./scripts/auto_commit.sh

# or via vibe function
source ./vibe.sh
autocommit 30 1   # every 30s and push
```

- Safety: `.env` and common secrets are already gitignored. The loop skips if
  merge conflicts exist. Stop with `pkill -f auto_commit.sh` or Ctrl+C if run
  foreground.
If the script is not executable, run: `chmod +x scripts/auto_commit.sh`.

- CI control: by default, auto-commits include `[skip ci]` to avoid triggering
  workflows. To allow CI on autosaves, set `SKIP_CI=0` when starting the loop:

```bash
SKIP_CI=0 bash ./scripts/auto_commit.sh           # foreground
SKIP_CI=0 source ./vibe.sh && autocommit 60 1     # via vibe helper
```

### Run Dev Server + Auto-Commit in one command

- Use the wrapper to run any dev command alongside auto‑commit:

```bash
# generic pattern
bash ./scripts/with_autocommit.sh -- <your dev command>

# examples
bash ./scripts/with_autocommit.sh --interval 30 --push -- uvicorn app:app --reload
bash ./scripts/with_autocommit.sh -- npm run dev
```

- Or via vibe helpers:

```bash
source ./vibe.sh
withac --interval 30 --push -- uvicorn app:app --reload
```

### Safe Audit (avoid large outputs)

- Use the built-in safe audit to collect repo diagnostics without overflowing the chat/API payload limit. It writes full logs under `build/audit` and only prints short summaries.

```bash
# quick summary + saved logs
source ./vibe.sh
audit

# open full logs afterward
ls build/audit/
```

- Tip: avoid `cat`-ing huge files or dumping entire CSVs in chat sessions. Prefer `sed -n '1,200p' <file>` or `rg pattern | head -n 200`.
