#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, List, Tuple, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Reuse helpers from apply_alias_mapping
from apply_alias_mapping import load_aliases, build_alias_index, resolve_canonical, load_canonical_map  # type: ignore
from espn_api.football import League  # type: ignore


def read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str, rows: List[dict], fieldnames: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def count_teams_for_year(canon_meta: Dict[Tuple[int, str], Dict[str, str]], year: int) -> int:
    return len({code for (y, code) in canon_meta.keys() if y == year})


def _load_env() -> Tuple[int, Optional[str], Optional[str]]:
    """Load LEAGUE/ESPN_S2/SWID from .env if not present."""
    if not os.getenv("LEAGUE") and os.path.exists(os.path.join(ROOT, ".env")):
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k.strip(), v)
    league_id = int(os.getenv("LEAGUE")) if os.getenv("LEAGUE") else None
    return league_id, os.getenv("ESPN_S2"), os.getenv("SWID")


def _player_meta_for_ids(year: int, ids: List[int]) -> Dict[int, Tuple[str, str]]:
    """Return {player_id: (NFL_team_abbrev, position)} using ESPN API."""
    league_id, s2, swid = _load_env()
    meta: Dict[int, Tuple[str, str]] = {}
    if not league_id:
        return meta
    try:
        lg = League(league_id=league_id, year=year, espn_s2=s2, swid=swid)
        # League.player_info accepts a list of ids and returns Player or list
        players = lg.player_info(playerId=ids)
        if not players:
            return meta
        if not isinstance(players, list):
            players = [players]
        for pl in players:
            pid = getattr(pl, "playerId", None)
            team = getattr(pl, "proTeam", "") or ""
            pos = getattr(pl, "position", "") or ""
            if pid:
                meta[int(pid)] = (str(team), str(pos))
    except Exception:
        # Leave meta empty on failure; caller will leave blanks
        pass
    return meta


def make_snake(year: int, mapping_path: str, out_path: str, max_rounds: Optional[int] = None) -> Tuple[int, str]:
    draft_path = os.path.join(ROOT, "data", "seasons", str(year), "draft.csv")
    if not os.path.exists(draft_path):
        raise FileNotFoundError(f"Missing draft.csv for {year}: {draft_path}")

    rows = read_csv(draft_path)
    aliases = load_aliases(mapping_path)
    idx = build_alias_index(aliases)
    canon_meta = load_canonical_map()
    team_count = count_teams_for_year(canon_meta, year)
    if team_count == 0:
        # Fallback: infer from max round_pick
        try:
            team_count = max(int(r.get("round_pick") or 0) for r in rows if (r.get("year") or "") == str(year))
        except Exception:
            team_count = 12

    out_rows: List[dict] = []
    # Collect all player ids to enrich with team/position
    want_ids: List[int] = []
    for r in rows:
        if (r.get("year") or "") != str(year):
            continue
        try:
            rnd = int(r.get("round") or 0)
            rnd_pick = int(r.get("round_pick") or 0)
        except Exception:
            continue
        if rnd == 0 or rnd_pick == 0:
            continue
        if max_rounds and rnd > max_rounds:
            continue

        src_abbrev = (r.get("team_abbrev") or "").strip()
        code = resolve_canonical(src_abbrev, year, idx)
        meta = canon_meta.get((year, code), {})
        overall_pick = (rnd - 1) * team_count + rnd_pick
        pid = r.get("player_id")
        try:
            pid_int = int(pid) if pid not in (None, "") else None
        except Exception:
            pid_int = None
        if pid_int is not None:
            want_ids.append(pid_int)

    # Fetch player meta (team/position) in batch
    player_meta = _player_meta_for_ids(year, sorted(list(set(want_ids))))

    for r in rows:
        if (r.get("year") or "") != str(year):
            continue
        try:
            rnd = int(r.get("round") or 0)
            rnd_pick = int(r.get("round_pick") or 0)
        except Exception:
            continue
        if rnd == 0 or rnd_pick == 0:
            continue
        if max_rounds and rnd > max_rounds:
            continue

        src_abbrev = (r.get("team_abbrev") or "").strip()
        code = resolve_canonical(src_abbrev, year, idx)
        meta = canon_meta.get((year, code), {})
        overall_pick = (rnd - 1) * team_count + rnd_pick
        pid = r.get("player_id")
        try:
            pid_int = int(pid) if pid not in (None, "") else None
        except Exception:
            pid_int = None
        nfl_team, pos = ("", "")
        if pid_int is not None and pid_int in player_meta:
            nfl_team, pos = player_meta[pid_int]
        # keeper column in source may be boolean/string; normalize Yes/No
        keep_val = (r.get("keeper") or "").strip()
        keep_str = "Yes" if str(keep_val).lower() in ("true", "1", "yes") else "No"

        out_rows.append({
            "year": str(year),
            "round": str(rnd),
            "round_pick": str(rnd_pick),
            "overall_pick": str(overall_pick),
            "team_code": code,
            "team_full_name": meta.get("team_full_name", ""),
            "is_co_owned": meta.get("is_co_owned", ""),
            "owner_code_1": meta.get("owner_code_1", ""),
            "owner_code_2": meta.get("owner_code_2", ""),
            "player_id": r.get("player_id", ""),
            "player_name": r.get("player_name", ""),
            "player_NFL_team": nfl_team,
            "player_position": pos,
            "is_a_keeper?": keep_str,
        })

    fieldnames = [
        "year",
        "round",
        "round_pick",
        "overall_pick",
        "team_code",
        "team_full_name",
        "is_co_owned",
        "owner_code_1",
        "owner_code_2",
        "player_id",
        "player_name",
        "player_NFL_team",
        "player_position",
        "is_a_keeper?",
    ]
    write_csv(out_path, out_rows, fieldnames)
    return len(out_rows), out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Create snake-draft canonical CSVs (no auction fields)")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mapping", default=os.path.join(ROOT, "data", "teams", "alias_mapping.yaml"))
    ap.add_argument("--max-rounds", type=int, default=None, help="Limit rounds (default: all)")
    args = ap.parse_args()

    n, path = make_snake(args.year, args.mapping, args.out, args.max_rounds)
    print(f"Wrote {n} picks -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
