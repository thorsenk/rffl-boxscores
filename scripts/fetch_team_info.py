#!/usr/bin/env python3
"""
Fetch team metadata from ESPN for each season and write CSVs:
- data/teams/teams_<year>.csv: year,team_id,team_abbrev,team_name
- data/teams/teams_all.csv: concatenation of all seasons

Uses env: LEAGUE, ESPN_S2, SWID (dotenv auto-loads .env).
"""
from __future__ import annotations

import csv
import os
import sys
from typing import List, Dict, Any
from espn_api.football import League  # type: ignore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    load_dotenv(find_dotenv(), override=False)
except Exception:
    # Fallback: naive .env parser for lines like `export KEY=VALUE`
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :]
                if "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    os.environ.setdefault(k.strip(), v)

# espn_api import is at top

DATA_SEASONS_DIR = os.path.join(ROOT, "data", "seasons")
OUT_DIR = os.path.join(ROOT, "data", "teams")


def get_env_int(name: str, default: int | None = None) -> int:
    v = os.getenv(name)
    if v is None:
        if default is None:
            raise SystemExit(f"Missing env {name}")
        return default
    try:
        return int(v)
    except Exception:
        raise SystemExit(f"Env {name} must be int, got: {v}")


def _get_team_abbrev(team) -> str:
    for attr in ["abbrev", "team_abbrev", "abbreviation", "team_id", "name"]:
        v = getattr(team, attr, None)
        if isinstance(v, str) and v:
            return v
    return str(getattr(team, "team_id", "")) or "UNKNOWN"


def _get_team_name(team) -> str:
    for attr in ["team_name", "name", "nickname", "location"]:
        v = getattr(team, attr, None)
        if isinstance(v, str) and v:
            return v
    return "UNKNOWN"


def _get_team_id(team) -> int:
    for attr in ["team_id", "teamId", "id"]:
        v = getattr(team, attr, None)
        if isinstance(v, int):
            return v
        try:
            return int(v)
        except Exception:
            pass
    return -1


def discovered_years() -> List[int]:
    years: List[int] = []
    if os.path.isdir(DATA_SEASONS_DIR):
        for name in os.listdir(DATA_SEASONS_DIR):
            try:
                y = int(name)
            except Exception:
                continue
            years.append(y)
    years.sort()
    return years


def write_year_csv(year: int, rows: List[Dict[str, Any]]) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"teams_{year}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["year", "team_id", "team_abbrev", "team_name"]
        )
        w.writeheader()
        w.writerows(rows)
    return path


def append_all_csv(rows: List[Dict[str, Any]]):
    path = os.path.join(OUT_DIR, "teams_all.csv")
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["year", "team_id", "team_abbrev", "team_name"]
        )
        if not exists:
            w.writeheader()
        w.writerows(rows)


def main(argv: List[str]) -> int:
    league_id = get_env_int("LEAGUE")
    espn_s2 = os.getenv("ESPN_S2")
    swid = os.getenv("SWID")

    years = discovered_years()
    if not years:
        raise SystemExit(f"No seasons found in {DATA_SEASONS_DIR}")

    # Reset all.csv
    all_csv_path = os.path.join(OUT_DIR, "teams_all.csv")
    if os.path.exists(all_csv_path):
        os.remove(all_csv_path)

    for year in years:
        try:
            lg = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        except Exception as e:
            print(f"! Skipping {year}: {e}")
            continue
        rows: List[Dict[str, Any]] = []
        for t in getattr(lg, "teams", []) or []:
            rows.append(
                {
                    "year": year,
                    "team_id": _get_team_id(t),
                    "team_abbrev": _get_team_abbrev(t),
                    "team_name": _get_team_name(t),
                }
            )
        if rows:
            write_year_csv(year, rows)
            append_all_csv(rows)
            print(f"{year}: {len(rows)} teams")
        else:
            print(f"{year}: no teams found")

    print("Done. Wrote teams_*.csv and teams_all.csv under data/teams/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
