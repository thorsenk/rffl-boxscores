#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, List, Tuple

# Reuse helpers from apply_alias_mapping
from apply_alias_mapping import (
    load_aliases,
    build_alias_index,
    resolve_canonical,
    load_canonical_map,
)  # type: ignore

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


def make_h2h_teamweek(year: int, mapping_path: str, out_path: str) -> Tuple[int, str]:
    src_path = os.path.join(ROOT, "data", "seasons", str(year), "h2h.csv")
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Missing h2h.csv for {year}: {src_path}")

    rows = read_csv(src_path)
    aliases = load_aliases(mapping_path)
    idx = build_alias_index(aliases)
    canon_meta = load_canonical_map()

    out_rows: List[dict] = []
    for r in rows:
        wk = (r.get("week") or "").strip()
        mu = (r.get("matchup") or "").strip()
        h_ab = (r.get("home_team") or "").strip()
        a_ab = (r.get("away_team") or "").strip()
        try:
            hs = float(r.get("home_score") or 0.0)
            as_ = float(r.get("away_score") or 0.0)
        except Exception:
            # Skip malformed
            continue

        # Canonical codes
        hc = resolve_canonical(h_ab, year, idx)
        ac = resolve_canonical(a_ab, year, idx)
        h_meta = canon_meta.get((year, hc), {})
        a_meta = canon_meta.get((year, ac), {})

        # Results
        if hs > as_:
            h_res, a_res = "W", "L"
        elif as_ > hs:
            h_res, a_res = "L", "W"
        else:
            h_res = a_res = "T"
        h_margin = round(hs - as_, 2)
        a_margin = round(as_ - hs, 2)

        # Rows: one per team-week
        out_rows.append(
            {
                "season_year": str(year),
                "week": wk,
                "matchup": mu,
                "team_code": hc,
                "is_co_owned?": h_meta.get("is_co_owned", ""),
                "team_owner_1": h_meta.get("owner_code_1", ""),
                "team_owner_2": h_meta.get("owner_code_2", ""),
                "opponent_code": ac,
                "opp_is_co_owned?": a_meta.get("is_co_owned", ""),
                "opp_owner_1": a_meta.get("owner_code_1", ""),
                "opp_owner_2": a_meta.get("owner_code_2", ""),
                "team_projected_total": "",
                "team_actual_total": f"{hs}",
                "opp_actual_total": f"{as_}",
                "result": h_res,
                "margin": f"{h_margin}",
            }
        )
        out_rows.append(
            {
                "season_year": str(year),
                "week": wk,
                "matchup": mu,
                "team_code": ac,
                "is_co_owned?": a_meta.get("is_co_owned", ""),
                "team_owner_1": a_meta.get("owner_code_1", ""),
                "team_owner_2": a_meta.get("owner_code_2", ""),
                "opponent_code": hc,
                "opp_is_co_owned?": h_meta.get("is_co_owned", ""),
                "opp_owner_1": h_meta.get("owner_code_1", ""),
                "opp_owner_2": h_meta.get("owner_code_2", ""),
                "team_projected_total": "",
                "team_actual_total": f"{as_}",
                "opp_actual_total": f"{hs}",
                "result": a_res,
                "margin": f"{a_margin}",
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
        description="Build team-week H2H normalized CSV (legacy seasons)"
    )
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--mapping", default=os.path.join(ROOT, "data", "teams", "alias_mapping.yaml")
    )
    args = ap.parse_args()

    n, path = make_h2h_teamweek(args.year, args.mapping, args.out)
    print(f"Wrote {n} rows -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
