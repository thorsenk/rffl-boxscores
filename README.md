# RFFL Boxscores

A clean ESPN fantasy football boxscore exporter and validator CLI tool.

## Features

- **Export**: Fetch ESPN fantasy football boxscores and export to CSV format
- **Validate**: Verify data consistency and completeness
- **Validate Lineup**: Check RFFL lineup compliance (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K)
- **Clean Data**: Normalized slot positions, injury status, and bye week information
- **Flexible**: Support for public and private leagues with cookie authentication

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

### Export Boxscores

#### Public League (No Authentication Required)

```bash
rffl-bs export --league 323196 --year 2024
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
rffl-bs export --league 323196 --year 2024 --start-week 1 --end-week 10
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
# 1. Export current season data
rffl-bs export --league 323196 --year 2024

# 2. Validate the export
rffl-bs validate validated_boxscores_2024.csv

# 3. Check lineup compliance
rffl-bs validate-lineup validated_boxscores_2024.csv

# 4. Check for any issues
cat validated_boxscores_2024_validation_report.csv
cat validated_boxscores_2024_lineup_validation_report.csv
```

### Multiple Seasons

```bash
# Export multiple seasons
for year in 2022 2023 2024; do
    rffl-bs export --league 323196 --year $year
    rffl-bs validate validated_boxscores_$year.csv
    rffl-bs validate-lineup validated_boxscores_$year.csv
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
