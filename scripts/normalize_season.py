#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def normalize_file(year: int, rel_path: str, mapping: str) -> None:
    in_path = os.path.join(ROOT, rel_path)
    if not os.path.exists(in_path):
        return
    ydir = os.path.dirname(in_path)
    out_dir = os.path.join(ydir, "reports")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.basename(in_path)
    name = os.path.splitext(base)[0]
    out_path = os.path.join(out_dir, f"{name}_normalized.csv")
    cmd = [
        "python3",
        os.path.join(ROOT, "scripts", "apply_alias_mapping.py"),
        "--file",
        in_path,
        "--year",
        str(year),
        "--out",
        out_path,
        "--mapping",
        mapping,
    ]
    subprocess.run(cmd, check=True)
    print(f"✓ {rel_path} -> {os.path.relpath(out_path, ROOT)}")


def audit_year(year: int) -> None:
    cmd = ["python3", os.path.join(ROOT, "scripts", "audit_alias_coverage.py"), str(year)]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize all season CSVs for a given year")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument(
        "--mapping",
        default=os.path.join(ROOT, "data", "teams", "alias_mapping.yaml"),
        help="Alias mapping YAML path",
    )
    args = ap.parse_args()

    year = args.year
    base = os.path.join("data", "seasons", str(year))
    normalize_file(year, os.path.join(base, "draft.csv"), args.mapping)
    normalize_file(year, os.path.join(base, "boxscores.csv"), args.mapping)
    normalize_file(year, os.path.join(base, "h2h.csv"), args.mapping)
    audit_year(year)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

