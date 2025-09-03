#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from typing import Dict, List, Set, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from apply_alias_mapping import load_aliases, build_alias_index, resolve_canonical  # type: ignore


def load_canonicals(year: int) -> Set[str]:
    path = os.path.join(ROOT, "data", "teams", "canonical_teams.csv")
    if not os.path.exists(path):
        return set()
    vals: Set[str] = set()
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                y = int(row.get("season_year", "0"))
            except Exception:
                continue
            if y == year:
                code = (row.get("team_code") or "").strip()
                if code:
                    vals.add(code)
    return vals


def load_codes_from_file(path: str) -> Set[str]:
    codes: Set[str] = set()
    if not os.path.exists(path):
        return codes
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        cols = set(r.fieldnames or [])
        if {"home_team", "away_team"}.issubset(cols):
            for row in r:
                for c in ("home_team", "away_team", "winner"):
                    v = (row.get(c) or "").strip()
                    if v and v != "TIE":
                        codes.add(v)
        elif "team_abbrev" in cols:
            for row in r:
                v = (row.get("team_abbrev") or "").strip()
                if v:
                    codes.add(v)
    return codes


def main(year: int) -> int:
    mapping_path = os.path.join(ROOT, "data", "teams", "alias_mapping.yaml")
    aliases = load_aliases(mapping_path)
    idx = build_alias_index(aliases)
    canon_set = load_canonicals(year)

    ydir = os.path.join(ROOT, "data", "seasons", str(year))
    codes: Set[str] = set()
    for fname in ("h2h.csv", "draft.csv", "boxscores.csv"):
        codes |= load_codes_from_file(os.path.join(ydir, fname))

    rows: List[dict] = []
    for c in sorted(codes):
        can = resolve_canonical(c, year, idx)
        known = "yes" if (can in canon_set or can == "AWAY") else "no"
        rows.append({
            "raw_code": c,
            "canonical": can,
            "is_canonical_known": known,
        })

    outdir = os.path.join(ydir, "reports")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "alias_coverage.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["raw_code", "canonical", "is_canonical_known"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} codes)")
    return 0


if __name__ == "__main__":
    import sys
    y = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    raise SystemExit(main(y))
