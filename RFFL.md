# RFFL Enhanced Matchup Box Scores

This document explains how the CLI builds “Enhanced Matchup Box Scores” CSVs and how validations work. It captures the normalization logic, rounding rules, lineup requirements, and the optional missing‑slot fill feature.

## Overview

- Goal: consistent, analysis‑ready matchup box scores for an entire season.
- Source: ESPN Fantasy Football via `espn_api.football.League`.
- Output: one CSV row per rostered player per team‑week, with normalized slots and stable team totals.

## Columns

Each row contains (final schema):

- season_year: season year
- week: NFL week number
- matchup: matchup index within the week (1‑based)
- team_code: canonical team code (via alias mapping)
- is_co_owned?: Yes/No if co-owned (from canonicals)
- team_owner_1: primary owner code
- team_owner_2: secondary owner code (if any)
- team_projected_total: rounded sum of the team’s starters’ projected points
- team_actual_total: rounded sum of the team’s starters’ actual points
- slot_type: "starters" or "bench"
- slot: normalized roster slot (QB, RB, WR, TE, FLEX, D/ST, Bench, IR)
- player_name: player display name (or placeholder for fills)
- nfl_team: player's NFL team (abbrev, e.g., CIN, ARI)
- position: ESPN position (normalized for D/ST, FLEX placeholder set to WR)
- is_placeholder: "Yes" for auto-inserted 0-pt fills (when using --fill-missing-slots), else "No"
- issue_flag: optional marker (e.g., MISSING_SLOT:WR, INVALID_FLEX_POSITION:QB)
- rs_projected_pf: player projected points (rounded to 2 decimals)
- rs_actual_pf: player actual points (rounded to 2 decimals)

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

Team Identity:

- Resolve canonical `team_code` by mapping ESPN team fields (e.g., abbrev/name) through `data/teams/alias_mapping.yaml` against `data/teams/canonical_teams.csv` per season.

## Canonicals + Aliases

To maintain a stable historical identity for teams (despite abbrev/name changes), use:

- `data/teams/canonical_teams.csv`: per-year canonical team_code, full name, and ownership info.
- `data/teams/alias_mapping.yaml`: master alias → canonical mapping with optional year bounds.

Normalize season CSVs to add canonical codes:

- H2H: adds `home_code`, `away_code`, `winner_code` based on aliases.
- Draft/Boxscores: exporter emits `team_code` (canonical) instead of source `team_abbrev`.

Scripts:

- `scripts/apply_alias_mapping.py --file <csv> --year <YYYY> --out <path>`
  Applies `alias_mapping.yaml` to one CSV, writing normalized output.

Example:

```bash
python3 scripts/apply_alias_mapping.py \
  --file data/seasons/2011/h2h.csv \
  --year 2011 \
  --out data/seasons/2011/reports/h2h_normalized.csv
```

Notes:

- Extend `alias_mapping.yaml` as teams rebrand or abbreviations vary by source/season.
- Keep `canonical_teams.csv` authoritative for the team_code set per season.

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
  - rs_projected_pf/rs_actual_pf: `0.0`

This ensures:

- Starter count is always 9
- Team totals remain correct (unchanged), since fills are 0.0
- Lineup compliance validation becomes deterministic across seasons

## Validations

Command `validate` checks by team‑week:

- proj_diff: sum(starters.rs_projected_pf) − team_projected_total (should be 0.00)
- act_diff: sum(starters.rs_actual_pf) − team_actual_total (should be 0.00)
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

## Simplified H2H (Legacy Seasons)

For seasons before 2019, ESPN’s per‑player lineup data can be incomplete or inconsistent. Use the `rffl-bs h2h` command to export simplified head‑to‑head matchup results without per‑player rows. This produces one row per matchup with home/away teams, scores, winner, and margin, and is suitable for season‑level results and standings.

## Draft Exports

Two draft outputs are supported when normalizing historical data:

- Draft Corrected Canonicals (per season): `data/seasons/<year>/reports/<year>-Draft-Correct-Canonicals.csv`
  - Schema: year, round, round_pick, team_abbrev (source), player_id, player_name, keeper, team_code, team_full_name, is_co_owned, owner_code_1, owner_code_2
  - Notes: retains ESPN’s `team_abbrev` for traceability; canonical `team_code` is authoritative.

- Draft Snake Canonicals (per season): `data/seasons/<year>/reports/<year>-Draft-Snake-Canonicals.csv`
  - Schema: year, round, round_pick, overall_pick, team_code, team_full_name, is_co_owned, owner_code_1, owner_code_2, player_id, player_name, player_NFL_team, player_position, is_a_keeper?
  - Notes: optimized for analysis; no auction fields. `overall_pick = (round-1)*teams + round_pick`.

### Ownership Columns

- `owner_code_1` / `owner_code_2`: flat owner codes. Names are positional only for determinism; they do not imply hierarchy or priority. Co‑owners are equals.
- `is_co_owned`: Yes/No convenience flag

These names are canonical across all generated CSVs. If legacy columns exist (e.g., `owner_code`, `owner_code (CO-OWNER)`), generators backfill them for compatibility but do not rely on them.

## Co‑Ownership Semantics

- Equality: Co‑owners are equal. The `*_1` / `*_2` suffixes in column names are not hierarchical.
- Aggregation rules for analytics:
  - USD‑denominated metrics (columns ending with `_usd`): split 50/50 between co‑owners.
  - All other team metrics (wins, PF/PA, records, titles, etc.): attribute 100% to each co‑owner for owner‑level rollups.
- Determinism: When two owners exist, the pair order in `owner_code_1/2` is stable but arbitrary (often lexical). Logic should not depend on which appears first.
