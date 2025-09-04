#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from typing import List


def read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str, rows: List[dict], fieldnames: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Drop legacy owner columns and standardize " "owner_code_1/owner_code_2"
        )
    )
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    args = ap.parse_args()

    rows = read_csv(args.in_path)
    if not rows:
        raise SystemExit("No rows found")

    legacy_cols = {"owner_code", "owner_code (CO-OWNER)"}

    # Build new schema: keep all columns except legacy owner ones, and
    # ensure owner_code_1/2 exist after is_co_owned
    orig_fields = list(rows[0].keys())
    fields = [c for c in orig_fields if c not in legacy_cols]

    # ensure owner_code_1/2 present; if not, add
    if "owner_code_1" not in fields:
        fields.append("owner_code_1")
    if "owner_code_2" not in fields:
        fields.append("owner_code_2")

    # Reorder: place owner_code_1/2 immediately after is_co_owned if present
    if "is_co_owned" in fields:
        # remove
        fields = [c for c in fields if c not in ("owner_code_1", "owner_code_2")]
        idx = fields.index("is_co_owned") + 1
        fields[idx:idx] = ["owner_code_1", "owner_code_2"]

    # Clean rows: drop legacy cols; ensure owner_code_1/2 set if legacy had values
    cleaned: List[dict] = []
    for r in rows:
        r = dict(r)
        oc1 = (r.get("owner_code_1") or r.get("owner_code") or "").strip()
        oc2 = (r.get("owner_code_2") or r.get("owner_code (CO-OWNER)") or "").strip()
        r["owner_code_1"] = oc1
        r["owner_code_2"] = oc2
        for lc in legacy_cols:
            r.pop(lc, None)
        cleaned.append(r)

    write_csv(args.out_path, cleaned, fields)
    print(
        f"Wrote clean master: {args.out_path} (cols={len(fields)}, rows={len(cleaned)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
