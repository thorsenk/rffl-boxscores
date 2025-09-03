.PHONY: help normalize drafts master clean_master all

# All years discovered in data/seasons
YEARS ?= $(shell ls -1 data/seasons | rg '^[0-9]+$$' | sort)

# Path to your source master CSV (can be overridden)
MASTER_IN ?= ✌️ RFFL MASTER DB POWERBOOK - RFFL_CODEX_DB (1).csv

help:
	@echo "make normalize YEAR=YYYY   # normalize one season"
	@echo "make normalize             # normalize all seasons"
	@echo "make drafts                # generate corrected + snake drafts for all seasons"
	@echo "make master                # build master_v2/v2_rs/v2 (from $(MASTER_IN))"
	@echo "make clean_master          # drop legacy owner columns from master_v2"
	@echo "make all                   # normalize (all), drafts, master, clean_master"

normalize:
ifdef YEAR
	@python3 scripts/normalize_season.py --year $(YEAR)
else
	@for y in $(YEARS); do \
	  python3 scripts/normalize_season.py --year $$y; \
	done
endif

drafts:
	@for y in $(YEARS); do \
	  if [ -f data/seasons/$$y/draft.csv ]; then \
	    python3 scripts/apply_alias_mapping.py --file data/seasons/$$y/draft.csv --year $$y --out data/seasons/$$y/reports/$$y-Draft-Correct-Canonicals.csv; \
	    python3 scripts/make_draft_snake.py --year $$y --out data/seasons/$$y/reports/$$y-Draft-Snake-Canonicals.csv; \
	  fi; \
	done

master:
	@mkdir -p build/outputs
	@python3 scripts/fill_master_db.py --in "$(MASTER_IN)" --out build/outputs/master_v2.csv
	@python3 scripts/fill_master_rs.py --in build/outputs/master_v2.csv --out build/outputs/master_v2_rs.csv
	@python3 scripts/fill_master_ps.py --in build/outputs/master_v2_rs.csv --out build/outputs/RFFL_MASTER_DB_v2.csv

clean_master:
	@python3 scripts/make_master_clean.py --in build/outputs/RFFL_MASTER_DB_v2.csv --out build/outputs/RFFL_MASTER_DB_clean.csv

all: normalize drafts master clean_master

