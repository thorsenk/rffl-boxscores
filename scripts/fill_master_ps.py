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


def load_playoff_pairs_from_h2h(
    year: int,
) -> Dict[Tuple[int, str], Tuple[str, float, float, str]]:
    """Return mapping (week, team_code) -> (opp_code, pf, pa, result) for weeks >=15.

    Source: data/seasons/<year>/reports/h2h_normalized.csv.
    """
    path = os.path.join(
        ROOT, "data", "seasons", str(year), "reports", "h2h_normalized.csv"
    )
    out: Dict[Tuple[int, str], Tuple[str, float, float, str]] = {}
    if not os.path.exists(path):
        return out
    for r in read_csv(path):
        try:
            wk = int(r.get("week") or 0)
        except Exception:
            continue
        if wk < 15:
            continue
        hc = (r.get("home_code") or "").strip()
        ac = (r.get("away_code") or "").strip()
        if not hc or not ac:
            continue
        try:
            hs = float(r.get("home_score") or 0.0)
            as_ = float(r.get("away_score") or 0.0)
        except Exception:
            continue
        # home
        if hs > as_:
            hr = "W"
            ar = "L"
        elif as_ > hs:
            hr = "L"
            ar = "W"
        else:
            hr = ar = "T"
        out[(wk, hc)] = (ac, hs, as_, hr)
        out[(wk, ac)] = (hc, as_, hs, ar)
    return out


def load_playoff_pairs_from_box(
    year: int,
) -> Dict[Tuple[int, str], Tuple[str, float, float, str, float, float]]:
    """Infer playoff pairs from boxscores_normalized for weeks >=15.

    Pair teams by (week, matchup).
    """
    path = os.path.join(
        ROOT, "data", "seasons", str(year), "reports", "boxscores_normalized.csv"
    )
    out: Dict[Tuple[int, str], Tuple[str, float, float, str, float, float]] = {}
    if not os.path.exists(path):
        return out
    rows = read_csv(path)
    # team-week totals
    tw: Dict[Tuple[int, int, str], Tuple[float, float]] = {}
    for r in rows:
        try:
            wk = int(r.get("week") or 0)
            mu = int(r.get("matchup") or 0)
        except Exception:
            continue
        if wk < 15:
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
        if key not in tw:
            tw[key] = (sc, pr)
    from collections import defaultdict

    pairs: Dict[Tuple[int, int], List[Tuple[str, float]]] = defaultdict(list)
    for (wk, mu, code), (sc, pr) in tw.items():
        pairs[(wk, mu)].append((code, sc, pr))
    for (wk, mu), lst in pairs.items():
        if len(lst) != 2:
            continue
        (c1, s1, p1), (c2, s2, p2) = lst
        if s1 > s2:
            r1, r2 = "W", "L"
        elif s2 > s1:
            r1, r2 = "L", "W"
        else:
            r1 = r2 = "T"
        out[(wk, c1)] = (c2, s1, s2, r1, p1, p2)
        out[(wk, c2)] = (c1, s2, s1, r2, p2, p1)
    return out


def build_playoff_index(
    years: List[int],
) -> Dict[int, Dict[int, Dict[str, Tuple[str, float, float, str]]]]:
    idx: Dict[
        int, Dict[int, Dict[str, Tuple[str, float, float, str, float, float]]]
    ] = {}
    for y in years:
        pairs = load_playoff_pairs_from_h2h(y)
        if not pairs:
            pairs = load_playoff_pairs_from_box(y)
        per_week: Dict[int, Dict[str, Tuple[str, float, float, str, float, float]]] = {}
        for (wk, code), tup in pairs.items():
            per_week.setdefault(wk, {})[code] = tup
        idx[y] = per_week
    return idx


def fill_master_ps(in_path: str, out_path: str) -> Dict[str, int]:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    years = sorted(
        [
            int(name)
            for name in os.listdir(os.path.join(ROOT, "data", "seasons"))
            if name.isdigit()
        ]
    )
    pidx = build_playoff_index(years)
    counts = {
        k: 0
        for k in [
            "ps_gp",
            "ps_wins",
            "ps_losses",
            "ps_actual_pf",
            "ps_actual_pa",
            "ps_proj_pf",
            "ps_proj_pa",
            "qf_pf",
            "qf_pa",
            "qf_results",
            "qf_opponent_code",
            "sf_pf",
            "sf_pa",
            "sf_results",
            "sf_opponent_code",
            "f_week",
            "f_pf",
            "f_pa",
            "f_result",
            "f_opponent_code",
        ]
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
            per_week = pidx.get(y, {})
            # collect weeks 15,16,17 data
            weeks = [wk for wk in (15, 16, 17) if code in per_week.get(wk, {})]
            # ps summary
            if (row.get("ps_gp") or "").strip() == "":
                row["ps_gp"] = str(len(weeks))
                counts["ps_gp"] += 1
            # wins/losses + pf/pa sums
            if any(
                (row.get(k) or "").strip() == ""
                for k in (
                    "ps_wins",
                    "ps_losses",
                    "ps_actual_pf",
                    "ps_actual_pa",
                    "ps_proj_pf",
                    "ps_proj_pa",
                )
            ):
                wcnt = lcnt = 0
                pf_sum = pa_sum = 0.0
                ppf_sum = ppa_sum = 0.0
                for wk in weeks:
                    tup = per_week[wk][code]
                    opp, pf, pa, res = tup[0], tup[1], tup[2], tup[3]
                    proj_pf = tup[4] if len(tup) > 4 else None
                    proj_pa = tup[5] if len(tup) > 5 else None
                    pf_sum += pf
                    pa_sum += pa
                    if proj_pf is not None and proj_pa is not None:
                        ppf_sum += proj_pf
                        ppa_sum += proj_pa
                    if res == "W":
                        wcnt += 1
                    elif res == "L":
                        lcnt += 1
                if (row.get("ps_wins") or "").strip() == "":
                    row["ps_wins"] = str(wcnt)
                    counts["ps_wins"] += 1
                if (row.get("ps_losses") or "").strip() == "":
                    row["ps_losses"] = str(lcnt)
                    counts["ps_losses"] += 1
                if (row.get("ps_actual_pf") or "").strip() == "":
                    row["ps_actual_pf"] = f"{pf_sum:.2f}".rstrip("0").rstrip(".")
                    counts["ps_actual_pf"] += 1
                if (row.get("ps_actual_pa") or "").strip() == "":
                    row["ps_actual_pa"] = f"{pa_sum:.2f}".rstrip("0").rstrip(".")
                    counts["ps_actual_pa"] += 1
                # projections (boxscores only)
                if ppf_sum > 0 and (row.get("ps_proj_pf") or "").strip() == "":
                    row["ps_proj_pf"] = f"{ppf_sum:.2f}".rstrip("0").rstrip(".")
                    counts["ps_proj_pf"] += 1
                if ppa_sum > 0 and (row.get("ps_proj_pa") or "").strip() == "":
                    row["ps_proj_pa"] = f"{ppa_sum:.2f}".rstrip("0").rstrip(".")
                    counts["ps_proj_pa"] += 1
            # QF (week 15)
            if 15 in per_week:
                if (row.get("qf_pf") or "").strip() == "":
                    if code in per_week[15]:
                        tup = per_week[15][code]
                        opp, pf, pa, res = tup[0], tup[1], tup[2], tup[3]
                        row["qf_pf"] = f"{pf:.2f}".rstrip("0").rstrip(".")
                        row["qf_pa"] = f"{pa:.2f}".rstrip("0").rstrip(".")
                        row["qf_results"] = res
                        row["qf_opponent_code"] = opp
                    else:
                        row["qf_pf"] = row["qf_pa"] = row["qf_results"] = "Bye"
                        row["qf_opponent_code"] = ""
                    counts["qf_pf"] += 1
                    counts["qf_pa"] += 1
                    counts["qf_results"] += 1
                    counts["qf_opponent_code"] += 1
            # SF (week 16)
            if 16 in per_week and (row.get("sf_pf") or "").strip() == "":
                if code in per_week[16]:
                    tup = per_week[16][code]
                    opp, pf, pa, res = tup[0], tup[1], tup[2], tup[3]
                    row["sf_pf"] = f"{pf:.2f}".rstrip("0").rstrip(".")
                    row["sf_pa"] = f"{pa:.2f}".rstrip("0").rstrip(".")
                    row["sf_results"] = res
                    row["sf_opponent_code"] = opp
                    counts["sf_pf"] += 1
                    counts["sf_pa"] += 1
                    counts["sf_results"] += 1
                    counts["sf_opponent_code"] += 1
            # Final (week 17)
            if 17 in per_week and (row.get("f_pf") or "").strip() == "":
                if code in per_week[17]:
                    tup = per_week[17][code]
                    opp, pf, pa, res = tup[0], tup[1], tup[2], tup[3]
                    row["f_week"] = (
                        "17"
                        if (row.get("f_week") or "").strip() == ""
                        else row["f_week"]
                    )
                    row["f_pf"] = f"{pf:.2f}".rstrip("0").rstrip(".")
                    row["f_pa"] = f"{pa:.2f}".rstrip("0").rstrip(".")
                    row["f_result"] = res
                    row["f_opponent_code"] = opp
                    counts["f_week"] += 1
                    counts["f_pf"] += 1
                    counts["f_pa"] += 1
                    counts["f_result"] += 1
                    counts["f_opponent_code"] += 1
            w.writerow(row)
    counts["rows"] = total
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fill Postseason fields from normalized h2h/boxscores"
    )
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    args = ap.parse_args()
    stats = fill_master_ps(args.in_path, args.out_path)
    print("Filled Postseason:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
