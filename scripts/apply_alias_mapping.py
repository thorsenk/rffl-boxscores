#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_aliases(path: str) -> List[dict]:
    import yaml  # PyYAML available via espn_api deps; if not, we could fallback

    with open(path, encoding="utf-8") as f:
        y = yaml.safe_load(f)
    return y.get("aliases", []) if isinstance(y, dict) else []


def build_alias_index(aliases: List[dict]) -> Dict[str, List[dict]]:
    idx: Dict[str, List[dict]] = {}
    for a in aliases:
        alias = a.get("alias")
        if not alias:
            continue
        idx.setdefault(alias, []).append(a)
    return idx


def resolve_canonical(
    abbrev: str, year: Optional[int], idx: Dict[str, List[dict]]
) -> str:
    rules = idx.get(abbrev)
    if not rules:
        return abbrev
    if year is None:
        # If no year provided, prefer a rule without year bounds, else first
        for r in rules:
            if not r.get("start_year") and not r.get("end_year"):
                return r.get("canonical", abbrev)
        return rules[0].get("canonical", abbrev)
    # Prefer rule that matches year within [start_year, end_year]
    best = None
    for r in rules:
        s = r.get("start_year")
        e = r.get("end_year")
        if (s is None or year >= int(s)) and (e is None or year <= int(e)):
            best = r
            break
    return (best or rules[0]).get("canonical", abbrev)


def load_canonical_map() -> Dict[Tuple[int, str], Dict[str, str]]:
    """Load canonical team metadata keyed by (year, team_code)."""
    path = os.path.join(ROOT, "data", "teams", "canonical_teams.csv")
    meta: Dict[Tuple[int, str], Dict[str, str]] = {}
    if not os.path.exists(path):
        return meta
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                y = int(row.get("season_year", "0"))
            except Exception:
                continue
            code = (row.get("team_code") or "").strip()
            if not y or not code:
                continue
            meta[(y, code)] = {
                "team_full_name": (row.get("team_full_name") or "").strip(),
                "is_co_owned": (row.get("is_co_owned") or "").strip(),
                # Support new canonical names with fallback to legacy
                "owner_code_1": (
                    row.get("owner_code_1") or row.get("owner_code") or ""
                ).strip(),
                "owner_code_2": (
                    row.get("owner_code_2") or row.get("co_owner_code") or ""
                ).strip(),
            }
    return meta


def detect_type(headers: List[str]) -> str:
    cols = set(h.strip() for h in headers)
    if {"home_team", "away_team", "winner"}.issubset(cols):
        return "h2h"
    if "team_abbrev" in cols and {"week", "matchup"}.issubset(cols):
        return "boxscores"
    if "team_abbrev" in cols and {"year", "round"}.issubset(cols):
        return "draft"
    return "unknown"


def normalize_file(
    path: str, out_path: str, year: Optional[int], idx: Dict[str, List[dict]]
) -> Dict[str, int]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        ftype = detect_type(headers)
        rows: List[dict] = []
        seen = set()
        meta = load_canonical_map()
        if ftype == "h2h":
            new_headers = headers + [
                "home_code",
                "away_code",
                "winner_code",
                "home_team_full_name",
                "away_team_full_name",
                "winner_team_full_name",
            ]
            for r in reader:
                h = r.get("home_team", "")
                a = r.get("away_team", "")
                w = r.get("winner", "")
                hc = resolve_canonical(h, year, idx)
                ac = resolve_canonical(a, year, idx)
                wc = resolve_canonical(w, year, idx) if w not in ("TIE",) else "TIE"
                r["home_code"] = hc
                r["away_code"] = ac
                r["winner_code"] = wc
                # attach names from canonical map
                if year is not None:
                    r["home_team_full_name"] = meta.get((year, hc), {}).get(
                        "team_full_name", ""
                    )
                    r["away_team_full_name"] = meta.get((year, ac), {}).get(
                        "team_full_name", ""
                    )
                    r["winner_team_full_name"] = (
                        meta.get((year, wc), {}).get("team_full_name", "")
                        if wc != "TIE"
                        else "TIE"
                    )
                rows.append(r)
                seen.update([h, a, w])
        elif ftype in ("boxscores", "draft"):
            new_headers = headers + [
                "team_code",
                "team_full_name",
                "is_co_owned",
                "owner_code_1",
                "owner_code_2",
            ]
            for r in reader:
                ab = r.get("team_abbrev", "")
                tc = resolve_canonical(ab, year, idx)
                r["team_code"] = tc
                if year is not None:
                    info = meta.get((year, tc), {})
                    r["team_full_name"] = info.get("team_full_name", "")
                    r["is_co_owned"] = info.get("is_co_owned", "")
                    r["owner_code_1"] = info.get("owner_code_1", "")
                    r["owner_code_2"] = info.get("owner_code_2", "")
                rows.append(r)
                seen.add(ab)
        else:
            raise SystemExit(f"Unsupported CSV format: {path}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=new_headers)
        w.writeheader()
        w.writerows(rows)

    return {"unique_seen": len([s for s in seen if s])}


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply RFFL alias mapping to season CSVs")
    ap.add_argument("--file", required=True, help="CSV to normalize")
    ap.add_argument("--year", type=int, help="Season year for mapping context")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument(
        "--mapping", default=os.path.join(ROOT, "data", "teams", "alias_mapping.yaml")
    )
    args = ap.parse_args()

    aliases = load_aliases(args.mapping)
    idx = build_alias_index(aliases)
    stats = normalize_file(args.file, args.out, args.year, idx)
    print(f"Normalized {args.file} -> {args.out} ({stats['unique_seen']} unique codes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
