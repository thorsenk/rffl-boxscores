#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str, rows: List[dict], fieldnames: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _first(r: dict, key: str, default: str = "") -> str:
    v = r.get(key)
    return str(v) if v is not None else default


def make_teamweek_unified(year: int, out_path: str) -> Tuple[int, str]:
    src_path = os.path.join(
        ROOT, "data", "seasons", str(year), "reports", "boxscores_normalized.csv"
    )
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Missing normalized boxscores for {year}: {src_path}")

    rows = read_csv(src_path)

    # Group per team-week
    from collections import defaultdict

    teamweeks: Dict[Tuple[str, str, str, str], dict] = {}

    for r in rows:
        season = _first(r, "season_year")
        week = _first(r, "week")
        matchup = _first(r, "matchup")
        code = _first(r, "team_code")
        if not season or not week or not matchup or not code:
            continue
        key = (season, week, matchup, code)
        if key not in teamweeks:
            teamweeks[key] = {
                "season_year": season,
                "week": week,
                "matchup": matchup,
                "team_code": code,
                "is_co_owned?": _first(r, "is_co_owned?"),
                "team_owner_1": _first(r, "team_owner_1"),
                "team_owner_2": _first(r, "team_owner_2"),
                "team_projected_total": _first(r, "team_projected_total"),
                "team_actual_total": _first(r, "team_actual_total"),
            }
    # accumulate unique team weeks for pairing
    by_matchup: Dict[Tuple[str, str, str], List[dict]] = defaultdict(list)
    for tw in teamweeks.values():
        by_matchup[(tw["season_year"], tw["week"], tw["matchup"])].append(tw)

    # Pair into opponent view
    out_rows: List[dict] = []
    for key, teams in by_matchup.items():
        if len(teams) != 2:
            # skip malformed matchups
            continue
        t1, t2 = teams[0], teams[1]
        # produce t1 row
        try:
            s1 = float(t1.get("team_actual_total") or 0.0)
            s2 = float(t2.get("team_actual_total") or 0.0)
        except Exception:
            s1 = s2 = 0.0
        margin = round(s1 - s2, 2)
        result = "W" if margin > 0 else ("L" if margin < 0 else "T")
        out_rows.append(
            {
                **t1,
                "opponent_code": t2.get("team_code", ""),
                "opp_is_co_owned?": t2.get("is_co_owned?", ""),
                "opp_owner_1": t2.get("team_owner_1", ""),
                "opp_owner_2": t2.get("team_owner_2", ""),
                "opp_actual_total": t2.get("team_actual_total", ""),
                "result": result,
                "margin": f"{margin}",
            }
        )
        # produce t2 row
        margin2 = -margin
        result2 = "W" if margin2 > 0 else ("L" if margin2 < 0 else "T")
        out_rows.append(
            {
                **t2,
                "opponent_code": t1.get("team_code", ""),
                "opp_is_co_owned?": t1.get("is_co_owned?", ""),
                "opp_owner_1": t1.get("team_owner_1", ""),
                "opp_owner_2": t1.get("team_owner_2", ""),
                "opp_actual_total": t1.get("team_actual_total", ""),
                "result": result2,
                "margin": f"{margin2}",
            }
        )

    fieldnames = [
        "season_year",
        "week",
        "matchup",
        "team_code",
        "is_co_owned?",
        "team_owner_1",
        "team_owner_2",
        "opponent_code",
        "opp_is_co_owned?",
        "opp_owner_1",
        "opp_owner_2",
        "team_projected_total",
        "team_actual_total",
        "opp_actual_total",
        "result",
        "margin",
    ]

    write_csv(out_path, out_rows, fieldnames)
    return len(out_rows), out_path


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Collapse enhanced boxscores into team-week unified file"
    )
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    n, path = make_teamweek_unified(args.year, args.out)
    print(f"Wrote {n} rows -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
