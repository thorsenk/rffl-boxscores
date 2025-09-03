#!/usr/bin/env python3
"""
Scan data/seasons/* for team abbreviations and produce:
- data/teams/observed_abbrevs.csv: year,source,team_abbrev,count
- data/teams/all_abbrevs.csv: team_abbrev,years,sources,total_count
- data/teams/canonicals.yaml: scaffold for manual canonical mapping

Notes
- This does not guess franchise groupings. Each unique abbrev becomes its own
  canonical by default. You can merge by adding aliases under one canonical.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Tuple, Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_SEASONS_DIR = os.path.join(ROOT, "data", "seasons")
OUT_DIR = os.path.join(ROOT, "data", "teams")


def read_csv_rows(path: str) -> Iterable[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def collect_abbrevs() -> Tuple[Dict[Tuple[int, str], Counter], Dict[str, set], Dict[str, set]]:
    per_year_source: Dict[Tuple[int, str], Counter] = defaultdict(Counter)
    years_by_abbrev: Dict[str, set] = defaultdict(set)
    sources_by_abbrev: Dict[str, set] = defaultdict(set)

    if not os.path.isdir(DATA_SEASONS_DIR):
        raise SystemExit(f"Missing data path: {DATA_SEASONS_DIR}")

    for name in sorted(os.listdir(DATA_SEASONS_DIR)):
        try:
            year = int(name)
        except Exception:
            continue
        ydir = os.path.join(DATA_SEASONS_DIR, name)
        if not os.path.isdir(ydir):
            continue

        # draft.csv
        draft_path = os.path.join(ydir, "draft.csv")
        if os.path.exists(draft_path):
            src = "draft"
            for r in read_csv_rows(draft_path):
                for col in ("team_abbrev", "nominating_team"):
                    ab = (r.get(col) or "").strip()
                    if ab:
                        per_year_source[(year, src)][ab] += 1
                        years_by_abbrev[ab].add(year)
                        sources_by_abbrev[ab].add(src)

        # h2h.csv (legacy seasons)
        h2h_path = os.path.join(ydir, "h2h.csv")
        if os.path.exists(h2h_path):
            src = "h2h"
            for r in read_csv_rows(h2h_path):
                for col in ("home_team", "away_team", "winner"):
                    ab = (r.get(col) or "").strip()
                    if ab and ab != "TIE":
                        per_year_source[(year, src)][ab] += 1
                        years_by_abbrev[ab].add(year)
                        sources_by_abbrev[ab].add(src)

        # boxscores.csv (2019+)
        box_path = os.path.join(ydir, "boxscores.csv")
        if os.path.exists(box_path):
            src = "boxscores"
            for r in read_csv_rows(box_path):
                ab = (r.get("team_abbrev") or "").strip()
                if ab:
                    per_year_source[(year, src)][ab] += 1
                    years_by_abbrev[ab].add(year)
                    sources_by_abbrev[ab].add(src)

    return per_year_source, years_by_abbrev, sources_by_abbrev


def load_latest_names_by_abbrev() -> Dict[str, str]:
    """Read data/teams/teams_all.csv and return latest team_name per abbrev."""
    teams_all = os.path.join(OUT_DIR, "teams_all.csv")
    latest: Dict[str, Tuple[int, str]] = {}
    if not os.path.exists(teams_all):
        return {}
    with open(teams_all, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ab = (r.get("team_abbrev") or "").strip()
            nm = (r.get("team_name") or "").strip()
            try:
                yr = int(r.get("year") or 0)
            except Exception:
                continue
            if not ab or not nm:
                continue
            prev = latest.get(ab)
            if prev is None or yr >= prev[0]:
                latest[ab] = (yr, nm)
    return {k: v[1] for k, v in latest.items()}


def ensure_out_dir() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)


def write_observed_csv(per_year_source: Dict[Tuple[int, str], Counter]) -> str:
    out = os.path.join(OUT_DIR, "observed_abbrevs.csv")
    rows: List[Dict[str, str]] = []
    for (year, src), counter in sorted(per_year_source.items()):
        for ab, count in sorted(counter.items()):
            rows.append({
                "year": str(year),
                "source": src,
                "team_abbrev": ab,
                "count": str(count),
            })
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["year", "source", "team_abbrev", "count"])
        w.writeheader()
        w.writerows(rows)
    return out


def write_all_csv(years_by_abbrev: Dict[str, set], sources_by_abbrev: Dict[str, set]) -> str:
    out = os.path.join(OUT_DIR, "all_abbrevs.csv")
    rows: List[Dict[str, str]] = []
    for ab in sorted(years_by_abbrev.keys() | sources_by_abbrev.keys()):
        years = sorted(years_by_abbrev.get(ab, set()))
        sources = sorted(sources_by_abbrev.get(ab, set()))
        rows.append({
            "team_abbrev": ab,
            "years": ",".join(str(y) for y in years),
            "sources": ",".join(sources),
            "total_count": "",
        })
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["team_abbrev", "years", "sources", "total_count"])
        w.writeheader()
        w.writerows(rows)
    return out


def write_canonicals_yaml(years_by_abbrev: Dict[str, set], sources_by_abbrev: Dict[str, set]) -> str:
    out = os.path.join(OUT_DIR, "canonicals.yaml")
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    lines: List[str] = []
    lines.append("version: 1")
    lines.append(f"generated_at: {now}")
    lines.append("notes: |-")
    lines.append("  Canonical mapping scaffold.\n  - Each entry defaults to identity.\n  - To merge historical variants, pick a canonical abbrev and move others into its aliases list.\n  - Keep years/sources lists to help validate coverage.")
    lines.append("teams:")
    latest_names = load_latest_names_by_abbrev()
    for ab in sorted(years_by_abbrev.keys() | sources_by_abbrev.keys()):
        years = sorted(years_by_abbrev.get(ab, set()))
        sources = sorted(sources_by_abbrev.get(ab, set()))
        lines.append(f"  - canonical: {ab}")
        lines.append(f"    aliases: [{ab}]")
        name = latest_names.get(ab)
        if name:
            # basic YAML string escaping for colon in names
            if ":" in name:
                name_val = f'"{name}"'
            else:
                name_val = name
            lines.append(f"    name: {name_val}")
        if years:
            lines.append(f"    years: [{', '.join(str(y) for y in years)}]")
        if sources:
            lines.append(f"    sources: [{', '.join(sources)}]")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out


def main(argv: List[str]) -> int:
    ensure_out_dir()
    per_year_source, years_by_abbrev, sources_by_abbrev = collect_abbrevs()
    observed = write_observed_csv(per_year_source)
    all_csv = write_all_csv(years_by_abbrev, sources_by_abbrev)
    canon = write_canonicals_yaml(years_by_abbrev, sources_by_abbrev)
    print("Wrote:")
    print(" -", os.path.relpath(observed, ROOT))
    print(" -", os.path.relpath(all_csv, ROOT))
    print(" -", os.path.relpath(canon, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
