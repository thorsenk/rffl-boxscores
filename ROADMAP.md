# RFFL Boxscores – Roadmap / Backlog

This document tracks near‑term ideas and backlog items to keep the data model consistent across eras and improve downstream analytics.

## Backlog (Prioritized)

1) Legacy Team‑Week H2H (2011–2018)
- Add `h2h_normalized_v2` generator producing one row per team‑week with canonical identity and result context (no home/away).
- Proposed columns: `season_year, week, matchup, team_code, is_co_owned?, team_owner_1, team_owner_2, opponent_code, opp_is_co_owned?, opp_owner_1, opp_owner_2, team_projected_total, team_actual_total, opp_actual_total, result, margin` (optional: `winner_code`, `matchup_uid`).

2) Unified Team‑Week Output (2019–)
- Collapse enhanced boxscores to the same team‑week schema as above to provide a single cross‑era source for the Dashboard.
- Populate `team_projected_total` from starters (already available for 2019+).

3) Co‑Ownership Neutrality Improvements
- Consider alternative display naming (e.g., `co_owner_a` / `co_owner_b`) while retaining canonical `owner_code_1/2` for compatibility.
- Optionally add a combined `owners` display field (comma‑separated) for UI.

4) Owner Share Helper
- Add `owner_share_usd` (1.0 for solo; 0.5 if co‑owned) to simplify owner‑level aggregations for USD‑denominated metrics.

5) Defensive Dedupe
- Add defensive de‑duplication in `scripts/make_draft_snake.py` (by `(year, round, round_pick, team_code, player_id)`) to guard against future upstream duplication.

6) CLI Convenience
- Add CLI option(s) to export Excel workbooks: per‑year and combined multi‑year, one tab per year, plus `All_Years`.
- Add commands to emit the unified team‑week files for any year.

7) Tests / Invariants
- Add header and ordering tests (starter sequence, column order) for enhanced boxscores.
- Add schema tests for H2H normalized v2 to ensure cross‑era compatibility.

## Notes

- Co‑ownership semantics are documented in `RFFL.md` and `README.md`: co‑owners are equals; `_1/_2` are positional only. USD metrics split 50/50; all other team metrics attribute 100% to each co‑owner.
- Keep `alias_mapping.yaml` + `canonical_teams.csv` authoritative for identity.
