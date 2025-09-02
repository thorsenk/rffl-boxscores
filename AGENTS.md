Agent Command Reference

Overview
- Audience: solo‑vibecoding + agent workflows.
- Goal: fast, predictable commands with small, stable outputs.

Environment
- Vars: `LEAGUE`, `ESPN_S2`, `SWID` (dotenv auto‑loads `.env`).
- Precedence: CLI flags > real env > `.env`.

CLI Commands
- `rffl-bs --help`: show main help.
- `rffl-bs export --league <id> --year <year> [--start-week N] [--end-week N] [--out PATH] [--espn-s2 S2] [--swid SWID] [--fill-missing-slots]`
  Export season boxscores to CSV (`validated_boxscores_<year>.csv` by default). Use `--fill-missing-slots` to insert 0‑pt placeholders for missing required starters (see Enhanced Matchup Box Scores below).
- `rffl-bs h2h --league <id> --year <year> [--start-week N] [--end-week N] [--out PATH] [--espn-s2 S2] [--swid SWID]`
  Export simplified head‑to‑head matchup results to CSV (`h2h_<year>.csv` by default). Columns: week, matchup, home_team, away_team, home_score, away_score, winner, margin. Compatible with older seasons (pre‑2019) where per‑player boxscores aren’t reliable.
- `rffl-bs validate <csv> [--tolerance FLOAT]`
  Validate sums and starter counts; writes `<csv>_validation_report.csv` on issues.
- `rffl-bs validate-lineup <csv> [--out PATH]`
  Validate RFFL lineup rules; writes `<csv>_lineup_validation_report.csv` on issues.

Enhanced Matchup Box Scores
- Normalizes ESPN slots/positions into stable slots: QB, RB, WR, TE, FLEX, D/ST, K, Bench, IR.
- Starters are only QB/RB/WR/TE/FLEX/D/ST/K; bench and IR excluded from totals.
- Rounds per‑player to 2 decimals first; team totals are sum of rounded starters → exact match with rows.
- Optional `--fill-missing-slots` ensures 9 starters by inserting `EMPTY SLOT - {SLOT}` rows with 0.0 points when ESPN data has incomplete starters (does not change totals). See `RFFL.md`.

Vibe Helpers (source `./vibe.sh`)
- `bs <year> [start] [end] [out]`: export using `$LEAGUE`.
- `h2h <year> [start] [end] [out]`: export simplified H2H results using `$LEAGUE`.
- `bsv <year>`: validate `validated_boxscores_<year>.csv`.
- `bsl <year>`: lineup validation for `validated_boxscores_<year>.csv`.
- `bsp <year>`: export weeks 15–17 (playoffs helper).
- `withac --interval N [--push] -- <cmd>`: run `<cmd>` with auto‑commit in background.
- `autocommit [interval] [push]`: loop commits every `interval` seconds (default 60).
- `autocommit_idle <idle_minutes> [push]`: commit on changes; exit after idle.
- `autocommit_once [push]`: commit next change then exit.
- `acstop`: stop auto‑commit loop.
- `audit`: safe audit; prints summaries, saves full logs to `build/audit/`.
- `pview <file> [lines]`: print first N lines (default 200) of a file.

Scripts
- `scripts/auto_commit.sh`
  Env: `INTERVAL` (sec), `PUSH` (0/1), `ONCE` (0/1), `MAX_IDLE_MINUTES`, `BACKOFF` (0/1), `SKIP_CI` (default 1 → adds "[skip ci]").
- `scripts/with_autocommit.sh`:
  Wrapper to run a dev command with auto‑commit; stops loop on exit.
- `scripts/safe_audit.sh`:
  Collects diagnostics; truncates console output; writes logs to `build/audit/`.

Exit Codes (CLI)
- `0`: success.
- `1`: argument/config/network/data errors (friendly message via Typer).

Safe Output Tips
- Prefer `pview file 200`, `sed -n '1,200p' file`, or `rg pattern | head -n 200`.
- Avoid dumping large CSVs or logs into chat; use `audit` then open files from `build/audit/`.
