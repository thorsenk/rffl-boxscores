#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from typing import List, Dict, Tuple

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


def season_years() -> List[int]:
    base = os.path.join(ROOT, "data", "seasons")
    years = [int(name) for name in os.listdir(base) if name.isdigit()]
    return sorted(years)


def keeper_rows_from_snake(year: int) -> List[dict]:
    path = os.path.join(
        ROOT, "data", "seasons", str(year), "reports", f"{year}-Draft-Snake-Canonicals.csv"
    )
    if not os.path.exists(path):
        return []
    rows = read_csv(path)
    # Filter rows where is_a_keeper? == Yes (case-insensitive)
    out: List[dict] = []
    for r in rows:
        keep = (r.get("is_a_keeper?") or "").strip().lower() in {"yes", "true", "1"}
        if keep:
            out.append(r)
    return out


def audit_year(year: int) -> Tuple[str, str]:
    """Write per-season keeper detail and summary; return paths."""
    keepers = keeper_rows_from_snake(year)
    outdir = os.path.join(ROOT, "data", "seasons", str(year), "reports")
    detail_path = os.path.join(outdir, "keepers.csv")
    summary_path = os.path.join(outdir, "keepers_summary.csv")

    if keepers:
        # Normalize detail columns (reuse subset from snake)
        detail_fields = [
            "year",
            "round",
            "round_pick",
            "overall_pick",
            "team_code",
            "team_full_name",
            "owner_code_1",
            "owner_code_2",
            "player_id",
            "player_name",
            "player_NFL_team",
            "player_position",
        ]
        # Coerce keys to ensure all present
        detail_rows: List[dict] = []
        for r in keepers:
            row = {k: r.get(k, "") for k in detail_fields}
            detail_rows.append(row)
        write_csv(detail_path, detail_rows, detail_fields)

        # Build summary by team_code
        from collections import defaultdict

        groups: Dict[str, Dict[str, any]] = defaultdict(lambda: {
            "season_year": str(year),
            "team_code": "",
            "keepers_count": 0,
            "rounds": [],
            "players": [],
        })
        for r in keepers:
            code = (r.get("team_code") or "").strip()
            groups[code]["team_code"] = code
            groups[code]["keepers_count"] += 1
            rnd = (r.get("round") or "").strip()
            if rnd:
                groups[code]["rounds"].append(rnd)
            pname = (r.get("player_name") or "").strip()
            if pname:
                groups[code]["players"].append(pname)
        summary_rows: List[dict] = []
        for code, data in groups.items():
            summary_rows.append(
                {
                    "season_year": data["season_year"],
                    "team_code": data["team_code"],
                    "keepers_count": data["keepers_count"],
                    "rounds": ",".join(data["rounds"]),
                    "players": ",".join(data["players"]),
                }
            )
        summary_fields = [
            "season_year",
            "team_code",
            "keepers_count",
            "rounds",
            "players",
        ]
        write_csv(summary_path, summary_rows, summary_fields)
    else:
        # No keepers (or file missing) -> write empty shells for consistency
        write_csv(detail_path, [], [
            "year",
            "round",
            "round_pick",
            "overall_pick",
            "team_code",
            "team_full_name",
            "owner_code_1",
            "owner_code_2",
            "player_id",
            "player_name",
            "player_NFL_team",
            "player_position",
        ])
        write_csv(summary_path, [], [
            "season_year",
            "team_code",
            "keepers_count",
            "rounds",
            "players",
        ])

    return detail_path, summary_path


def audit_all(year_filter: List[int] | None = None) -> Tuple[str, str]:
    years = year_filter or season_years()
    all_detail: List[dict] = []
    all_summary: List[dict] = []
    for y in years:
        dpath, spath = audit_year(y)
        # Append to combined
        for r in read_csv(dpath):
            all_detail.append(r)
        for r in read_csv(spath):
            all_summary.append(r)
    out_dir = os.path.join(ROOT, "build", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    detail_out = os.path.join(out_dir, "keepers_all.csv")
    summary_out = os.path.join(out_dir, "keepers_summary_all.csv")
    # Derive fields from first row if any
    if all_detail:
        detail_fields = list(all_detail[0].keys())
    else:
        detail_fields = [
            "year",
            "round",
            "round_pick",
            "overall_pick",
            "team_code",
            "team_full_name",
            "owner_code_1",
            "owner_code_2",
            "player_id",
            "player_name",
            "player_NFL_team",
            "player_position",
        ]
    if all_summary:
        summary_fields = list(all_summary[0].keys())
    else:
        summary_fields = [
            "season_year",
            "team_code",
            "keepers_count",
            "rounds",
            "players",
        ]
    write_csv(detail_out, all_detail, detail_fields)
    write_csv(summary_out, all_summary, summary_fields)
    return detail_out, summary_out


def main() -> int:
    ap = argparse.ArgumentParser(description="Keeper audit across seasons")
    ap.add_argument("--years", nargs="*", type=int, help="Optional list of years to audit")
    args = ap.parse_args()

    d, s = audit_all(args.years)
    print("Wrote:", os.path.relpath(d, ROOT))
    print("Wrote:", os.path.relpath(s, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

