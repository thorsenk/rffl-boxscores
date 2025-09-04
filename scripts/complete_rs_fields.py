#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from typing import Dict, Tuple, List

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


def season_rs_from_h2h(year: int) -> Dict[str, Dict[str, float]]:
    path = os.path.join(
        ROOT, "data", "seasons", str(year), "reports", "h2h_normalized.csv"
    )
    stats: Dict[str, Dict[str, float]] = {}
    if not os.path.exists(path):
        return stats
    for r in read_csv(path):
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
            s = stats.setdefault(code, {"pf": 0.0, "pa": 0.0})
            s["pf"] += pf
            s["pa"] += pa
    return stats


def season_rs_from_boxscores(year: int) -> Dict[str, Dict[str, float]]:
    path = os.path.join(
        ROOT, "data", "seasons", str(year), "reports", "boxscores_normalized.csv"
    )
    stats: Dict[str, Dict[str, float]] = {}
    if not os.path.exists(path):
        return stats
    rows = read_csv(path)
    from collections import defaultdict

    tw: Dict[Tuple[int, int, str], Tuple[float, float]] = {}
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
            act = float(r.get("team_actual_total") or 0.0)
            proj = float(r.get("team_proj_total") or 0.0)
        except Exception:
            continue
        key = (wk, mu, code)
        if key not in tw:
            tw[key] = (act, proj)
    pairs: Dict[Tuple[int, int], List[Tuple[str, float, float]]] = defaultdict(list)
    for (wk, mu, code), (act, proj) in tw.items():
        pairs[(wk, mu)].append((code, act, proj))
    for (wk, mu), lst in pairs.items():
        if len(lst) != 2:
            continue
        (c1, a1, p1), (c2, a2, p2) = lst
        s1 = stats.setdefault(
            c1, {"pf": 0.0, "pa": 0.0, "proj_pf": 0.0, "proj_pa": 0.0}
        )
        s2 = stats.setdefault(
            c2, {"pf": 0.0, "pa": 0.0, "proj_pf": 0.0, "proj_pa": 0.0}
        )
        s1["pf"] += a1
        s1["pa"] += a2
        s1["proj_pf"] += p1
        s1["proj_pa"] += p2
        s2["pf"] += a2
        s2["pa"] += a1
        s2["proj_pf"] += p2
        s2["proj_pa"] += p1
    return stats


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def main() -> int:
    master = os.path.join(ROOT, "build", "outputs", "RFFL_MASTER_DB.csv")
    rows = read_csv(master)
    # Build season maps
    years = sorted(
        set(
            int(r["season_year"])
            for r in rows
            if (r.get("season_year") or "").isdigit()
        )
    )
    rs_maps: Dict[int, Dict[str, Dict[str, float]]] = {}
    for y in years:
        m = season_rs_from_h2h(y)
        if not m:
            m = season_rs_from_boxscores(y)
        rs_maps[y] = m

    # Ensure new columns exist and prepare output
    fieldnames = rows[0].keys()
    out_fields = list(fieldnames)
    # add explicit actual aliases if absent
    if "rs_actual_pf" not in out_fields:
        out_fields.append("rs_actual_pf")
    if "rs_actual_pa" not in out_fields:
        out_fields.append("rs_actual_pa")

    completed: List[dict] = []
    for r in rows:
        try:
            y = int((r.get("season_year") or "").strip())
        except Exception:
            completed.append(r)
            continue
        code = (r.get("team_code") or "").strip()
        m = rs_maps.get(y, {})
        s = m.get(code)
        # derive values
        if s:
            pf = fmt(s.get("pf", 0.0))
            pa = fmt(s.get("pa", 0.0))
            proj_pf = fmt(s.get("proj_pf", 0.0)) if "proj_pf" in s else ""
            proj_pa = fmt(s.get("proj_pa", 0.0)) if "proj_pa" in s else ""

            # Overwrite if blank or placeholder
            def empty_or_placeholder(val: str) -> bool:
                return (val or "").strip() in ("", "MISSING_TASK_ESPN-MCP")

            # actuals
            if empty_or_placeholder(r.get("rs_pf", "")):
                r["rs_pf"] = pf
            if empty_or_placeholder(r.get("rs_pa", "")):
                r["rs_pa"] = pa
            # projections (only if available, i.e., 2019+ boxscores)
            if proj_pf and empty_or_placeholder(r.get("rs_proj_pf", "")):
                r["rs_proj_pf"] = proj_pf
            if proj_pa and empty_or_placeholder(r.get("rs_proj_pa", "")):
                r["rs_proj_pa"] = proj_pa
            # mirror into explicit actual columns
            r["rs_actual_pf"] = r.get("rs_pf", pf)
            r["rs_actual_pa"] = r.get("rs_pa", pa)
        completed.append(r)

    out_path = os.path.join(ROOT, "build", "outputs", "RFFL_MASTER_DB_completed.csv")
    write_csv(out_path, completed, out_fields)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
