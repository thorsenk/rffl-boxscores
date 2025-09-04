.PHONY: help normalize drafts master clean_master all venv install fmt lint test audit devclean lint-files print-in verify

# More portable default, still 3.10+ compliant; override with `make venv PYTHON=/opt/homebrew/bin/python3`
PYTHON ?= python3
VENV_ACT := . .venv/bin/activate &&
MASTER_IN := build/outputs/rffl_master_db_powerbook_rffl_codex_db_1.csv

# All years discovered in data/seasons
YEARS ?= $(shell ls -1 data/seasons | rg '^[0-9]+$$' | sort)

# Path to your source master CSV (can be overridden)
print-in:
	@printf 'Input: %s\n' "$(MASTER_IN)"

help:
	@echo "make normalize YEAR=YYYY   # normalize one season"
	@echo "make normalize             # normalize all seasons"
	@echo "make drafts                # generate corrected + snake drafts for all seasons"
	@echo "make master                # build master_v2/v2_rs/v2 (from $(MASTER_IN))"
	@echo "make clean_master          # drop legacy owner columns from master_v2"
	@echo "make all                   # normalize (all), drafts, master, clean_master"

normalize:
ifdef YEAR
	@"$(PYTHON)" scripts/normalize_season.py --year "$(YEAR)"
else
	@for y in $(YEARS); do \
	  "$(PYTHON)" scripts/normalize_season.py --year $$y; \
	done
endif

drafts:
	@for y in $(YEARS); do \
	  if [ -f data/seasons/$$y/draft.csv ]; then \
	    "$(PYTHON)" scripts/apply_alias_mapping.py --file data/seasons/$$y/draft.csv --year $$y --out data/seasons/$$y/reports/$$y-Draft-Correct-Canonicals.csv; \
	    "$(PYTHON)" scripts/make_draft_snake.py --year $$y --out data/seasons/$$y/reports/$$y-Draft-Snake-Canonicals.csv; \
	  fi; \
	done

master:
	@mkdir -p build/outputs
	@"$(PYTHON)" scripts/fill_master_db.py --in "$(MASTER_IN)" --out build/outputs/master_v2.csv
	@"$(PYTHON)" scripts/fill_master_rs.py --in build/outputs/master_v2.csv --out build/outputs/master_v2_rs.csv
	@"$(PYTHON)" scripts/fill_master_ps.py --in build/outputs/master_v2_rs.csv --out build/outputs/RFFL_MASTER_DB_v2.csv

clean_master:
	@"$(PYTHON)" scripts/make_master_clean.py --in build/outputs/RFFL_MASTER_DB_v2.csv --out build/outputs/RFFL_MASTER_DB_clean.csv

all: normalize drafts master clean_master

# --- QoL targets for local dev ---
venv:
	"$(PYTHON)" -m venv .venv

install:
	$(VENV_ACT) pip install -U pip && pip install -e ".[dev]"

fmt:
	$(VENV_ACT) black .

lint:
	$(VENV_ACT) flake8

test:
	$(VENV_ACT) pytest -q

audit:
	bash scripts/safe_audit.sh

devclean:
	rm -rf .venv venv build dist *.egg-info

lint-files:
	@violations=$$(git ls-files | awk '/[[:space:]]/ {print; next} /[^ -~]/ {print}'); \
	if [ -n "$$violations" ]; then \
	  echo "❌ Invalid filenames (must be ASCII, no spaces/emoji):"; \
	  echo "$$violations"; exit 1; \
	else echo "✅ Filenames clean"; fi

# Run all checks without mutating files
verify:
	$(VENV_ACT) black --check .
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) audit
	$(MAKE) lint-files
	$(VENV_ACT) rffl-bs --help >/dev/null
	$(VENV_ACT) python -m rffl_boxscores.cli --help >/dev/null
	@echo "✅ verify: all checks passed"
