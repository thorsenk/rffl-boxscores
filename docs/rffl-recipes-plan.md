# RFFL Recipes — Project Plan (Public League Defaults)

This document defines the design, workflow, and milestones for a new, separate repository that orchestrates repeatable, validated ESPN Fantasy queries using a Recipes + Runner + Wizard pattern. The league is public; authentication cookies are not used by default.

## 1) Objectives

- Predictable, repeatable runs using declarative recipes.
- Guardrails that prevent drift: locked baselines; wizard creates versioned clones.
- Validated outputs: fail fast if exports are not clean; always produce validation reports.
- Clean separation of concerns: this repo orchestrates; `rffl-boxscores` does data/logic.
- Public-league first: no cookies required or passed; CI-friendly without secrets.

## 2) Out of Scope (Initial Phase)

- Editing or refactoring `rffl-boxscores` core logic beyond what’s needed for orchestration.
- Persisting run history in a database (file-based logs only initially).
- Web UI; this is a CLI-first workflow.

## 3) High-Level Design

- Recipes (YAML): Immutable definitions of a query (type, year/weeks, output, flags).
- Runner (CLI): Executes a recipe, logs commands/stdout/stderr, runs validations, and copies artifacts.
- Wizard (CLI): Guided creation/cloning of recipes from baselines; never edits baselines.
- Validation: Enforce `--require-clean` where applicable and run CSV validations post-export.
- Data routing: Outputs written into the `rffl-boxscores` data layout via `DATA_ROOT`.

## 4) Repository Structure

```
rffl-recipes/
  recipes/
    baselines/        # curated, locked YAMLs (immutable)
    local/            # wizard-generated, versioned clones
  src/rffl_recipes/
    __init__.py
    cli.py            # entrypoint that exposes subcommands
    runner.py         # execute recipes, log, validate, copy artifacts
    wizard.py         # interactive creation/cloning of recipes
    models.py         # Pydantic models for schema validation
    io.py             # file ops, path resolution, logging helpers
  scripts/
    run-*.sh          # optional convenience stubs calling the runner
  build/
    recipes/<name>/<timestamp>/  # runtime logs + copied outputs
  docs/
    rffl-recipes-plan.md
    README.md
  tests/
    test_schema.py
    test_command_builder.py
    test_runner_dry.py
  .env.example        # LEAGUE, DATA_ROOT; cookies commented (private-only)
  pyproject.toml      # Typer, Pydantic, PyYAML, ruff/black/mypy/pytest
  .pre-commit-config.yaml
  .gitignore
```

## 5) Recipe Schema (YAML)

```yaml
# Minimal example
name: weekly-enhanced-boxscores-2024
version: 1
type: export            # one of: export | h2h | draft | transactions | roster-changes | weekly-roster-changes
league: 323196
year: 2024
weeks: { start: 1, end: 18 }   # optional
out: ${DATA_ROOT}/data/seasons/2024/boxscores.csv
flags:
  fill_missing_slots: true
  require_clean: true
  tolerance: 0.0
post:
  validate: true
  lineup_validate: true        # export only
profile: active                 # active | preview
public_only: true               # enforce public-league mode (no cookies)
locked: true                    # baselines only; local clones default false
notes: |
  Public league; full season export with slot fill and strict validation.
```

Schema rules:
- `public_only: true` prohibits using cookies; runner strips/ignores any provided auth.
- `out` can use `${DATA_ROOT}` to route into the `rffl-boxscores` repo.
- `weeks` is optional; omit for full-season.
- Local clones set `locked: false` and increment `version` on changes.

## 6) CLI Specification

Primary binary: `rffl-recipes`

- `rffl-recipes run --recipe <path> [--override-locked] [--dry-run] [--data-root PATH]`
  - Loads and validates recipe; enforces `public_only` behavior.
  - Constructs exact `rffl-bs` command based on `type`.
  - Logs command + stdout/stderr to `build/recipes/<name>/<ts>/run.log`.
  - For `type: export`, runs `rffl-bs validate` and `rffl-bs validate-lineup`.
  - Copies outputs and reports into the build log directory.

- `rffl-recipes wizard [--baseline NAME] [--profile active|preview]`
  - Clones a baseline from `recipes/baselines/` into `recipes/local/<name>_vN.yaml`.
  - Prompts for league/year/weeks/out with sensible defaults.
  - Never edits baselines; sets `locked: false` in clones.

- `rffl-recipes list [--all]`
  - Lists available baselines and local recipes.

- `rffl-recipes validate-recipe <path>`
  - Validates YAML against schema and checks paths.

## 7) Command Construction

- export:
  ```
  rffl-bs export --league <L> --year <Y> [--start-week N] [--end-week M] \
    --out <OUT> [--fill-missing-slots] [--require-clean] [--tolerance X]
  ```
- h2h:
  ```
  rffl-bs h2h --league <L> --year <Y> [--start-week N] [--end-week M] --out <OUT>
  ```
- draft:
  ```
  rffl-bs draft --league <L> --year <Y> --out <OUT>
  ```

Public mode: No cookies are passed. If `public_only: true`, any provided `ESPN_S2`/`SWID` are ignored and a warning is logged.

## 8) Workflows

Active season (2019+):
1. Wizard: clone `weekly-enhanced-boxscores.yaml` → set year, weeks (1..current), league, out.
2. Run: `rffl-recipes run --recipe recipes/local/<name>_v1.yaml`.
3. Outputs: `${DATA_ROOT}/data/seasons/<year>/boxscores.csv` + validation reports under `reports/`.

Legacy season (<2019):
1. Wizard: clone `legacy-h2h.yaml` → set year and out.
2. Run: produces `${DATA_ROOT}/data/seasons/<year>/h2h.csv`.

Preview (current/next week):
1. Wizard with `profile: preview` → suggest week window and preview path (optional) or canonical path.
2. Run: same validations and logging.

## 9) Data Destinations

- Use `DATA_ROOT` to route into the `rffl-boxscores` repository:
  - `${DATA_ROOT}/data/seasons/<year>/boxscores.csv`
  - `${DATA_ROOT}/data/seasons/<year>/h2h.csv`
  - `${DATA_ROOT}/data/seasons/<year>/draft.csv`
  - `${DATA_ROOT}/data/seasons/<year>/reports/` (validation + derived reports)

## 10) Validation & Quality Gates

- Export runs with `--require-clean` (and `tolerance`) to fail fast on mismatches.
- Always run `rffl-bs validate` and `rffl-bs validate-lineup` for exports.
- Smoke checks in CI use `--dry-run` (no network) and optional public online runs for a tiny slice.

## 11) Error Handling

- Clear exit codes and messages; recipe path and name logged.
- Partial failures still capture logs and write whatever validation was available.
- Public access preflight (optional) warns if API access unexpectedly requires cookies.

## 12) Security & Privacy

- Public league mode by default; no secrets needed.
- If a recipe ever requires auth (private leagues), remove `public_only: true` and provide cookies via env/CI secrets (not planned initially).
- Logs redact any incidental cookie values defensively.

## 13) CI/CD

- GitHub Actions:
  - Lint: ruff + black --check
  - Types: mypy
  - Unit: pytest (schema, command builder, lock enforcement)
  - Smoke: `--dry-run` on baselines
  - Optional nightly: small real run using public access

## 14) Multi-Machine Setup

- Each machine: clone `rffl-recipes` and `rffl-boxscores`.
- `.env` per machine:
  - `DATA_ROOT=/path/to/rffl-boxscores`
  - `LEAGUE=<leagueId>`
  - (No cookies needed; public league)
- `pre-commit install`, Python 3.11+.

## 15) Milestones & Timeline

Phase 1 — Foundations (1–2 days)
- Scaffold repo, CLI skeletons, schema models, pre-commit, CI.
- Seed baselines: `weekly-enhanced-boxscores.yaml`, `legacy-h2h.yaml`, `draft.yaml`.

Phase 2 — Runner & Wizard (1–3 days)
- Implement runner with logging, public-mode enforcement, validation steps.
- Implement wizard cloning with versioning and prompts.

Phase 3 — Tests & Hardening (1–2 days)
- Unit tests, dry-run smoke tests, public online smoke (optional).
- Docs and examples.

Phase 4 — Rollout (ongoing)
- Use for weekly ops; add additional baseline recipes as needed.

## 16) Risks & Mitigations

- ESPN API shape changes: mitigate by pinning `rffl-boxscores` version and adding smoke tests.
- Accidental baseline edits: mitigate via `locked: true` and write-protect in CI.
- Path confusion across machines: mitigate with `${DATA_ROOT}` and path checks in runner.

## 17) Open Questions

- Commit `recipes/local/` to git for reproducibility, or `.gitignore` it? (Recommend commit; redact secrets if any in future.)
- Generate convenience `scripts/run-*.sh` by default? (Recommended.)

## 18) Next Steps

1. Approve this plan and repo name (`rffl-recipes`).
2. Scaffold repository with public-mode defaults.
3. Add seed baselines and wire initial runner/wizard.
4. Validate on both machines with `.env` and DATA_ROOT pointing to `rffl-boxscores`.

