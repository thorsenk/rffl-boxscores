# RFFL Enhanced Matchup Box Scores

This document explains how the CLI builds “Enhanced Matchup Box Scores” CSVs and how validations work. It captures the normalization logic, rounding rules, lineup requirements, and the optional missing‑slot fill feature.

## Overview

- Goal: consistent, analysis‑ready matchup box scores for an entire season.
- Source: ESPN Fantasy Football via `espn_api.football.League`.
- Output: one CSV row per rostered player per team‑week, with normalized slots and stable team totals.

## Columns

Each row contains:
- week: NFL week number
- matchup: matchup index within the week (1‑based)
- team_abbrev: team identifier (best‑effort from ESPN team fields)
- team_proj_total: rounded sum of the team’s starters’ projected points
- team_actual_total: rounded sum of the team’s starters’ actual points
- slot: normalized roster slot (QB, RB, WR, TE, FLEX, D/ST, K, Bench, IR)
- slot_type: "starters" or "bench"
- player_name: player display name (or placeholder for fills)
- position: ESPN position (normalized for D/ST, FLEX placeholder set to WR)
- injured: boolean if reported
- injury_status: ESPN injury status or "EMPTY" for placeholders
- bye_week: boolean if reported
- projected_points: player projected points (rounded to 2 decimals)
- actual_points: player actual points (rounded to 2 decimals)

## Export Logic

High‑level steps (see `rffl_boxscores/cli.py`):
1. Load cookies/env, init `League`.
2. Iterate weeks; fetch `league.box_scores(week)`.
3. For each matchup side (home/away), iterate lineup and build rows.
4. Normalize each player’s `slot` using `_norm_slot`.
5. Classify starters vs bench via `STARTER_SLOTS`.
6. Round each player’s projected/actual to 2 decimals.
7. Compute team totals by summing starters only, then round to 2 decimals.
8. Optionally insert 0‑point placeholders for missing required starter slots.
9. Emit rows to CSV with minimal quoting.

Why per‑player rounding first? Summing already‑rounded values guarantees the team totals match the sum of the starter rows exactly (no floating drift).

## Normalization Rules

Function `_norm_slot` maps ESPN data to stable slots:
- FLEX, RB/WR/TE → FLEX
- DST, D/ST, Defense → D/ST
- BE, Bench → Bench
- IR → IR
- QB/RB/WR/TE/K pass through
- If slot unknown, fallback to position; D/ST handled explicitly

Starters vs Bench:
- Starters: {QB, RB, WR, TE, D/ST, K, FLEX}
- Bench: {Bench, IR}

Team Abbreviation:
- Best effort across ESPN team attrs: `abbrev`, `team_abbrev`, `abbreviation`, `team_id`, `name`.

## RFFL Lineup Requirements

Required starters per team‑week (total 9):
- QB: 1
- RB: 2
- WR: 2
- TE: 1
- FLEX: 1 (must be RB/WR/TE)
- D/ST: 1
- K: 1

FLEX Eligibility:
- Only RB, WR, or TE are allowed in FLEX.

## Missing Starter Fills (optional)

Some historical lineups have fewer than 9 starters recorded by ESPN (e.g., a missing WR). To keep datasets structurally consistent while preserving totals, the exporter can fill missing required starter slots with 0‑point placeholders.

- CLI flag: `--fill-missing-slots` (default off)
- Placeholder fields:
  - player_name: `EMPTY SLOT - {SLOT}`
  - slot: missing required slot (e.g., WR)
  - slot_type: starters
  - position: for FLEX placeholders, set to WR (to remain FLEX‑eligible); otherwise same as slot
  - injury_status: `EMPTY`
  - projected_points/actual_points: `0.0`

This ensures:
- Starter count is always 9
- Team totals remain correct (unchanged), since fills are 0.0
- Lineup compliance validation becomes deterministic across seasons

## Validations

Command `validate` checks by team‑week:
- proj_diff: sum(starters.projected_points) − team_proj_total (should be 0.00)
- act_diff: sum(starters.actual_points) − team_actual_total (should be 0.00)
- starter_count: exactly 9 starters

Command `validate-lineup` enforces:
- Position counts match RFFL requirements (above)
- FLEX contains only RB/WR/TE
- No duplicate player names among starters
- Slot vs. position sanity for QB, K, D/ST

If issues exist, each command writes a `*_validation_report.csv` for details.

## Example Workflows

Export a season:
```bash
rffl-bs export --league $LEAGUE --year 2019
```

Export with missing‑slot fills:
```bash
rffl-bs export --league $LEAGUE --year 2019 --fill-missing-slots --out validated_boxscores_2019_filled.csv
```

Validate:
```bash
rffl-bs validate validated_boxscores_2019.csv
rffl-bs validate-lineup validated_boxscores_2019.csv
```

## Edge Cases + Notes

- Historical seasons sometimes record incomplete starters; use `--fill-missing-slots` for a stable dataset.
- D/ST naming varies across ESPN responses; normalization maps consistently to `D/ST`.
- Per‑player rounding first avoids fractional cent drift in totals.
- Team abbreviations are best‑effort and may differ across leagues.

## Reproducibility

- Env precedence: CLI flags > real environment > `.env` (dotenv is auto‑loaded).
- Stable CSV column order and float rounding make outputs deterministic.

