#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import shutil
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _season_dirs(base: str) -> List[str]:
    return sorted([d for d in os.listdir(base) if d.isdigit()])


def _add_if_exists(files: List[Tuple[str, str, str, str]], year: str, src: str, flat_name: str, kind: str) -> None:
    if os.path.exists(src):
        files.append((year, kind, src, flat_name))


def build_flat_index(out_dir: str) -> Tuple[int, str]:
    seasons_dir = os.path.join(ROOT, "data", "seasons")
    years = _season_dirs(seasons_dir)
    # Clean output directory to ensure it's a source-of-truth snapshot
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Collect all source files with desired flat names
    items: List[Tuple[str, str, str, str]] = []  # (year, kind, src_path, flat_name)
    for y in years:
        ydir = os.path.join(seasons_dir, y)
        rdir = os.path.join(ydir, "reports")
        # Raw inputs intentionally excluded from flat index (keep this a source-of-truth for finalized reports)

        # Reports – Draft (use Snake canonicals as the source of truth in flat)
        # Exclude Draft-Correct-Canonicals from flat to avoid duplication
        _add_if_exists(items, y, os.path.join(rdir, f"{y}-Draft-Snake-Canonicals.csv"), f"{y}_draft_snake_canonicals.csv", "draft_snake_canonicals")

        # Reports – Boxscores
        _add_if_exists(items, y, os.path.join(rdir, "boxscores_normalized.csv"), f"{y}_boxscores_normalized.csv", "boxscores_normalized")
        _add_if_exists(items, y, os.path.join(rdir, "boxscores_lineup_validation_report.csv"), f"{y}_boxscores_lineup_validation_report.csv", "boxscores_lineup_report")

        # Reports – Team-week
        _add_if_exists(items, y, os.path.join(rdir, "h2h_teamweek.csv"), f"{y}_h2h_teamweek.csv", "teamweek_legacy")
        _add_if_exists(items, y, os.path.join(rdir, "teamweek_unified.csv"), f"{y}_teamweek_unified.csv", "teamweek_unified")

    # Write catalog and copy files
    catalog_path = os.path.join(out_dir, "catalog.csv")
    with open(catalog_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["year", "kind", "source_path", "flat_name", "flat_path"],
        )
        w.writeheader()
        for year, kind, src, flat_name in items:
            dst = os.path.join(out_dir, flat_name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            w.writerow(
                {
                    "year": year,
                    "kind": kind,
                    "source_path": os.path.relpath(src, ROOT),
                    "flat_name": flat_name,
                    "flat_path": os.path.relpath(dst, ROOT),
                }
            )

    return len(items), catalog_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a flat index of season files with year-prefixed names")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "flat"))
    args = ap.parse_args()

    n, path = build_flat_index(args.out)
    print(f"Wrote {n} files into {os.path.relpath(args.out, ROOT)}")
    print(f"Catalog: {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
