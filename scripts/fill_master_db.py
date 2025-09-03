#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, Tuple, List, Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_canonicals() -> Dict[Tuple[int, str], dict]:
    path = os.path.join(ROOT, "data", "teams", "canonical_teams.csv")
    m: Dict[Tuple[int, str], dict] = {}
    rows = read_csv(path)
    for r in rows:
        try:
            y = int((r.get("season_year") or "").strip())
        except Exception:
            continue
        code = (r.get("team_code") or "").strip()
        if not y or not code:
            continue
        m[(y, code)] = {
            "team_full_name": (r.get("team_full_name") or "").strip(),
            "is_co_owned": (r.get("is_co_owned") or "").strip(),
            # Support new owner columns with fallback to legacy names if found
            "owner_code_1": (r.get("owner_code_1") or r.get("owner_code") or "").strip(),
            "owner_code_2": (r.get("owner_code_2") or r.get("co_owner_code") or "").strip(),
        }
    return m


def compute_season_numbers(canon_rows: List[dict]) -> Dict[int, int]:
    years = sorted({int(r["season_year"]) for r in canon_rows if (r.get("season_year") or "").isdigit()})
    return {y: i + 1 for i, y in enumerate(years)}


def count_teams_by_year(canon_rows: List[dict]) -> Dict[int, int]:
    from collections import defaultdict
    s = defaultdict(set)
    for r in canon_rows:
        y = r.get("season_year")
        c = r.get("team_code")
        if (y or "").isdigit() and c:
            s[int(y)].add(c)
    return {y: len(codes) for y, codes in s.items()}


def build_draft_order(year: int) -> Dict[str, int]:
    """Return team_code -> draft_order for a year using round 1 from draft.csv.

    Uses the normalized reports if present; else reads raw and uses team_abbrev (best effort).
    """
    # Prefer normalized to leverage alias mapping and canonical codes
    norm_path = os.path.join(ROOT, "data", "seasons", str(year), "reports", "draft_normalized.csv")
    raw_path = os.path.join(ROOT, "data", "seasons", str(year), "draft.csv")
    order: Dict[str, int] = {}
    if os.path.exists(norm_path):
        rows = read_csv(norm_path)
        for r in rows:
            if (r.get("year") or "") != str(year):
                continue
            if (r.get("round") or "") != "1":
                continue
            code = (r.get("team_code") or "").strip()
            try:
                rp = int((r.get("round_pick") or ""))
            except Exception:
                continue
            if code and rp:
                order[code] = rp
        return order
    # Fallback to raw
    if os.path.exists(raw_path):
        rows = read_csv(raw_path)
        for r in rows:
            if (r.get("year") or "") != str(year):
                continue
            if (r.get("round") or "") != "1":
                continue
            ab = (r.get("team_abbrev") or "").strip()
            try:
                rp = int((r.get("round_pick") or ""))
            except Exception:
                continue
            if ab and rp:
                order[ab] = rp  # Note: abbrev, not canonical
    return order


def fill_master(in_path: str, out_path: str) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canon_rows = read_csv(os.path.join(ROOT, "data", "teams", "canonical_teams.csv"))
    canon_index = read_canonicals()
    season_numbers = compute_season_numbers(canon_rows)
    team_counts = count_teams_by_year(canon_rows)

    # Build draft orders cache for seasons where draft data exists
    draft_orders: Dict[int, Dict[str, int]] = {}

    filled_counts = {"team_full_name": 0, "is_co_owned": 0, "owner_code_1": 0, "owner_code_2": 0, "teams_count": 0, "season_number": 0, "draft_order": 0}
    total_rows = 0

    with open(in_path, newline="", encoding="utf-8") as f_in, open(out_path, "w", newline="", encoding="utf-8") as f_out:
        r = csv.DictReader(f_in)
        fieldnames = r.fieldnames or []
        # Ensure new canonical owner columns exist in output
        if "owner_code_1" not in fieldnames:
            fieldnames.append("owner_code_1")
        if "owner_code_2" not in fieldnames:
            fieldnames.append("owner_code_2")
        # Legacy co-owner column (if exists) preserved but not required
        legacy_owner2_col = None
        for name in r.fieldnames or []:
            if name.lower().strip().startswith("owner_code") and "co-owner" in name.lower():
                legacy_owner2_col = name
                break
        if not legacy_owner2_col and "owner_code (CO-OWNER)" in (r.fieldnames or []):
            legacy_owner2_col = "owner_code (CO-OWNER)"
        w = csv.DictWriter(f_out, fieldnames=fieldnames)
        w.writeheader()
        for row in r:
            total_rows += 1
            # Basic keys
            try:
                year = int((row.get("season_year") or "").strip())
            except Exception:
                w.writerow(row)
                continue
            code = (row.get("team_code") or "").strip()

            # Canonical join
            info = canon_index.get((year, code), {})
            if not (row.get("team_full_name") or "").strip() and info.get("team_full_name"):
                row["team_full_name"] = info["team_full_name"]
                filled_counts["team_full_name"] += 1
            if not (row.get("is_co_owned") or "").strip() and info.get("is_co_owned"):
                row["is_co_owned"] = info["is_co_owned"]
                filled_counts["is_co_owned"] += 1
            # New canonical owner columns
            oc1_blank = (str(row.get("owner_code_1") or "").strip() == "")
            oc2_blank = (str(row.get("owner_code_2") or "").strip() == "")
            if oc1_blank and (info.get("owner_code_1") or ""):
                row["owner_code_1"] = info["owner_code_1"]
                filled_counts["owner_code_1"] += 1
            if oc2_blank and (info.get("owner_code_2") or ""):
                row["owner_code_2"] = info["owner_code_2"]
                filled_counts["owner_code_2"] += 1
            # Also backfill legacy columns if present but blank
            if not (row.get("owner_code") or "").strip():
                if info.get("owner_code_1"):
                    row["owner_code"] = info["owner_code_1"]
            if legacy_owner2_col and not (row.get(legacy_owner2_col) or "").strip():
                if info.get("owner_code_2"):
                    row[legacy_owner2_col] = info["owner_code_2"]

            # teams_count
            if not (row.get("teams_count") or "").strip():
                tc = team_counts.get(year)
                if tc is not None:
                    row["teams_count"] = str(tc)
                    filled_counts["teams_count"] += 1

            # season_number
            if not (row.get("season_number") or "").strip():
                sn = season_numbers.get(year)
                if sn is not None:
                    row["season_number"] = str(sn)
                    filled_counts["season_number"] += 1

            # draft_order (11+ only where draft.csv exists)
            if not (row.get("draft_order") or "").strip() and year >= 2011:
                if year not in draft_orders:
                    draft_orders[year] = build_draft_order(year)
                order_map = draft_orders.get(year, {})
                draft_pos = order_map.get(code)
                if draft_pos:
                    row["draft_order"] = str(draft_pos)
                    filled_counts["draft_order"] += 1

            w.writerow(row)

    return {"rows": total_rows, **filled_counts}


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill master DB CSV with canonical team metadata and draft order")
    ap.add_argument("--in", dest="in_path", required=True, help="Input master CSV path")
    ap.add_argument("--out", dest="out_path", required=True, help="Output CSV path")
    args = ap.parse_args()

    stats = fill_master(args.in_path, args.out_path)
    print("Filled:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
