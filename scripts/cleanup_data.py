#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def list_season_dirs(base: str) -> List[str]:
    out = []
    for name in os.listdir(base):
        if name.isdigit():
            out.append(os.path.join(base, name))
    return sorted(out)


def should_keep(path: str, year: int) -> bool:
    # Always keep directories
    if os.path.isdir(path):
        return True
    name = os.path.basename(path)
    # Raw season inputs we keep
    if name in {"draft.csv", "h2h.csv", "boxscores.csv"}:
        # boxscores.csv exists only for 2019+
        if name == "boxscores.csv" and year < 2019:
            return False
        return True
    # Reports that are current (sources of truth)
    if name.endswith("-Draft-Snake-Canonicals.csv"):
        return True
    if name == "boxscores_normalized.csv":
        return year >= 2019
    if name == "teamweek_unified.csv":
        return year >= 2019
    if name == "h2h_teamweek.csv":
        return year < 2019
    # Explicitly drop legacy/intermediate/derived reports
    if name in {
        "boxscores_lineup_validation_report.csv",
        "h2h_normalized.csv",
        "alias_coverage.csv",
        "draft_normalized.csv",
        "keepers.csv",
        "keepers_summary.csv",
    }:
        return False
    # Everything else is deletable by default
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Identify and clean obsolete data files")
    ap.add_argument(
        "--apply", action="store_true", help="Perform deletion (otherwise dry-run)"
    )
    args = ap.parse_args()

    base = os.path.join(ROOT, "data", "seasons")
    to_delete: List[str] = []
    to_keep: List[str] = []

    for sdir in list_season_dirs(base):
        year = int(os.path.basename(sdir))
        # Walk season dir
        for root, dirs, files in os.walk(sdir):
            for fn in files:
                p = os.path.join(root, fn)
                if should_keep(p, year):
                    to_keep.append(p)
                else:
                    to_delete.append(p)

    # Root-level validated_* artifacts are safe to delete
    for fn in os.listdir(ROOT):
        if (
            fn.startswith("validated_boxscores_")
            or fn.startswith("validated_CLI_Boxscores_")
        ) and fn.endswith(".csv"):
            to_delete.append(os.path.join(ROOT, fn))

    # Deduplicate lists
    to_keep = sorted(set(to_keep))
    to_delete = sorted(set(to_delete))

    # Write plan
    plan_dir = os.path.join(ROOT, "build", "audit")
    os.makedirs(plan_dir, exist_ok=True)
    plan_path = os.path.join(plan_dir, "cleanup_plan.txt")
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write("KEEP ({} files)\n".format(len(to_keep)))
        for p in to_keep:
            f.write("KEEP: {}\n".format(os.path.relpath(p, ROOT)))
        f.write("\nDELETE ({} files)\n".format(len(to_delete)))
        for p in to_delete:
            f.write("DELETE: {}\n".format(os.path.relpath(p, ROOT)))

    if not args.apply:
        print("Dry-run complete. Plan at:", os.path.relpath(plan_path, ROOT))
        print("KEEP:", len(to_keep), "DELETE:", len(to_delete))
        return 0

    # Apply: move to build/trash/<timestamp>/ then delete
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_dir = os.path.join(ROOT, "build", "trash", stamp)
    os.makedirs(trash_dir, exist_ok=True)
    for p in to_delete:
        rel = os.path.relpath(p, ROOT)
        dst = os.path.join(trash_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.move(p, dst)
        except Exception:
            # Best-effort
            pass
    print("Moved", len(to_delete), "files to", os.path.relpath(trash_dir, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
