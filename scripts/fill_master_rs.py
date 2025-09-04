#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, Tuple, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def season_rs_from_h2h(year: int) -> Dict[str, Dict[str, float]]:
    path = os.path.join(
        ROOT, "data", "seasons", str(year), "reports", "h2h_normalized.csv"
    )
    stats: Dict[str, Dict[str, float]] = {}
    if not os.path.exists(path):
        return stats
    rows = read_csv(path)
    for r in rows:
        try:
            wk = int(r.get("week") or 0)
        except Exception:
            continue
        if wk < 1 or wk > 14:
            continue
        hc = (r.get("home_code") or "").strip()
        ac = (r.get("away_code") or "").strip()
        try:
            hs = float(r.get("home_score") or 0.0)
            as_ = float(r.get("away_score") or 0.0)
        except Exception:
            continue
        for code, pf, pa in ((hc, hs, as_), (ac, as_, hs)):
            if not code:
                continue
            s = stats.setdefault(
                code, {"gp": 0, "w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0}
            )
            s["gp"] += 1
            s["pf"] += pf
            s["pa"] += pa
        # results
        if hs > as_:
            stats[hc]["w"] += 1
            stats[ac]["l"] += 1
        elif as_ > hs:
            stats[ac]["w"] += 1
            stats[hc]["l"] += 1
        else:
            stats[ac]["t"] += 1
            stats[hc]["t"] += 1
    return stats


def season_rs_from_boxscores(year: int) -> Dict[str, Dict[str, float]]:
    path = os.path.join(
        ROOT, "data", "seasons", str(year), "reports", "boxscores_normalized.csv"
    )
    stats: Dict[str, Dict[str, float]] = {}
    if not os.path.exists(path):
        return stats
    rows = read_csv(path)
    # aggregate to team-week totals from per-player rows

    tw_scores: Dict[Tuple[int, int, str], Tuple[float, float]] = {}
    for r in rows:
        try:
            wk = int(r.get("week") or 0)
            mu = int(r.get("matchup") or 0)
        except Exception:
            continue
        if wk < 1 or wk > 14:
            continue
        code = (r.get("team_code") or "").strip()
        if not code:
            continue
        try:
            sc = float(r.get("team_actual_total") or 0.0)
            pr = float(r.get("team_proj_total") or 0.0)
        except Exception:
            continue
        key = (wk, mu, code)
        # Keep first seen; all rows for same team-week carry same team totals
        if key not in tw_scores:
            tw_scores[key] = (sc, pr)
    # pair by (week,matchup)
    from collections import defaultdict

    per_pair: Dict[Tuple[int, int], List[Tuple[str, float]]] = defaultdict(list)
    for (wk, mu, code), (sc, pr) in tw_scores.items():
        per_pair[(wk, mu)].append((code, sc, pr))
    for (wk, mu), lst in per_pair.items():
        if len(lst) != 2:
            continue
        (c1, s1, p1), (c2, s2, p2) = lst
        for code, pf, pa in ((c1, s1, s2), (c2, s2, s1)):
            s = stats.setdefault(
                code,
                {
                    "gp": 0,
                    "w": 0,
                    "l": 0,
                    "t": 0,
                    "pf": 0.0,
                    "pa": 0.0,
                    "proj_pf": 0.0,
                    "proj_pa": 0.0,
                },
            )
            s["gp"] += 1
            s["pf"] += pf
            s["pa"] += pa
        # projections
        stats[c1]["proj_pf"] += p1
        stats[c1]["proj_pa"] += p2
        stats[c2]["proj_pf"] += p2
        stats[c2]["proj_pa"] += p1
        if s1 > s2:
            stats[c1]["w"] += 1
            stats[c2]["l"] += 1
        elif s2 > s1:
            stats[c2]["w"] += 1
            stats[c1]["l"] += 1
        else:
            stats[c1]["t"] += 1
            stats[c2]["t"] += 1
    return stats


def fill_master_rs(in_path: str, out_path: str) -> Dict[str, int]:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Preload per-year stats maps
    years = sorted(
        [
            int(name)
            for name in os.listdir(os.path.join(ROOT, "data", "seasons"))
            if name.isdigit()
        ]
    )
    rs_maps: Dict[int, Dict[str, Dict[str, float]]] = {}
    for y in years:
        m = season_rs_from_h2h(y)
        if not m:
            m = season_rs_from_boxscores(y)
        rs_maps[y] = m
    counts = {
        "rs_gp": 0,
        "rs_wins": 0,
        "rs_losses": 0,
        "rs_ties": 0,
        "rs_pf": 0,
        "rs_pa": 0,
        "rs_proj_pf": 0,
        "rs_proj_pa": 0,
    }
    total = 0
    with (
        open(in_path, newline="", encoding="utf-8") as f_in,
        open(out_path, "w", newline="", encoding="utf-8") as f_out,
    ):
        r = csv.DictReader(f_in)
        fn = r.fieldnames or []
        w = csv.DictWriter(f_out, fieldnames=fn)
        w.writeheader()
        for row in r:
            total += 1
            try:
                y = int((row.get("season_year") or "").strip())
            except Exception:
                w.writerow(row)
                continue
            code = (row.get("team_code") or "").strip()
            m = rs_maps.get(y, {})
            s = m.get(code)
            if s:
                for col, key in (
                    ("rs_gp", "gp"),
                    ("rs_wins", "w"),
                    ("rs_losses", "l"),
                    ("rs_ties", "t"),
                    ("rs_pf", "pf"),
                    ("rs_pa", "pa"),
                ):
                    if (row.get(col) or "").strip() == "":
                        val = s[key]
                        # ints without .0; pf/pa keep one decimal if needed
                        if col in ("rs_pf", "rs_pa"):
                            row[col] = f"{val:.2f}".rstrip("0").rstrip(".")
                        else:
                            row[col] = str(int(val))
                        counts[col] += 1
                # projections (boxscores only)
                for col, key in ("rs_proj_pf", "proj_pf"), ("rs_proj_pa", "proj_pa"):
                    if (row.get(col) or "").strip() == "" and key in s:
                        val = s[key]
                        row[col] = f"{val:.2f}".rstrip("0").rstrip(".")
                        counts[col] += 1
            w.writerow(row)
    counts["rows"] = total
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fill RS stats (GP/W/L/T/PF/PA) into master DB from season files"
    )
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    args = ap.parse_args()
    stats = fill_master_rs(args.in_path, args.out_path)
    print("Filled RS stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
