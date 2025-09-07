# SPDX-License-Identifier: MIT
# rffl_boxscores/cli.py
from __future__ import annotations
import os
import math
import csv
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import pandas as pd
import typer
from espn_api.football import League
import yaml
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

app = typer.Typer(add_completion=False, help="RFFL clean exporter + validator")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STARTER_SLOTS = {"QB", "RB", "WR", "TE", "D/ST", "K", "FLEX", "RB/WR/TE"}
BENCH_SLOTS = {"Bench", "IR"}

# RFFL lineup requirements
RFFL_LINEUP_REQUIREMENTS = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "TE": 1,
    "FLEX": 1,
    "D/ST": 1,
    "K": 1,
}

# Valid positions for FLEX slot
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}


def _norm_slot(s: str | None, pos: str | None) -> str:
    s = (s or "").upper()
    p = (pos or "").upper()
    if s in ("RB/WR/TE", "FLEX"):
        return "FLEX"
    if s in ("DST", "D/ST", "DEFENSE"):
        return "D/ST"
    if s in ("BE", "BENCH"):
        return "Bench"
    if s in ("IR",):
        return "IR"
    if s in ("QB", "RB", "WR", "TE", "K"):
        return s
    if p in ("QB", "RB", "WR", "TE", "K"):
        return p
    if p in ("D/ST", "DST"):
        return "D/ST"
    return s or p or "Bench"


def _is_starter(slot: str) -> bool:
    return slot in STARTER_SLOTS


def _f(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default


def _iter_weeks(league: League, start: int | None, end: int | None):
    lo = start or 1
    hi = end or 18
    for wk in range(lo, hi + 1):
        b = league.box_scores(wk)
        if b:
            yield wk, b


def _get_team_abbrev(team) -> str:
    """Get team abbreviation from ESPN API Team object."""
    # Try different possible attribute names for team abbreviation
    for attr in ["abbrev", "team_abbrev", "abbreviation", "team_id", "name"]:
        if hasattr(team, attr):
            value = getattr(team, attr)
            if value and isinstance(value, str):
                return value
    # Fallback to team name if no abbreviation found
    return getattr(team, "name", "Unknown")


# --- Canonical team mapping helpers ---
def _load_alias_index(mapping_path: str) -> dict:
    try:
        with open(mapping_path, encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        aliases = y.get("aliases", []) if isinstance(y, dict) else []
        idx: dict[str, list[dict]] = {}
        for a in aliases:
            alias = a.get("alias")
            if not alias:
                continue
            idx.setdefault(alias, []).append(a)
        return idx
    except Exception:
        return {}


def _resolve_canonical(abbrev: str, year: int | None, idx: dict) -> str:
    rules = idx.get(abbrev)
    if not rules:
        return abbrev
    if year is None:
        for r in rules:
            if not r.get("start_year") and not r.get("end_year"):
                return r.get("canonical", abbrev)
        return rules[0].get("canonical", abbrev)
    for r in rules:
        s = r.get("start_year")
        e = r.get("end_year")
        if (s is None or year >= int(s)) and (e is None or year <= int(e)):
            return r.get("canonical", abbrev)
    return rules[0].get("canonical", abbrev)


def _load_canonical_meta() -> dict:
    """Load canonical team metadata keyed by (year, team_code)."""
    path = os.path.join(ROOT, "data", "teams", "canonical_teams.csv")
    meta: dict[tuple[int, str], dict] = {}
    if not os.path.exists(path):
        return meta
    import csv as _csv

    with open(path, newline="", encoding="utf-8") as f:
        r = _csv.DictReader(f)
        for row in r:
            try:
                y = int((row.get("season_year") or "").strip())
            except Exception:
                continue
            code = (row.get("team_code") or "").strip()
            if not y or not code:
                continue
            meta[(y, code)] = {
                "team_full_name": (row.get("team_full_name") or "").strip(),
                "is_co_owned": (row.get("is_co_owned") or "").strip(),
                "owner_code_1": (
                    row.get("owner_code_1") or row.get("owner_code") or ""
                ).strip(),
                "owner_code_2": (
                    row.get("owner_code_2") or row.get("co_owner_code") or ""
                ).strip(),
            }
    return meta


def _validate_rffl_lineup(starters_df: pd.DataFrame) -> Dict[str, Any]:
    """Validate RFFL lineup compliance and return issues found."""
    issues = []

    # Count starters by slot
    slot_counts = starters_df["slot"].value_counts().to_dict()

    # Check each required position
    for position, required_count in RFFL_LINEUP_REQUIREMENTS.items():
        actual_count = slot_counts.get(position, 0)
        if actual_count != required_count:
            issues.append(
                {
                    "type": "count_mismatch",
                    "position": position,
                    "required": required_count,
                    "actual": actual_count,
                    "description": (
                        f"Expected {required_count} {position}, "
                        f"found {actual_count}"
                    ),
                }
            )

    # Check FLEX eligibility
    flex_players = starters_df[starters_df["slot"] == "FLEX"]
    for _, player in flex_players.iterrows():
        player_position = player["position"]
        if player_position not in FLEX_ELIGIBLE_POSITIONS:
            issues.append(
                {
                    "type": "flex_ineligible",
                    "position": player_position,
                    "player": player["player_name"],
                    "description": (
                        f"FLEX player {player['player_name']} pos {player_position} "
                        "not RB/WR/TE"
                    ),
                }
            )

    # Check for duplicate players
    player_counts = starters_df["player_name"].value_counts()
    duplicates = player_counts[player_counts > 1]
    for player, count in duplicates.items():
        issues.append(
            {
                "type": "duplicate_player",
                "player": player,
                "count": count,
                "description": f"Player {player} appears {count} times in starters",
            }
        )

    # Check for invalid positions in specific slots
    for _, player in starters_df.iterrows():
        slot = player["slot"]
        position = player["position"]

        # QB slot should only have QB position
        if slot == "QB" and position != "QB":
            issues.append(
                {
                    "type": "invalid_position_in_slot",
                    "slot": slot,
                    "position": position,
                    "player": player["player_name"],
                    "description": (
                        f"QB slot contains {position} "
                        f"player {player['player_name']}"
                    ),
                }
            )

        # K slot should only have K position
        if slot == "K" and position != "K":
            issues.append(
                {
                    "type": "invalid_position_in_slot",
                    "slot": slot,
                    "position": position,
                    "player": player["player_name"],
                    "description": (
                        f"K slot contains {position} " f"player {player['player_name']}"
                    ),
                }
            )

        # D/ST slot should only have D/ST position
        if slot == "D/ST" and position != "D/ST":
            issues.append(
                {
                    "type": "invalid_position_in_slot",
                    "slot": slot,
                    "position": position,
                    "player": player["player_name"],
                    "description": (
                        f"D/ST slot contains {position} "
                        f"player {player['player_name']}"
                    ),
                }
            )

    return {"is_valid": len(issues) == 0, "issues": issues, "total_issues": len(issues)}


@dataclass
class Row:
    season_year: int
    week: int
    matchup: int
    team_code: str
    is_co_owned: str
    team_owner_1: str
    team_owner_2: str
    team_projected_total: float
    team_actual_total: float
    slot_type: str
    slot: str
    player_name: str
    nfl_team: str | None
    position: str | None
    is_placeholder: str
    issue_flag: str | None
    rs_projected_pf: float
    rs_actual_pf: float


def _export(
    league_id: int,
    year: int,
    espn_s2: str | None,
    swid: str | None,
    start_week: int | None,
    end_week: int | None,
    out_path: str,
    fill_missing_slots: bool = False,
    require_clean: bool = False,
    tolerance: float = 0.0,
) -> str:
    try:
        lg = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize ESPN League (league={league_id}, year={year}). "
            f"Check LEAGUE/ESPN_S2/SWID and network. Error: {e}"
        ) from e
    rows: List[Row] = []

    try:
        # Load alias index once for canonical team_code resolution
        mapping_path = os.path.join(ROOT, "data", "teams", "alias_mapping.yaml")
        alias_idx = _load_alias_index(mapping_path)
        for week, boxscores in _iter_weeks(lg, start_week, end_week):
            for m_idx, bs in enumerate(boxscores, start=1):
                for side in ("home", "away"):
                    team = getattr(bs, f"{side}_team", None)
                    lineup = getattr(bs, f"{side}_lineup", None) or []
                    if not team:
                        continue
                    # resolve canonical team_code
                    src_abbrev = _get_team_abbrev(team)
                    team_code = _resolve_canonical(src_abbrev, year, alias_idx)
                    # owners/co-owned from canonical meta
                    canon_meta = _load_canonical_meta()
                    meta = canon_meta.get((year, team_code), {})
                    is_co_owned = meta.get("is_co_owned", "")
                    owner1 = meta.get("owner_code_1", "")
                    owner2 = meta.get("owner_code_2", "")

                    # Build starter list
                    # Per-player rounding occurs before summing so team totals
                    # match the sum of starter rows exactly.
                    starters = []
                    stamped = []
                    for _idx, bp in enumerate(lineup):
                        slot = _norm_slot(
                            getattr(bp, "slot_position", None),
                            getattr(bp, "position", None),
                        )
                        proj = round(_f(getattr(bp, "projected_points", 0.0)), 2)
                        act = round(_f(getattr(bp, "points", 0.0)), 2)
                        row = {
                            "slot": slot,
                            "slot_type": "starters" if _is_starter(slot) else "bench",
                            "player_name": getattr(bp, "name", None),
                            "nfl_team": getattr(bp, "proTeam", ""),
                            "position": getattr(bp, "position", None),
                            "is_placeholder": "No",
                            "issue_flag": "",
                            "rs_projected_pf": proj,
                            "rs_actual_pf": act,
                            "_orig_idx": _idx,
                        }
                        # Flag invalid FLEX position on real rows (RB/WR/TE only)
                        if row["slot"] == "FLEX":
                            pos = (row.get("position") or "").upper()
                            if pos not in FLEX_ELIGIBLE_POSITIONS:
                                row["issue_flag"] = (
                                    f"INVALID_FLEX_POSITION:{pos or 'UNKNOWN'}"
                                )
                        stamped.append(row)
                        if row["slot_type"] == "starters":
                            starters.append(row)

                    # Fill missing required starter slots (0-pt placeholders)
                    if fill_missing_slots:
                        # Count current starters by slot
                        have_counts = {}
                        for r in starters:
                            have_counts[r["slot"]] = have_counts.get(r["slot"], 0) + 1

                        for req_slot, req_count in RFFL_LINEUP_REQUIREMENTS.items():
                            have = have_counts.get(req_slot, 0)
                            missing = max(0, req_count - have)
                            for i in range(missing):
                                placeholder = {
                                    "slot": req_slot,
                                    "slot_type": "starters",
                                    "player_name": f"EMPTY SLOT - {req_slot}",
                                    # FLEX placeholder uses a FLEX-eligible position
                                    "position": (
                                        req_slot if req_slot != "FLEX" else "WR"
                                    ),
                                    "nfl_team": "",
                                    "is_placeholder": "Yes",
                                    "issue_flag": f"MISSING_SLOT:{req_slot}",
                                    "rs_projected_pf": 0.0,
                                    "rs_actual_pf": 0.0,
                                    "_orig_idx": 1000,
                                }
                                starters.append(placeholder)
                                stamped.append(placeholder)

                    team_proj = round(sum(r["rs_projected_pf"] for r in starters), 2)
                    team_act = round(sum(r["rs_actual_pf"] for r in starters), 2)
                    # Order rows: starters in fixed slot sequence, then bench (original order)
                    desired_order = [
                        "QB",
                        "RB",
                        "RB",
                        "WR",
                        "WR",
                        "TE",
                        "FLEX",
                        "D/ST",
                        "K",
                    ]
                    # Build starters by desired sequence
                    starters_by_slot = {}
                    for r in starters:
                        starters_by_slot.setdefault(r["slot"], []).append(r)
                    # Maintain original order within same slot
                    for lst in starters_by_slot.values():
                        lst.sort(key=lambda x: x.get("_orig_idx", 0))
                    starters_sorted: list[dict] = []
                    for s in desired_order:
                        if s in starters_by_slot and starters_by_slot[s]:
                            starters_sorted.append(starters_by_slot[s].pop(0))
                    # Append any leftover starters just in case (stable by slot then orig idx)
                    leftovers = [r for lst in starters_by_slot.values() for r in lst]
                    slot_rank = {
                        "QB": 0,
                        "RB": 1,
                        "WR": 2,
                        "TE": 3,
                        "FLEX": 4,
                        "D/ST": 5,
                        "K": 6,
                    }
                    leftovers.sort(
                        key=lambda x: (
                            slot_rank.get(x.get("slot", ""), 99),
                            x.get("_orig_idx", 0),
                        )
                    )
                    starters_sorted.extend(leftovers)
                    bench_sorted = [r for r in stamped if r["slot_type"] != "starters"]
                    bench_sorted.sort(key=lambda x: x.get("_orig_idx", 0))
                    ordered = starters_sorted + bench_sorted

                    for r in ordered:
                        r.pop("_orig_idx", None)
                        rows.append(
                            Row(
                                season_year=year,
                                week=week,
                                matchup=m_idx,
                                team_code=team_code,
                                is_co_owned=is_co_owned,
                                team_owner_1=owner1,
                                team_owner_2=owner2,
                                team_projected_total=team_proj,
                                team_actual_total=team_act,
                                **r,
                            )
                        )
    except Exception as e:
        raise RuntimeError(f"Failed fetching box scores. Error: {e}") from e

    df = pd.DataFrame([asdict(r) for r in rows])
    # Rename columns to final header names
    rename_map = {
        "is_co_owned": "is_co_owned?",
    }
    df = df.rename(columns=rename_map)

    # Optional: enforce cleanliness before writing
    if require_clean:
        starters = df[df["slot_type"] == "starters"].copy()
        team_key = "team_code" if "team_code" in starters.columns else "team_abbrev"
        agg = starters.groupby(["week", "matchup", team_key], as_index=False).agg(
            team_projected_total=("team_projected_total", "first"),
            team_actual_total=("team_actual_total", "first"),
            starters_proj_sum=("rs_projected_pf", "sum"),
            starters_actual_sum=("rs_actual_pf", "sum"),
            starter_count=("slot", "count"),
        )
        agg["proj_diff"] = (
            agg["starters_proj_sum"] - agg["team_projected_total"]
        ).round(2)
        agg["act_diff"] = (agg["starters_actual_sum"] - agg["team_actual_total"]).round(
            2
        )

        bad_proj = agg[agg["proj_diff"].abs() > tolerance]
        bad_act = agg[agg["act_diff"].abs() > tolerance]
        bad_cnt = agg[agg["starter_count"] != 9]

        if not bad_proj.empty or not bad_act.empty or not bad_cnt.empty:
            raise RuntimeError(
                (
                    f"Export not clean: proj={len(bad_proj)}, act={len(bad_act)}, "
                    f"bad_count={len(bad_cnt)}."
                )
            )

    out = out_path or f"validated_boxscores_{year}.csv"
    df.to_csv(out, index=False, quoting=csv.QUOTE_MINIMAL)
    return out


@dataclass
class H2HRow:
    week: int
    matchup: int
    home_team: str
    away_team: str
    home_score: float
    away_score: float
    winner: str  # home_team, away_team, or TIE
    margin: float


def _export_h2h(
    league_id: int,
    year: int,
    espn_s2: str | None,
    swid: str | None,
    start_week: int | None,
    end_week: int | None,
    out_path: str | None,
) -> str:
    """Export simplified head-to-head matchup results for a season.

    This uses per-matchup team scores from ESPN (no per-player lineups),
    which is more stable for older seasons (pre-2019).
    """
    try:
        lg = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize ESPN League (league={league_id}, year={year}). "
            f"Check LEAGUE/ESPN_S2/SWID and network. Error: {e}"
        ) from e

    rows: List[H2HRow] = []

    # Iterate via scoreboard to support pre-2019 seasons
    lo = start_week or 1
    hi = end_week or 18
    try:
        for week in range(lo, hi + 1):
            try:
                matchups = lg.scoreboard(week)
            except Exception:
                # Skip weeks that cannot be fetched
                continue
            if not matchups:
                continue
            for m_idx, mu in enumerate(matchups, start=1):
                home_t = getattr(mu, "home_team", None)
                away_t = getattr(mu, "away_team", None)
                home_score = round(_f(getattr(mu, "home_score", None), 0.0), 2)
                away_score = round(_f(getattr(mu, "away_score", None), 0.0), 2)

                home_abbrev = _get_team_abbrev(home_t) if home_t else "HOME"
                away_abbrev = _get_team_abbrev(away_t) if away_t else "AWAY"

                if home_score > away_score:
                    winner = home_abbrev
                elif away_score > home_score:
                    winner = away_abbrev
                else:
                    winner = "TIE"

                margin = round(abs(home_score - away_score), 2)

                rows.append(
                    H2HRow(
                        week=week,
                        matchup=m_idx,
                        home_team=home_abbrev,
                        away_team=away_abbrev,
                        home_score=home_score,
                        away_score=away_score,
                        winner=winner,
                        margin=margin,
                    )
                )
    except Exception as e:
        raise RuntimeError(f"Failed fetching matchup results. Error: {e}") from e

    out = out_path or f"h2h_{year}.csv"
    pd.DataFrame([asdict(r) for r in rows]).to_csv(
        out, index=False, quoting=csv.QUOTE_MINIMAL
    )
    return out


@app.command("export")
def cmd_export(
    league: int | None = typer.Option(None, help="ESPN leagueId (defaults to $LEAGUE)"),
    year: int = typer.Option(..., help="Season year"),
    out: str = typer.Option(None, help="Output CSV path"),
    start_week: int = typer.Option(None, help="Start week (default auto)"),
    end_week: int = typer.Option(None, help="End week (default auto)"),
    espn_s2: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $ESPN_S2"
    ),
    swid: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $SWID"
    ),
    fill_missing_slots: bool = typer.Option(
        False,
        help="Insert 0-pt placeholders for missing required starter slots",
    ),
    require_clean: bool = typer.Option(
        False,
        help="Validate in-memory and fail if sums/counts are not clean",
    ),
    tolerance: float = typer.Option(
        0.0,
        help="Allowed |sum(starters rs_projected_pf) - team_projected_total| for --require-clean",
    ),
):
    """Export ESPN fantasy football boxscores to CSV format."""
    league_id = league
    if league_id is None:
        env_league = os.getenv("LEAGUE")
        if env_league and env_league.isdigit():
            league_id = int(env_league)
    if league_id is None:
        typer.echo("❌ Missing league id. Pass --league or set $LEAGUE in .env")
        raise typer.Exit(1)

    try:
        path = _export(
            league_id=league_id,
            year=year,
            espn_s2=espn_s2 or os.getenv("ESPN_S2"),
            swid=swid or os.getenv("SWID"),
            start_week=start_week,
            end_week=end_week,
            out_path=out or f"validated_boxscores_{year}.csv",
            fill_missing_slots=fill_missing_slots,
            require_clean=require_clean,
            tolerance=tolerance,
        )
    except Exception as e:
        typer.echo(f"❌ Export failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote {path}")


@dataclass
class DraftRow:
    year: int
    round: int | None
    round_pick: int | None
    team_abbrev: str
    player_id: int | None
    player_name: str
    bid_amount: float | None
    keeper: bool | None
    nominating_team: str | None


def _export_draft(
    league_id: int,
    year: int,
    espn_s2: str | None,
    swid: str | None,
    out_path: str | None,
) -> str:
    try:
        lg = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize ESPN League (league={league_id}, year={year}). "
            f"Check LEAGUE/ESPN_S2/SWID and network. Error: {e}"
        ) from e

    # League initialization already fetches players, teams, and draft picks.
    # Avoid calling refresh_draft here to prevent duplicate picks from being appended.

    rows: List[DraftRow] = []
    for p in getattr(lg, "draft", []) or []:
        team_abbrev = _get_team_abbrev(getattr(p, "team", None))
        nom_team = (
            _get_team_abbrev(getattr(p, "nominatingTeam", None))
            if getattr(p, "nominatingTeam", None)
            else None
        )
        rows.append(
            DraftRow(
                year=year,
                round=getattr(p, "round_num", None),
                round_pick=getattr(p, "round_pick", None),
                team_abbrev=team_abbrev,
                player_id=getattr(p, "playerId", None),
                player_name=(getattr(p, "playerName", None) or ""),
                bid_amount=(
                    float(p.bid_amount)
                    if getattr(p, "bid_amount", None) is not None
                    else None
                ),
                keeper=getattr(p, "keeper_status", None),
                nominating_team=nom_team,
            )
        )

    out = out_path or f"draft_{year}.csv"
    pd.DataFrame([asdict(r) for r in rows]).to_csv(
        out, index=False, quoting=csv.QUOTE_MINIMAL
    )
    return out


@app.command("draft")
def cmd_draft(
    league: int | None = typer.Option(None, help="ESPN leagueId (defaults to $LEAGUE)"),
    year: int = typer.Option(..., help="Season year"),
    out: str = typer.Option(
        None, help="Output CSV path (default data/seasons/<year>/draft.csv)"
    ),
    espn_s2: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $ESPN_S2"
    ),
    swid: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $SWID"
    ),
):
    """Export season draft results to CSV (snake or auction)."""
    league_id = league
    if league_id is None:
        env_league = os.getenv("LEAGUE")
        if env_league and env_league.isdigit():
            league_id = int(env_league)
    if league_id is None:
        typer.echo("❌ Missing league id. Pass --league or set $LEAGUE in .env")
        raise typer.Exit(1)

    default_out = out or os.path.join("data", "seasons", str(year), "draft.csv")
    try:
        os.makedirs(os.path.dirname(default_out), exist_ok=True)
    except Exception:
        pass

    try:
        path = _export_draft(
            league_id=league_id,
            year=year,
            espn_s2=espn_s2 or os.getenv("ESPN_S2"),
            swid=swid or os.getenv("SWID"),
            out_path=default_out,
        )
    except Exception as e:
        typer.echo(f"❌ Draft export failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote {path}")


@app.command("h2h")
def cmd_h2h(
    league: int | None = typer.Option(None, help="ESPN leagueId (defaults to $LEAGUE)"),
    year: int = typer.Option(..., help="Season year"),
    out: str = typer.Option(None, help="Output CSV path (default h2h_<year>.csv)"),
    start_week: int = typer.Option(None, help="Start week (default auto)"),
    end_week: int = typer.Option(None, help="End week (default auto)"),
    espn_s2: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $ESPN_S2"
    ),
    swid: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $SWID"
    ),
):
    """Export simplified head-to-head matchup results to CSV.

    Columns: week, matchup, home_team, away_team, home_score, away_score,
    winner, margin. Suitable for older seasons where per-player boxscores
    are unavailable.
    """
    league_id = league
    if league_id is None:
        env_league = os.getenv("LEAGUE")
        if env_league and env_league.isdigit():
            league_id = int(env_league)
    if league_id is None:
        typer.echo("❌ Missing league id. Pass --league or set $LEAGUE in .env")
        raise typer.Exit(1)

    try:
        path = _export_h2h(
            league_id=league_id,
            year=year,
            espn_s2=espn_s2 or os.getenv("ESPN_S2"),
            swid=swid or os.getenv("SWID"),
            start_week=start_week,
            end_week=end_week,
            out_path=out or f"h2h_{year}.csv",
        )
    except Exception as e:
        typer.echo(f"❌ H2H export failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote {path}")


@app.command("validate")
def cmd_validate(
    csv_path: str = typer.Argument(..., help="validated_boxscores_YYYY.csv"),
    tolerance: float = typer.Option(
        0.0,
        help="Allowed |sum(starters rs_projected_pf) - team_projected_total| (e.g., 0.02)",
    ),
):
    """Validate exported boxscore data for consistency and completeness."""
    df = pd.read_csv(csv_path)
    starters = df[df["slot_type"] == "starters"].copy()
    team_key = "team_code" if "team_code" in starters.columns else "team_abbrev"
    agg = starters.groupby(["week", "matchup", team_key], as_index=False).agg(
        team_projected_total=("team_projected_total", "first"),
        team_actual_total=("team_actual_total", "first"),
        starters_proj_sum=("rs_projected_pf", "sum"),
        starters_actual_sum=("rs_actual_pf", "sum"),
        starter_count=("slot", "count"),
        slots_list=("slot", lambda s: ",".join(sorted(s))),
    )
    agg["proj_diff"] = (agg["starters_proj_sum"] - agg["team_projected_total"]).round(2)
    agg["act_diff"] = (agg["starters_actual_sum"] - agg["team_actual_total"]).round(2)

    bad_proj = agg[agg["proj_diff"].abs() > tolerance]
    bad_act = agg[agg["act_diff"].abs() > tolerance]
    bad_cnt = agg[agg["starter_count"] != 9]

    typer.echo(f"Team-weeks: {len(agg)}")
    typer.echo(f"❌ proj mismatches > {tolerance}: {len(bad_proj)}")
    typer.echo(f"❌ actual mismatches > {tolerance}: {len(bad_act)}")
    typer.echo(f"❌ starter_count != 9: {len(bad_cnt)}")

    if not bad_proj.empty or not bad_act.empty or not bad_cnt.empty:
        out = os.path.splitext(csv_path)[0] + "_validation_report.csv"
        pd.concat(
            [
                bad_proj.assign(issue="proj_mismatch"),
                bad_act.assign(issue="actual_mismatch"),
                bad_cnt.assign(issue="starter_count"),
            ],
            ignore_index=True,
        ).to_csv(out, index=False)
        typer.echo(f"↳ wrote detail: {out}")
    else:
        typer.echo("✅ clean")


@app.command("validate-lineup")
def cmd_validate_lineup(
    csv_path: str = typer.Argument(..., help="validated_boxscores_YYYY.csv"),
    out: str = typer.Option(None, help="Output report path"),
):
    """Validate RFFL lineup compliance (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K)."""
    df = pd.read_csv(csv_path)
    starters = df[df["slot_type"] == "starters"].copy()

    # Group by team-week and validate each lineup
    lineup_issues = []
    valid_lineups = 0
    total_lineups = 0

    team_key = "team_code" if "team_code" in starters.columns else "team_abbrev"
    for (week, matchup, team), lineup_df in starters.groupby(
        ["week", "matchup", team_key]
    ):
        total_lineups += 1
        validation = _validate_rffl_lineup(lineup_df)

        if validation["is_valid"]:
            valid_lineups += 1
        else:
            for issue in validation["issues"]:
                lineup_issues.append(
                    {
                        "week": week,
                        "matchup": matchup,
                        team_key: team,
                        "issue_type": issue["type"],
                        "description": issue["description"],
                        **{
                            k: v
                            for k, v in issue.items()
                            if k not in ["type", "description"]
                        },
                    }
                )

    # Print summary
    typer.echo("RFFL Lineup Validation Report")
    typer.echo("=" * 50)
    typer.echo(f"Total lineups checked: {total_lineups}")
    typer.echo(f"✅ Valid lineups: {valid_lineups}")
    typer.echo(f"❌ Invalid lineups: {total_lineups - valid_lineups}")
    typer.echo(f"Total issues found: {len(lineup_issues)}")

    if lineup_issues:
        typer.echo("\nIssues by type:")
        issue_types = {}
        for issue in lineup_issues:
            issue_type = issue["issue_type"]
            issue_types[issue_type] = issue_types.get(issue_type, 0) + 1

        for issue_type, count in sorted(issue_types.items()):
            typer.echo(f"  {issue_type}: {count}")

        # Write detailed report
        report_path = (
            out or os.path.splitext(csv_path)[0] + "_lineup_validation_report.csv"
        )
        pd.DataFrame(lineup_issues).to_csv(report_path, index=False)
        typer.echo(f"\n📄 Detailed report written to: {report_path}")

        # Show first few issues
        typer.echo("\nFirst 5 issues:")
        for i, issue in enumerate(lineup_issues[:5]):
            team_val = issue.get("team_code") or issue.get("team_abbrev")
            msg = (
                f"  {i+1}. Week {issue['week']} Matchup {issue['matchup']} "
                f"{team_val}: {issue['description']}"
            )
            typer.echo(msg)
    else:
        typer.echo("\n🎉 All lineups are RFFL compliant!")


@dataclass
class HistoricalRosterRow:
    season_year: int
    week: int
    matchup: int
    team_code: str
    slot: str
    player_name: str
    nfl_team: str | None
    position: str | None
    is_starter: bool


@dataclass
class TransactionRow:
    season_year: int
    bid_amount: float | None
    date: str
    effective_date: str | None
    id: str
    is_pending: bool
    rating: int | None
    status: str
    type: str
    team_id: int | None
    team_code: str | None
    member_id: int | None
    player_id: int | None
    player_name: str | None
    to_team_id: int | None
    to_team_code: str | None
    from_team_id: int | None
    from_team_code: str | None


def _export_transactions(
    league_id: int,
    year: int,
    espn_s2: str | None,
    swid: str | None,
    out_path: str | None,
) -> str:
    """Export transaction history using modern ESPN v3 API for 2018+ seasons."""
    from datetime import datetime
    import requests

    # Set up cookies for private leagues first
    cookies = {}
    if espn_s2:
        cookies["espn_s2"] = espn_s2
    if swid:
        cookies["SWID"] = swid

    base_url = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

    if year < 2018:
        # Try legacy leagueHistory endpoint
        url = f"{base_url}/leagueHistory/{league_id}?seasonId={year}&view=mTransactions"
    else:
        # Try separate communication endpoint that might contain transactions
        comm_url = (
            f"{base_url}/seasons/{year}/segments/0/leagues/{league_id}/communication/"
        )
        try:
            comm_response = requests.get(comm_url, cookies=cookies)
            if comm_response.status_code == 200:
                comm_data = comm_response.json()
                typer.echo(
                    f"📞 Communication endpoint keys: {list(comm_data.keys()) if isinstance(comm_data, dict) else 'Not a dict'}"
                )
        except Exception:
            pass

        # Try multiple comprehensive transaction view combinations
        view_combinations = [
            "view=mTransactions2&view=mTeam",
            "view=mTransactions&view=mTeam",
            "view=kona_league_communication",
            "view=mRoster&view=mTeam&view=mTransactions2",
            "view=mTeam&view=mSettings&view=mStatus&view=mTransactions2",
            "view=mPendingTransactions&view=mTeam",
        ]

        transactions_found = False
        for views in view_combinations:
            test_url = (
                f"{base_url}/seasons/{year}/segments/0/leagues/{league_id}?{views}"
            )
            try:
                test_response = requests.get(test_url, cookies=cookies)
                if test_response.status_code == 200:
                    test_data = test_response.json()
                    if isinstance(test_data, dict) and any(
                        key in test_data
                        for key in ["transactions", "recentTransactions", "activity"]
                    ):
                        typer.echo(f"✅ Found transactions with views: {views}")
                        url = test_url
                        transactions_found = True
                        break
            except Exception:
                continue

        if not transactions_found:
            # Fallback to basic endpoint
            url = f"{base_url}/seasons/{year}/segments/0/leagues/{league_id}?view=mTeam&view=mSettings&view=mStatus"

    try:
        response = requests.get(url, cookies=cookies)
        response.raise_for_status()
        data = response.json()

        # Handle different response structures
        if year < 2018 and isinstance(data, list) and data:
            # Legacy leagueHistory returns array, use first element
            league_data = data[0]
        else:
            league_data = data

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to fetch transaction data from ESPN API: {e}")
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Failed to parse ESPN API response: {e}")

    # Extract transaction data - try multiple possible keys
    transactions = []
    possible_keys = ["transactions", "recentTransactions", "activity", "recentActivity"]

    for key in possible_keys:
        if key in league_data:
            transactions = league_data[key]
            typer.echo(f"✅ Found transaction data under key: {key}")
            break

    if not transactions:
        typer.echo(f"⚠️  No transaction data found for {year}")
        # Debug: check what keys are available
        typer.echo(f"🔍 Available keys in API response: {list(league_data.keys())}")

        # Look for nested transaction data
        for key, value in league_data.items():
            if isinstance(value, dict) and any(
                subkey in str(value.keys()).lower()
                for subkey in ["transaction", "activity", "trade"]
            ):
                typer.echo(
                    f"🔍 Potential transaction data in {key}: {list(value.keys())}"
                )
        transactions = []

    # Create team code mapping
    teams_data = league_data.get("teams", [])
    team_id_to_code = {}
    for team in teams_data:
        team_id = team.get("id")
        # Use existing team abbrev logic
        team_code = None
        if "abbrev" in team:
            team_code = team["abbrev"]
        elif "teamAbbrev" in team:
            team_code = team["teamAbbrev"]
        elif "location" in team and "nickname" in team:
            team_code = f"{team['location'][:2].upper()}{team['nickname'][:2].upper()}"
        else:
            team_code = f"T{team_id}"

        team_id_to_code[team_id] = team_code

    # Process transactions
    rows: List[TransactionRow] = []
    for txn in transactions:
        # Extract basic transaction info
        txn_id = str(txn.get("id", ""))
        txn_type = txn.get("type", "")
        txn_status = txn.get("status", "")
        is_pending = txn.get("isPending", False)
        rating = txn.get("rating")
        bid_amount = txn.get("bidAmount")

        # Handle timestamps
        date_epoch = txn.get("date", 0)
        date_str = ""
        if date_epoch:
            try:
                date_str = datetime.fromtimestamp(date_epoch / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except (ValueError, OSError, OverflowError):
                date_str = str(date_epoch)

        effective_date_epoch = txn.get("effectiveDate")
        effective_date_str = None
        if effective_date_epoch:
            try:
                effective_date_str = datetime.fromtimestamp(
                    effective_date_epoch / 1000
                ).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError, OverflowError):
                effective_date_str = str(effective_date_epoch)

        # Handle team and member info
        team_id = txn.get("teamId")
        team_code = team_id_to_code.get(team_id) if team_id else None
        member_id = txn.get("memberId")

        # Process transaction items (players involved)
        items = txn.get("items", [])
        if not items:
            # Transaction with no items (rare but possible)
            rows.append(
                TransactionRow(
                    season_year=year,
                    bid_amount=bid_amount,
                    date=date_str,
                    effective_date=effective_date_str,
                    id=txn_id,
                    is_pending=is_pending,
                    rating=rating,
                    status=txn_status,
                    type=txn_type,
                    team_id=team_id,
                    team_code=team_code,
                    member_id=member_id,
                    player_id=None,
                    player_name=None,
                    to_team_id=None,
                    to_team_code=None,
                    from_team_id=None,
                    from_team_code=None,
                )
            )
        else:
            # Process each player/item in transaction
            for item in items:
                player_id = item.get("playerId")
                player_name = item.get("playerName", "")

                to_team_id = item.get("toTeamId")
                to_team_code = team_id_to_code.get(to_team_id) if to_team_id else None

                from_team_id = item.get("fromTeamId")
                from_team_code = (
                    team_id_to_code.get(from_team_id) if from_team_id else None
                )

                rows.append(
                    TransactionRow(
                        season_year=year,
                        bid_amount=bid_amount,
                        date=date_str,
                        effective_date=effective_date_str,
                        id=txn_id,
                        is_pending=is_pending,
                        rating=rating,
                        status=txn_status,
                        type=txn_type,
                        team_id=team_id,
                        team_code=team_code,
                        member_id=member_id,
                        player_id=player_id,
                        player_name=player_name,
                        to_team_id=to_team_id,
                        to_team_code=to_team_code,
                        from_team_id=from_team_id,
                        from_team_code=from_team_code,
                    )
                )

    # Generate output filename
    if not out_path:
        out_path = f"transactions_{year}.csv"

    # Write CSV
    os.makedirs(
        os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True
    )
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "season_year",
                "bid_amount",
                "date",
                "effective_date",
                "id",
                "is_pending",
                "rating",
                "status",
                "type",
                "team_id",
                "team_code",
                "member_id",
                "player_id",
                "player_name",
                "to_team_id",
                "to_team_code",
                "from_team_id",
                "from_team_code",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    return out_path


def _export_historical_rosters(
    league_id: int,
    year: int,
    espn_s2: str | None,
    swid: str | None,
    week: int | None,
    out_path: str | None,
) -> str:
    """Export END-OF-SEASON roster compositions for historical seasons (2011-2018) using leagueHistory API.

    NOTE: This API returns final roster state after all season transactions, not weekly lineups.
    """
    import requests

    # Use historical API endpoint for pre-2019 seasons
    # Try the newer base URL first, fall back to old one if needed
    base_url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory/{league_id}"
    params = {
        "seasonId": year,
        "view": ["mRoster", "mTeam"],  # Try to get team info too
    }

    if week:
        params["scoringPeriodId"] = week

    # Setup authentication cookies if provided
    cookies = {}
    if espn_s2:
        cookies["espn_s2"] = espn_s2
    if swid:
        cookies["SWID"] = swid

    try:
        response = requests.get(base_url, params=params, cookies=cookies)
        response.raise_for_status()

        # Historical API returns data wrapped in array
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            league_data = data[0]
        else:
            league_data = data

    except Exception as e:
        raise RuntimeError(
            f"Failed to fetch historical roster data for {year}. "
            f"URL: {base_url}, Params: {params}. Error: {e}"
        ) from e

    rows: List[HistoricalRosterRow] = []

    # Load alias index for canonical team resolution
    mapping_path = os.path.join(ROOT, "data", "teams", "alias_mapping.yaml")
    alias_idx = _load_alias_index(mapping_path)

    try:
        # Extract teams and their rosters
        teams = league_data.get("teams", [])

        for team in teams:
            team_id = team.get("id", "Unknown")
            # Now we have team info with mTeam view
            team_abbrev = (
                team.get("abbrev")
                or team.get("teamAbbrev")
                or team.get("name")
                or f"TEAM_{team_id}"
            )
            team_code = _resolve_canonical(team_abbrev, year, alias_idx)
            # Removed debug output

            # Get roster for each week requested
            roster = team.get("roster", {})
            entries = roster.get("entries", [])

            for entry in entries:
                player_info = entry.get("playerPoolEntry", {}).get("player", {})
                lineup_slot = entry.get("lineupSlotId", 0)

                # Map lineup slot ID to readable slot name
                slot_name = _map_lineup_slot_id(lineup_slot)
                # ESPN typically uses <20 for starters, but bench is 20, IR is 21
                is_starter = lineup_slot not in [20, 21]  # Not bench or IR

                player_name = player_info.get("fullName", "Unknown")
                pro_team = player_info.get("proTeamId")
                position = _map_position_id(player_info.get("defaultPositionId"))

                # Convert pro team ID to team abbreviation if available
                nfl_team = _map_pro_team_id(pro_team) if pro_team else None

                rows.append(
                    HistoricalRosterRow(
                        season_year=year,
                        week=week or 1,  # Default to week 1 if not specified
                        matchup=1,  # Historical data may not have matchup info
                        team_code=team_code,
                        slot=slot_name,
                        player_name=player_name,
                        nfl_team=nfl_team,
                        position=position,
                        is_starter=is_starter,
                    )
                )

    except Exception as e:
        raise RuntimeError(f"Failed to parse historical roster data. Error: {e}") from e

    if not rows:
        raise RuntimeError(
            "No roster data found. Check year, league_id, and credentials."
        )

    out = out_path or f"end_of_season_roster_{year}.csv"
    pd.DataFrame([asdict(r) for r in rows]).to_csv(
        out, index=False, quoting=csv.QUOTE_MINIMAL
    )
    return out


def _map_lineup_slot_id(slot_id: int) -> str:
    """Map ESPN lineup slot ID to readable slot name."""
    slot_mapping = {
        0: "QB",
        1: "TQB",
        2: "RB",
        3: "RB/WR",
        4: "WR",
        5: "WR/TE",
        6: "TE",
        7: "OP",
        8: "DT",
        9: "DE",
        10: "LB",
        11: "DL",
        12: "CB",
        13: "S",
        14: "DB",
        15: "DP",
        16: "D/ST",
        17: "K",
        20: "Bench",
        21: "IR",
        23: "FLEX",
    }
    return slot_mapping.get(slot_id, "Unknown")


def _map_position_id(position_id: int | None) -> str:
    """Map ESPN position ID to readable position."""
    if position_id is None:
        return "Unknown"
    position_mapping = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
    return position_mapping.get(position_id, "Unknown")


def _map_pro_team_id(team_id: int | None) -> str:
    """Map ESPN pro team ID to NFL team abbreviation."""
    if team_id is None:
        return None
    # This is a simplified mapping - you'd want to expand this
    team_mapping = {
        1: "ATL",
        2: "BUF",
        3: "CHI",
        4: "CIN",
        5: "CLE",
        6: "DAL",
        7: "DEN",
        8: "DET",
        9: "GB",
        10: "TEN",
        11: "IND",
        12: "KC",
        13: "LV",
        14: "LAR",
        15: "MIA",
        16: "MIN",
        17: "NE",
        18: "NO",
        19: "NYG",
        20: "NYJ",
        21: "PHI",
        22: "ARI",
        23: "PIT",
        24: "LAC",
        25: "SF",
        26: "SEA",
        27: "TB",
        28: "WAS",
        29: "CAR",
        30: "JAX",
        33: "BAL",
        34: "HOU",
    }
    return team_mapping.get(team_id, "Unknown")


@app.command("historical-rosters")
def cmd_historical_rosters(
    league: int | None = typer.Option(None, help="ESPN leagueId (defaults to $LEAGUE)"),
    year: int = typer.Option(..., help="Season year (2011-2018)"),
    week: int = typer.Option(
        None, help="Week parameter (IGNORED - all weeks return same data)"
    ),
    out: str = typer.Option(None, help="Output CSV path"),
    espn_s2: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $ESPN_S2"
    ),
    swid: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $SWID"
    ),
):
    """Export END-OF-SEASON roster compositions for historical seasons (2011-2018).

    WARNING: This does NOT return weekly starting lineups. The ESPN leagueHistory API
    returns final roster compositions after all trades, pickups, and drops.
    All weeks return identical data - use this to see how teams evolved from draft.

    For actual weekly lineups, use the 'export' command (available for 2019+).
    """
    if year >= 2019:
        typer.echo(
            "❌ Use 'export' command for 2019+ seasons. This command is for 2011-2018."
        )
        raise typer.Exit(1)

    # Warning about what this data represents
    typer.echo(f"⚠️  NOTE: This exports END-OF-SEASON roster composition for {year}")
    typer.echo(
        "   This is NOT weekly starting lineups - all weeks return identical data"
    )
    typer.echo("   Data shows final rosters after all trades, pickups, and drops")

    league_id = league
    if league_id is None:
        env_league = os.getenv("LEAGUE")
        if env_league and env_league.isdigit():
            league_id = int(env_league)
    if league_id is None:
        typer.echo("❌ Missing league id. Pass --league or set $LEAGUE in .env")
        raise typer.Exit(1)

    try:
        path = _export_historical_rosters(
            league_id=league_id,
            year=year,
            espn_s2=espn_s2 or os.getenv("ESPN_S2"),
            swid=swid or os.getenv("SWID"),
            week=week,
            out_path=out,
        )
    except Exception as e:
        typer.echo(f"❌ Historical roster export failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote historical rosters: {path}")


@app.command("transactions")
def cmd_transactions(
    league: int | None = typer.Option(None, help="ESPN leagueId (defaults to $LEAGUE)"),
    year: int = typer.Option(..., help="Season year (2018-2024 for modern API)"),
    out: str = typer.Option(None, help="Output CSV path"),
    espn_s2: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $ESPN_S2"
    ),
    swid: str = typer.Option(
        None, help="Cookie (private leagues). Falls back to $SWID"
    ),
):
    """Export league transaction history (trades, waivers, pickups, drops).

    Available for seasons 2018-2024 via modern ESPN v3 API.
    For seasons 2011-2017, uses legacy leagueHistory API (may not work due to ESPN data purge).

    Includes: trade details, waiver claims, free agent pickups/drops, IR moves, and bid amounts.
    """
    league_id = league
    if league_id is None:
        env_league = os.getenv("LEAGUE")
        if env_league and env_league.isdigit():
            league_id = int(env_league)
    if league_id is None:
        typer.echo("❌ Missing league id. Pass --league or set $LEAGUE in .env")
        raise typer.Exit(1)

    if year < 2018:
        typer.echo(
            f"⚠️  WARNING: Attempting to fetch {year} transaction data from legacy API"
        )
        typer.echo("   ESPN has purged most pre-2018 data - this may fail")
    elif year >= 2019:
        typer.echo(f"📊 Fetching {year} transaction data from modern ESPN v3 API")
    else:  # year == 2018
        typer.echo(
            f"📊 Fetching {year} transaction data (transition year - using modern API)"
        )

    try:
        path = _export_transactions(
            league_id=league_id,
            year=year,
            espn_s2=espn_s2 or os.getenv("ESPN_S2"),
            swid=swid or os.getenv("SWID"),
            out_path=out,
        )
    except Exception as e:
        typer.echo(f"❌ Transaction export failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote transaction history: {path}")


@dataclass
class RosterChange:
    season_year: int
    team_code: str
    team_draft_code: str
    change_type: str  # "added", "dropped", "kept"
    player_name: str
    draft_round: int | None
    draft_pick: int | None
    final_slot: str | None
    final_is_starter: bool | None


def _analyze_roster_changes(
    years: list[int],
    out_path: str | None,
) -> str:
    """Compare draft results to end-of-season rosters to identify roster changes."""

    # Team code mapping from draft to final (based on 2017 analysis)
    team_code_mapping = {
        "DPCX": "PCX",
        "JAG": "JAGB",
        "MXBN": "MXLB",
        "PTB": "PITB",
        "DKGG": "DKEG",
        "WWZ": "WZRD",
        # These stayed the same
        "BRIM": "BRIM",
        "CHLK": "CHLK",
        "GFM": "GFM",
        "LNO": "LNO",
        "MRYJ": "MRYJ",
        "SSS": "SSS",
    }

    all_changes: List[RosterChange] = []

    for year in years:
        draft_file = f"/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/seasons/{year}/draft.csv"
        roster_file = f"/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/end_of_season_rosters/final_roster_{year}.csv"

        try:
            draft_df = pd.read_csv(draft_file)
            roster_df = pd.read_csv(roster_file)

            # Normalize draft team codes
            draft_df["normalized_team_code"] = (
                draft_df["team_abbrev"]
                .map(team_code_mapping)
                .fillna(draft_df["team_abbrev"])
            )

            # Create sets for comparison
            for team_code in roster_df["team_code"].unique():
                # Find draft code for this team
                draft_team_code = None
                for draft_code, final_code in team_code_mapping.items():
                    if final_code == team_code:
                        draft_team_code = draft_code
                        break
                if draft_team_code is None:
                    draft_team_code = team_code  # Assume same if not found

                # Get drafted players for this team
                team_draft = draft_df[draft_df["normalized_team_code"] == team_code]
                drafted_players = set(
                    team_draft["player_name"].dropna().str.strip().str.lower()
                )

                # Get final roster players for this team
                team_roster = roster_df[roster_df["team_code"] == team_code]
                final_players = set(
                    team_roster["player_name"].dropna().str.strip().str.lower()
                )

                # Analyze changes
                kept_players = drafted_players.intersection(final_players)
                added_players = final_players - drafted_players
                dropped_players = drafted_players - final_players

                # Process kept players
                for player in kept_players:
                    draft_matches = team_draft[
                        team_draft["player_name"].str.strip().str.lower() == player
                    ]
                    roster_matches = team_roster[
                        team_roster["player_name"].str.strip().str.lower() == player
                    ]

                    if draft_matches.empty or roster_matches.empty:
                        typer.echo(f"⚠️  Skipping player '{player}' - no match found")
                        continue

                    draft_info = draft_matches.iloc[0]
                    roster_info = roster_matches.iloc[0]

                    all_changes.append(
                        RosterChange(
                            season_year=year,
                            team_code=team_code,
                            team_draft_code=draft_team_code,
                            change_type="kept",
                            player_name=roster_info[
                                "player_name"
                            ],  # Use final roster spelling
                            draft_round=draft_info["round"],
                            draft_pick=draft_info["round_pick"],
                            final_slot=roster_info["slot"],
                            final_is_starter=roster_info["is_starter"],
                        )
                    )

                # Process added players (pickups/trades)
                for player in added_players:
                    roster_matches = team_roster[
                        team_roster["player_name"].str.strip().str.lower() == player
                    ]

                    if roster_matches.empty:
                        typer.echo(
                            f"⚠️  Skipping added player '{player}' - no match found"
                        )
                        continue

                    roster_info = roster_matches.iloc[0]

                    all_changes.append(
                        RosterChange(
                            season_year=year,
                            team_code=team_code,
                            team_draft_code=draft_team_code,
                            change_type="added",
                            player_name=roster_info["player_name"],
                            draft_round=None,
                            draft_pick=None,
                            final_slot=roster_info["slot"],
                            final_is_starter=roster_info["is_starter"],
                        )
                    )

                # Process dropped players
                for player in dropped_players:
                    draft_matches = team_draft[
                        team_draft["player_name"].str.strip().str.lower() == player
                    ]

                    if draft_matches.empty:
                        typer.echo(
                            f"⚠️  Skipping dropped player '{player}' - no match found"
                        )
                        continue

                    draft_info = draft_matches.iloc[0]

                    all_changes.append(
                        RosterChange(
                            season_year=year,
                            team_code=team_code,
                            team_draft_code=draft_team_code,
                            change_type="dropped",
                            player_name=draft_info["player_name"],
                            draft_round=draft_info["round"],
                            draft_pick=draft_info["round_pick"],
                            final_slot=None,
                            final_is_starter=None,
                        )
                    )

        except FileNotFoundError as e:
            typer.echo(f"⚠️  Skipping {year}: {e}")
            continue
        except Exception as e:
            typer.echo(f"❌ Error processing {year}: {e}")
            continue

    # Generate output filename
    if not out_path:
        year_range = f"{min(years)}-{max(years)}" if len(years) > 1 else str(years[0])
        out_path = f"roster_changes_{year_range}.csv"

    # Write CSV
    os.makedirs(
        os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True
    )
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "season_year",
                "team_code",
                "team_draft_code",
                "change_type",
                "player_name",
                "draft_round",
                "draft_pick",
                "final_slot",
                "final_is_starter",
            ],
        )
        writer.writeheader()
        for change in all_changes:
            writer.writerow(asdict(change))

    return out_path


@app.command("roster-changes")
def cmd_roster_changes(
    start_year: int = typer.Option(2011, help="Starting year for analysis"),
    end_year: int = typer.Option(2017, help="Ending year for analysis"),
    out: str = typer.Option(None, help="Output CSV path"),
):
    """Analyze roster changes by comparing draft results to end-of-season rosters.

    For each team and year, identifies:
    - KEPT: Players drafted and still on final roster
    - ADDED: Players acquired during season (trades/pickups)
    - DROPPED: Players drafted but not on final roster

    Available for years 2011-2017 where both draft and final roster data exist.
    """
    years = list(range(start_year, end_year + 1))

    typer.echo(f"📊 Analyzing roster changes for years: {start_year}-{end_year}")
    typer.echo("   Comparing draft results vs end-of-season rosters...")

    try:
        path = _analyze_roster_changes(years=years, out_path=out)
    except Exception as e:
        typer.echo(f"❌ Roster change analysis failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote roster change analysis: {path}")


@dataclass
class WeeklyRosterChange:
    season_year: int
    week: int
    team_code: str
    change_type: str  # "added", "dropped", "kept", "draft_kept"
    player_name: str
    previous_week: int | None  # Week last seen (for drops)
    draft_round: int | None
    draft_pick: int | None
    slot_type: str | None
    is_starter: bool | None


def _analyze_weekly_roster_changes(
    years: list[int],
    out_path: str | None,
) -> str:
    """Track weekly roster changes using boxscores data for modern seasons (2019-2024)."""

    all_changes: List[WeeklyRosterChange] = []

    for year in years:
        typer.echo(f"📅 Processing {year}...")

        try:
            # Load boxscores for this year
            boxscores_file = f"/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/seasons/{year}/boxscores.csv"
            boxscores_df = pd.read_csv(boxscores_file)

            # Load draft data (use canonical version with correct team codes)
            draft_file = f"/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/seasons/{year}/reports/{year}-Draft-Snake-Canonicals.csv"
            draft_df = pd.read_csv(draft_file)

            # Create draft lookup
            draft_lookup = {}
            for _, row in draft_df.iterrows():
                if pd.notna(row["player_name"]) and pd.notna(row["team_code"]):
                    player_name = str(row["player_name"]).strip().lower()
                    if player_name:  # Skip empty names
                        draft_lookup[player_name] = {
                            "team": row["team_code"],
                            "round": row["round"],
                            "pick": row["round_pick"],
                        }

            # Process each team
            teams = boxscores_df["team_code"].unique()
            weeks = sorted(boxscores_df["week"].unique())

            for team in teams:
                team_data = boxscores_df[boxscores_df["team_code"] == team]
                previous_week_roster = set()

                for week in weeks:
                    week_data = team_data[team_data["week"] == week]
                    # Clean player names and handle NaN values
                    clean_names = (
                        week_data["player_name"]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .str.lower()
                    )
                    current_week_roster = set(
                        name for name in clean_names if name and name != "nan"
                    )

                    if week == weeks[0]:
                        # First week - compare with draft
                        draft_team_players = {
                            name.lower()
                            for name, info in draft_lookup.items()
                            if info["team"] == team
                        }

                        # Players kept from draft
                        draft_kept = current_week_roster.intersection(
                            draft_team_players
                        )
                        for player in draft_kept:
                            player_info = week_data[
                                week_data["player_name"].str.strip().str.lower()
                                == player
                            ]
                            if not player_info.empty:
                                info = player_info.iloc[0]
                                draft_info = draft_lookup.get(player, {})
                                all_changes.append(
                                    WeeklyRosterChange(
                                        season_year=year,
                                        week=week,
                                        team_code=team,
                                        change_type="draft_kept",
                                        player_name=info["player_name"],
                                        previous_week=None,
                                        draft_round=draft_info.get("round"),
                                        draft_pick=draft_info.get("pick"),
                                        slot_type=info["slot_type"],
                                        is_starter=info["slot_type"] == "starter",
                                    )
                                )

                        # Players added from draft (pickups before week 1)
                        draft_added = current_week_roster - draft_team_players
                        for player in draft_added:
                            player_info = week_data[
                                week_data["player_name"].str.strip().str.lower()
                                == player
                            ]
                            if not player_info.empty:
                                info = player_info.iloc[0]
                                all_changes.append(
                                    WeeklyRosterChange(
                                        season_year=year,
                                        week=week,
                                        team_code=team,
                                        change_type="added",
                                        player_name=info["player_name"],
                                        previous_week=None,
                                        draft_round=None,
                                        draft_pick=None,
                                        slot_type=info["slot_type"],
                                        is_starter=info["slot_type"] == "starter",
                                    )
                                )

                        # Players dropped from draft
                        draft_dropped = draft_team_players - current_week_roster
                        for player in draft_dropped:
                            draft_info = draft_lookup.get(player, {})
                            # Use the draft spelling for dropped players
                            player_name = next(
                                (
                                    name
                                    for name in draft_lookup.keys()
                                    if name == player
                                ),
                                player,
                            )
                            all_changes.append(
                                WeeklyRosterChange(
                                    season_year=year,
                                    week=week,
                                    team_code=team,
                                    change_type="dropped",
                                    player_name=player_name.title(),  # Capitalize for display
                                    previous_week=0,  # 0 indicates dropped from draft
                                    draft_round=draft_info.get("round"),
                                    draft_pick=draft_info.get("pick"),
                                    slot_type=None,
                                    is_starter=None,
                                )
                            )

                    else:
                        # Week 2+ - compare with previous week
                        added_players = current_week_roster - previous_week_roster
                        dropped_players = previous_week_roster - current_week_roster
                        # kept_players = current_week_roster.intersection(
                        #     previous_week_roster
                        # )

                        # Players added this week
                        for player in added_players:
                            player_info = week_data[
                                week_data["player_name"].str.strip().str.lower()
                                == player
                            ]
                            if not player_info.empty:
                                info = player_info.iloc[0]
                                draft_info = draft_lookup.get(player, {})
                                all_changes.append(
                                    WeeklyRosterChange(
                                        season_year=year,
                                        week=week,
                                        team_code=team,
                                        change_type="added",
                                        player_name=info["player_name"],
                                        previous_week=None,
                                        draft_round=draft_info.get("round"),
                                        draft_pick=draft_info.get("pick"),
                                        slot_type=info["slot_type"],
                                        is_starter=info["slot_type"] == "starter",
                                    )
                                )

                        # Players dropped this week
                        for player in dropped_players:
                            draft_info = draft_lookup.get(player, {})
                            player_name = player.title()  # Capitalize for display
                            all_changes.append(
                                WeeklyRosterChange(
                                    season_year=year,
                                    week=week,
                                    team_code=team,
                                    change_type="dropped",
                                    player_name=player_name,
                                    previous_week=week - 1,
                                    draft_round=draft_info.get("round"),
                                    draft_pick=draft_info.get("pick"),
                                    slot_type=None,
                                    is_starter=None,
                                )
                            )

                    previous_week_roster = current_week_roster

        except FileNotFoundError as e:
            typer.echo(f"⚠️  Skipping {year}: {e}")
            continue
        except Exception as e:
            typer.echo(f"❌ Error processing {year}: {e}")
            continue

    # Generate output filename
    if not out_path:
        year_range = f"{min(years)}-{max(years)}" if len(years) > 1 else str(years[0])
        out_path = f"weekly_roster_changes_{year_range}.csv"

    # Write CSV
    os.makedirs(
        os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True
    )
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "season_year",
                "week",
                "team_code",
                "change_type",
                "player_name",
                "previous_week",
                "draft_round",
                "draft_pick",
                "slot_type",
                "is_starter",
            ],
        )
        writer.writeheader()
        for change in all_changes:
            writer.writerow(asdict(change))

    return out_path


@app.command("weekly-roster-changes")
def cmd_weekly_roster_changes(
    start_year: int = typer.Option(2019, help="Starting year for analysis"),
    end_year: int = typer.Option(2024, help="Ending year for analysis"),
    out: str = typer.Option(None, help="Output CSV path"),
):
    """Track weekly roster changes using boxscores data for modern seasons.

    For each team, week, and year, identifies:
    - DRAFT_KEPT: Players drafted and on Week 1 roster
    - ADDED: Players acquired during season (specific week)
    - DROPPED: Players released (last seen week)
    - Weekly timing of all roster moves

    Available for years 2019-2024 where weekly boxscores data exists.
    """
    years = list(range(start_year, end_year + 1))

    typer.echo(f"📊 Analyzing weekly roster changes for years: {start_year}-{end_year}")
    typer.echo("   Tracking week-by-week player movements...")

    try:
        path = _analyze_weekly_roster_changes(years=years, out_path=out)
    except Exception as e:
        typer.echo(f"❌ Weekly roster change analysis failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote weekly roster change analysis: {path}")


def _estimate_historical_transaction_patterns(
    historical_years: list[int],
    modern_years: list[int],
    out_path: str | None,
) -> str:
    """Estimate weekly transaction patterns for 2011-2017 based on 2019-2024 behavioral data."""

    # Load modern weekly data for pattern analysis
    modern_file = "/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/roster_changes/weekly_changes_2019-2024.csv"
    historical_file = "/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/roster_changes/roster_changes_2011-2017.csv"

    try:
        modern_df = pd.read_csv(modern_file)
        historical_df = pd.read_csv(historical_file)
    except FileNotFoundError as e:
        raise RuntimeError(f"Required data files not found: {e}")

    typer.echo("📊 Analyzing modern transaction patterns (2019-2024)...")

    # Analyze modern patterns
    modern_active = modern_df[modern_df["change_type"].isin(["added", "dropped"])]

    # Weekly distribution pattern
    weekly_pattern = modern_active.groupby("week").size()
    weekly_pattern_pct = (weekly_pattern / weekly_pattern.sum()) * 100

    # Round-based drop probability
    modern_drafted = modern_active[modern_active["draft_round"].notna()]
    round_drop_pattern = (
        modern_drafted[modern_drafted["change_type"] == "dropped"]
        .groupby("draft_round")
        .size()
    )
    total_drafted_by_round = (
        modern_df[modern_df["draft_round"].notna()].groupby("draft_round").size()
    )
    drop_probability_by_round = (
        round_drop_pattern / total_drafted_by_round * 100
    ).fillna(0)

    # Team activity patterns
    team_activity_modern = modern_active.groupby(["season_year", "team_code"]).size()
    avg_team_moves_per_year = team_activity_modern.groupby("season_year").mean()

    # Position-based patterns
    position_patterns = {}
    for pos in ["QB", "RB", "WR", "TE", "K", "D/ST"]:
        pos_data = modern_active[
            modern_active["player_name"].str.contains(pos, case=False, na=False)
        ]
        if not pos_data.empty:
            position_patterns[pos] = pos_data.groupby("week").size()

    typer.echo("🔮 Estimating historical transaction timing...")

    # Create estimated weekly transactions for historical data
    estimated_transactions = []

    for _, historical_row in historical_df.iterrows():
        year = historical_row["season_year"]
        team = historical_row["team_code"]
        change_type = historical_row["change_type"]
        player_name = historical_row["player_name"]
        draft_round = historical_row["draft_round"]

        if change_type in ["added", "dropped"]:
            # Estimate week based on multiple factors
            estimated_week = _estimate_transaction_week(
                change_type=change_type,
                draft_round=draft_round,
                player_name=player_name,
                weekly_pattern=weekly_pattern_pct,
                drop_probability_by_round=drop_probability_by_round,
            )

            estimated_transactions.append(
                {
                    "season_year": year,
                    "estimated_week": estimated_week,
                    "team_code": team,
                    "change_type": change_type,
                    "player_name": player_name,
                    "draft_round": draft_round,
                    "draft_pick": historical_row["draft_pick"],
                    "confidence": _calculate_confidence(
                        change_type, draft_round, player_name
                    ),
                    "estimation_method": _get_estimation_method(
                        change_type, draft_round, player_name
                    ),
                }
            )

    # Convert to DataFrame
    estimated_df = pd.DataFrame(estimated_transactions)

    # Generate summary statistics
    typer.echo("📈 Generating pattern-based estimates...")

    # Create comprehensive analysis
    analysis_summary = {
        "modern_patterns": {
            "avg_moves_per_team_per_year": avg_team_moves_per_year.mean(),
            "most_active_weeks": weekly_pattern.sort_values(ascending=False)
            .head(5)
            .to_dict(),
            "highest_drop_rounds": drop_probability_by_round.sort_values(
                ascending=False
            )
            .head(5)
            .to_dict(),
        },
        "historical_estimates": {
            "total_estimated_transactions": len(estimated_df),
            "estimated_weekly_distribution": estimated_df.groupby("estimated_week")
            .size()
            .to_dict(),
            "confidence_breakdown": estimated_df.groupby("confidence").size().to_dict(),
        },
    }

    # Generate output filename
    if not out_path:
        out_path = "estimated_historical_transactions_2011-2017.csv"

    # Write CSV with estimates
    os.makedirs(
        os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True
    )
    estimated_df.to_csv(out_path, index=False)

    # Also create a summary report
    summary_path = out_path.replace(".csv", "_analysis.txt")
    with open(summary_path, "w") as f:
        f.write("RFFL Historical Transaction Pattern Analysis\\n")
        f.write("=" * 50 + "\\n\\n")
        f.write(f"Modern Pattern Analysis (2019-2024):\\n")
        f.write(
            f"- Average moves per team per year: {analysis_summary['modern_patterns']['avg_moves_per_team_per_year']:.1f}\\n"
        )
        f.write(
            f"- Most active weeks: {analysis_summary['modern_patterns']['most_active_weeks']}\\n"
        )
        f.write(
            f"- Highest drop probability rounds: {analysis_summary['modern_patterns']['highest_drop_rounds']}\\n\\n"
        )
        f.write(f"Historical Estimates (2011-2017):\\n")
        f.write(
            f"- Total estimated transactions: {analysis_summary['historical_estimates']['total_estimated_transactions']}\\n"
        )
        f.write(
            f"- Estimated weekly distribution: {analysis_summary['historical_estimates']['estimated_weekly_distribution']}\\n"
        )
        f.write(
            f"- Confidence levels: {analysis_summary['historical_estimates']['confidence_breakdown']}\\n"
        )

    return out_path


def _estimate_transaction_week(
    change_type: str,
    draft_round: float,
    player_name: str,
    weekly_pattern,
    drop_probability_by_round,
) -> int:
    """Estimate the week a transaction likely occurred based on modern patterns."""
    import random

    # Base probability on weekly patterns
    week_weights = weekly_pattern.to_dict()

    # Adjust based on transaction type and draft round
    if change_type == "dropped":
        if pd.notna(draft_round):
            # Early round picks (1-6) likely dropped later in season due to injury
            if draft_round <= 6:
                # Weight towards weeks 8-12 (injury time)
                for week in [8, 9, 10, 11, 12]:
                    if week in week_weights:
                        week_weights[week] *= 2.0
            # Late round picks (13-16) dropped early
            elif draft_round >= 13:
                # Weight towards weeks 1-4 (early corrections)
                for week in [1, 2, 3, 4]:
                    if week in week_weights:
                        week_weights[week] *= 2.0

    elif change_type == "added":
        # Defenses added more often during bye weeks (6-8, 10-12)
        if "D/ST" in player_name or "D/St" in player_name:
            for week in [6, 7, 8, 10, 11, 12]:
                if week in week_weights:
                    week_weights[week] *= 1.5

        # Kickers added when needed (similar to defenses)
        elif any(k in player_name.lower() for k in ["kicker", "k "]):
            for week in [6, 7, 8, 10, 11, 12]:
                if week in week_weights:
                    week_weights[week] *= 1.3

    # Normalize weights and sample
    total_weight = sum(week_weights.values())
    week_probs = {w: weight / total_weight for w, weight in week_weights.items()}

    # Sample based on probabilities
    weeks = list(week_probs.keys())
    probabilities = list(week_probs.values())

    return random.choices(weeks, weights=probabilities)[0]


def _calculate_confidence(
    change_type: str, draft_round: float, player_name: str
) -> str:
    """Calculate confidence level of the week estimation."""
    score = 0

    # Base confidence on available information
    if pd.notna(draft_round):
        score += 30
        # Early/late rounds have more predictable patterns
        if draft_round <= 3 or draft_round >= 14:
            score += 20

    # Position-specific patterns are more predictable
    if "D/ST" in player_name or "D/St" in player_name:
        score += 25  # Defense streaming is very predictable
    elif any(k in player_name.lower() for k in ["tucker", "bass", "santos", "koo"]):
        score += 20  # Kicker patterns somewhat predictable

    # Transaction type patterns
    if change_type == "dropped":
        score += 15  # Drops have clearer patterns than adds

    if score >= 70:
        return "high"
    elif score >= 40:
        return "medium"
    else:
        return "low"


def _get_estimation_method(
    change_type: str, draft_round: float, player_name: str
) -> str:
    """Describe the method used for estimation."""
    methods = []

    if pd.notna(draft_round):
        if draft_round <= 6:
            methods.append("early_round_injury_pattern")
        elif draft_round >= 13:
            methods.append("late_round_early_drop_pattern")
        else:
            methods.append("mid_round_general_pattern")

    if "D/ST" in player_name or "D/St" in player_name:
        methods.append("defense_streaming_pattern")
    elif any(k in player_name.lower() for k in ["tucker", "bass", "santos", "koo"]):
        methods.append("kicker_adjustment_pattern")

    methods.append("weekly_distribution_weighting")

    return "+".join(methods)


@app.command("estimate-historical-patterns")
def cmd_estimate_historical_patterns(
    out: str = typer.Option(None, help="Output CSV path"),
):
    """Estimate weekly transaction timing for 2011-2017 based on 2019-2024 patterns.

    Uses behavioral analysis from modern seasons to make educated guesses about
    when historical transactions likely occurred, including:
    - Weekly activity patterns
    - Draft round drop probabilities
    - Position-specific timing (defense streaming, etc.)
    - Team activity levels

    Generates confidence scores and estimation methods for each prediction.
    """
    historical_years = list(range(2011, 2018))
    modern_years = list(range(2019, 2025))

    typer.echo(
        f"🔮 Estimating historical transaction patterns using modern behavioral data..."
    )
    typer.echo("   Applying 2019-2024 patterns to 2011-2017 end-of-season changes...")

    try:
        path = _estimate_historical_transaction_patterns(
            historical_years=historical_years, modern_years=modern_years, out_path=out
        )
    except Exception as e:
        typer.echo(f"❌ Historical pattern estimation failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote estimated historical patterns: {path}")


def _analyze_schedule_based_patterns(
    out_path: str | None,
) -> str:
    """Analyze transaction patterns by regular season vs playoff weeks and estimate historical volumes."""

    # Load modern weekly data
    modern_file = "/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/roster_changes/weekly_changes_2019-2024.csv"
    historical_file = "/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/roster_changes/roster_changes_2011-2017.csv"

    try:
        modern_df = pd.read_csv(modern_file)
        historical_df = pd.read_csv(historical_file)
    except FileNotFoundError as e:
        raise RuntimeError(f"Required data files not found: {e}")

    typer.echo("📅 Analyzing schedule-based transaction patterns...")

    # Define season structures
    season_structures = {
        2019: {"rs_weeks": list(range(1, 14)), "ps_weeks": list(range(14, 17))},
        2020: {"rs_weeks": list(range(1, 14)), "ps_weeks": list(range(14, 17))},
        2021: {"rs_weeks": list(range(1, 15)), "ps_weeks": list(range(15, 18))},
        2022: {"rs_weeks": list(range(1, 15)), "ps_weeks": list(range(15, 18))},
        2023: {"rs_weeks": list(range(1, 15)), "ps_weeks": list(range(15, 18))},
        2024: {"rs_weeks": list(range(1, 15)), "ps_weeks": list(range(15, 18))},
    }

    # Historical schedule (assuming 2011-2018 were 1-13 rs, 14-16 ps)
    historical_structure = {
        "rs_weeks": list(range(1, 14)),
        "ps_weeks": list(range(14, 17)),
    }

    # Analyze modern transaction patterns by phase
    modern_active = modern_df[modern_df["change_type"].isin(["added", "dropped"])]

    season_analysis = {}
    for year, structure in season_structures.items():
        year_data = modern_active[modern_active["season_year"] == year]

        rs_transactions = year_data[year_data["week"].isin(structure["rs_weeks"])]
        ps_transactions = year_data[year_data["week"].isin(structure["ps_weeks"])]

        season_analysis[year] = {
            "total_transactions": len(year_data),
            "rs_transactions": len(rs_transactions),
            "ps_transactions": len(ps_transactions),
            "rs_weeks": len(structure["rs_weeks"]),
            "ps_weeks": len(structure["ps_weeks"]),
            "rs_per_week": len(rs_transactions) / len(structure["rs_weeks"]),
            "ps_per_week": (
                len(ps_transactions) / len(structure["ps_weeks"])
                if structure["ps_weeks"]
                else 0
            ),
            "rs_weekly_pattern": rs_transactions.groupby("week").size().to_dict(),
            "ps_weekly_pattern": ps_transactions.groupby("week").size().to_dict(),
        }

    typer.echo("📊 Calculating transaction rate patterns...")

    # Calculate average transaction rates
    avg_rs_per_week = sum(s["rs_per_week"] for s in season_analysis.values()) / len(
        season_analysis
    )
    avg_ps_per_week = sum(
        s["ps_per_week"] for s in season_analysis.values() if s["ps_per_week"] > 0
    ) / len(season_analysis)

    # Analyze week-by-week patterns within regular season and playoffs
    rs_week_patterns = {}  # Week 1, 2, 3... patterns
    ps_week_patterns = {}  # Playoff week 1, 2, 3... patterns

    for year, analysis in season_analysis.items():
        structure = season_structures[year]

        # Regular season week patterns (normalize to week 1, 2, 3... of regular season)
        for i, week in enumerate(structure["rs_weeks"], 1):
            if i not in rs_week_patterns:
                rs_week_patterns[i] = []
            rs_week_patterns[i].append(analysis["rs_weekly_pattern"].get(week, 0))

        # Playoff week patterns
        for i, week in enumerate(structure["ps_weeks"], 1):
            if i not in ps_week_patterns:
                ps_week_patterns[i] = []
            ps_week_patterns[i].append(analysis["ps_weekly_pattern"].get(week, 0))

    # Average patterns
    avg_rs_week_pattern = {
        week: sum(counts) / len(counts) for week, counts in rs_week_patterns.items()
    }
    avg_ps_week_pattern = {
        week: sum(counts) / len(counts)
        for week, counts in ps_week_patterns.items()
        if counts
    }

    typer.echo("🔮 Estimating historical transaction volumes...")

    # Estimate historical transactions for 2011-2018
    historical_estimates = {}

    # Use the historical roster changes to get actual transaction counts we know happened
    historical_active = historical_df[
        historical_df["change_type"].isin(["added", "dropped"])
    ]
    historical_transactions_per_year = historical_active.groupby("season_year").size()

    for year in range(2011, 2019):
        # Get known transaction count for this year
        known_transactions = historical_transactions_per_year.get(year, 0)

        # Calculate scaling factor (historical vs modern activity level)
        modern_avg_per_year = sum(
            s["total_transactions"] for s in season_analysis.values()
        ) / len(season_analysis)
        if modern_avg_per_year > 0:
            scaling_factor = known_transactions / modern_avg_per_year
        else:
            scaling_factor = (
                0.6  # Default assumption that historical was 60% of modern activity
            )

        # Apply scaling to weekly patterns
        estimated_rs_weeks = {}
        for week_num, avg_transactions in avg_rs_week_pattern.items():
            if week_num <= len(historical_structure["rs_weeks"]):
                estimated_rs_weeks[week_num] = max(
                    1, int(avg_transactions * scaling_factor)
                )

        estimated_ps_weeks = {}
        for week_num, avg_transactions in avg_ps_week_pattern.items():
            if week_num <= len(historical_structure["ps_weeks"]):
                estimated_ps_weeks[week_num] = max(
                    1, int(avg_transactions * scaling_factor)
                )

        historical_estimates[year] = {
            "known_total_transactions": known_transactions,
            "scaling_factor": scaling_factor,
            "estimated_rs_weekly": estimated_rs_weeks,
            "estimated_ps_weekly": estimated_ps_weeks,
            "estimated_rs_total": sum(estimated_rs_weeks.values()),
            "estimated_ps_total": sum(estimated_ps_weeks.values()),
            "estimated_total": sum(estimated_rs_weeks.values())
            + sum(estimated_ps_weeks.values()),
        }

    # Create detailed week-by-week estimates
    detailed_estimates = []
    for year, estimates in historical_estimates.items():
        # Regular season weeks (1-13)
        for week_num, estimated_count in estimates["estimated_rs_weekly"].items():
            actual_week = week_num  # Week 1 = Week 1, etc.
            detailed_estimates.append(
                {
                    "season_year": year,
                    "week": actual_week,
                    "phase": "regular_season",
                    "estimated_transactions": estimated_count,
                    "confidence": (
                        "medium" if week_num <= 10 else "high"
                    ),  # Later RS weeks more predictable
                }
            )

        # Playoff weeks (14-16)
        for week_num, estimated_count in estimates["estimated_ps_weekly"].items():
            actual_week = 13 + week_num  # Playoff week 1 = Week 14, etc.
            detailed_estimates.append(
                {
                    "season_year": year,
                    "week": actual_week,
                    "phase": "playoffs",
                    "estimated_transactions": estimated_count,
                    "confidence": "high",  # Playoff patterns very consistent
                }
            )

    # Convert to DataFrame
    estimates_df = pd.DataFrame(detailed_estimates)

    # Generate output filename
    if not out_path:
        out_path = f"historical_weekly_estimates_2011-2018.csv"

    # Write detailed estimates
    os.makedirs(
        os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True
    )
    estimates_df.to_csv(out_path, index=False)

    # Create comprehensive analysis report
    analysis_path = out_path.replace(".csv", "_analysis.txt")
    with open(analysis_path, "w") as f:
        f.write("RFFL Schedule-Based Transaction Pattern Analysis\\n")
        f.write("=" * 50 + "\\n\\n")

        f.write("MODERN SEASON ANALYSIS (2019-2024):\\n")
        f.write(
            f"Average regular season transactions per week: {avg_rs_per_week:.1f}\\n"
        )
        f.write(f"Average playoff transactions per week: {avg_ps_per_week:.1f}\\n")
        f.write(
            f"Playoff activity is {(avg_ps_per_week/avg_rs_per_week)*100:.0f}% of regular season activity\\n\\n"
        )

        f.write("REGULAR SEASON WEEK PATTERNS (Average):\\n")
        for week, count in sorted(avg_rs_week_pattern.items()):
            f.write(f"Week {week:2d}: {count:.1f} transactions\\n")
        f.write("\\n")

        f.write("PLAYOFF WEEK PATTERNS (Average):\\n")
        for week, count in sorted(avg_ps_week_pattern.items()):
            f.write(f"Playoff Week {week}: {count:.1f} transactions\\n")
        f.write("\\n")

        f.write("HISTORICAL ESTIMATES (2011-2018):\\n")
        total_estimated = sum(
            est["estimated_total"] for est in historical_estimates.values()
        )
        f.write(f"Total estimated historical transactions: {total_estimated}\\n")

        for year, est in historical_estimates.items():
            f.write(f"\\n{year}:\\n")
            f.write(
                f"  Known end-of-season changes: {est['known_total_transactions']}\\n"
            )
            f.write(f"  Estimated weekly activity: {est['estimated_total']}\\n")
            f.write(f"  Regular season: {est['estimated_rs_total']} transactions\\n")
            f.write(f"  Playoffs: {est['estimated_ps_total']} transactions\\n")
            f.write(f"  Scaling factor: {est['scaling_factor']:.2f}\\n")

    return out_path


@app.command("analyze-schedule-patterns")
def cmd_analyze_schedule_patterns(
    out: str = typer.Option(None, help="Output CSV path"),
):
    """Analyze transaction patterns by regular season vs playoff schedule changes.

    Compares modern era schedule patterns:
    - 2019-2020: Weeks 1-13 RS, 14-16 PS
    - 2021-2024: Weeks 1-14 RS, 15-17 PS

    Estimates weekly transaction volumes for historical 2011-2018 seasons
    assuming they followed the 1-13 RS, 14-16 PS structure.

    Provides confidence levels and scaling factors based on known end-of-season data.
    """

    typer.echo(f"📊 Analyzing schedule-based transaction patterns...")
    typer.echo("   Comparing regular season vs playoff activity across eras...")

    try:
        path = _analyze_schedule_based_patterns(out_path=out)
    except Exception as e:
        typer.echo(f"❌ Schedule pattern analysis failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote schedule-based analysis: {path}")


def _create_transaction_matrix(
    out_path: str | None,
) -> str:
    """Create a comprehensive CSV matrix showing transactions per week for ALL years (2011-2024).

    Season Structure:
    - Week 0: Draft → Week 1 transition (all seasons)
    - 2011-2020: Weeks 0-15 (Week 0 + 13 RS + 3 PS = 17 total weeks)
    - 2021-2024: Weeks 0-16 (Week 0 + 14 RS + 3 PS = 18 total weeks)

    Historical years (2011-2018): Estimated based on scaling factors
    Modern years (2019-2024): Actual transaction counts from data
    """

    # Load the modern transaction data
    modern_file = "/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/roster_changes/weekly_changes_2019-2024.csv"

    try:
        modern_df = pd.read_csv(modern_file)
    except FileNotFoundError as e:
        raise RuntimeError(f"Required data files not found: {e}")

    typer.echo("📊 Creating comprehensive transaction matrix (2011-2024)...")

    # Get actual modern transaction data (2019-2024)
    modern_active = modern_df[modern_df["change_type"].isin(["added", "dropped"])]

    # Count actual transactions per year/week (total across all teams)
    modern_totals = (
        modern_active.groupby(["season_year", "week"])
        .size()
        .reset_index(name="total_transactions")
    )

    # Calculate team averages for scaling historical data
    modern_team_avg = (
        modern_active.groupby(["season_year", "week", "team_code"])
        .size()
        .reset_index(name="transactions")
    )
    modern_weekly_avg = (
        modern_team_avg.groupby(["season_year", "week"])["transactions"]
        .mean()
        .reset_index()
    )

    # Historical scaling factors (estimated activity levels vs modern)
    historical_scaling = {
        2011: 0.4,  # 40% of modern activity
        2012: 0.37,
        2013: 0.38,
        2014: 0.42,
        2015: 0.45,
        2016: 0.40,
        2017: 0.43,
        2018: 0.48,  # Closer to modern era
    }

    # Number of teams per year (assuming 12 teams consistently)
    teams_per_year = 12

    # Create comprehensive matrix with all years 2011-2024
    matrix_data = []
    all_week_cols = set()  # Track all week columns we need

    # Historical years (2011-2018) - use estimates with old schedule
    for year in range(2011, 2019):
        year_scaling = historical_scaling[year]
        year_row = {"Year": year}

        # Calculate modern baseline averages across all modern years for scaling
        baseline_patterns = {}
        for modern_year in [2019, 2020, 2021, 2022, 2023, 2024]:
            modern_year_data = modern_weekly_avg[
                modern_weekly_avg["season_year"] == modern_year
            ]

            # Map to historical week structure
            for _, row in modern_year_data.iterrows():
                week_idx = (
                    row["week"] - 1
                )  # Convert to 0-based indexing (Week 0 = draft transition)
                if 0 <= week_idx <= 15:  # Old schedule: Weeks 0-15 (17 total weeks)
                    if week_idx not in baseline_patterns:
                        baseline_patterns[week_idx] = []
                    baseline_patterns[week_idx].append(row["transactions"])

        # Calculate averages for each week across modern years
        avg_patterns = {
            week: sum(values) / len(values)
            for week, values in baseline_patterns.items()
        }

        # Apply historical scaling to create estimates for Weeks 0-15
        for week_idx in range(16):  # Weeks 0-15 (old schedule)
            col_name = f"Week_{week_idx:02d}"
            all_week_cols.add(col_name)
            if week_idx in avg_patterns:
                avg_per_team = avg_patterns[week_idx]
                historical_per_team = avg_per_team * year_scaling
                total_week_transactions = max(
                    1, int(historical_per_team * teams_per_year)
                )
                year_row[col_name] = total_week_transactions
            else:
                year_row[col_name] = 1  # Minimum activity

        matrix_data.append(year_row)

    # Modern years with old schedule (2019-2020) - use actual data
    for year in range(2019, 2021):
        year_row = {"Year": year}
        year_data = modern_totals[modern_totals["season_year"] == year]

        # Initialize weeks 0-15 (old schedule: 16 total weeks)
        for week_idx in range(16):  # Weeks 0-15 (old schedule)
            col_name = f"Week_{week_idx:02d}"
            all_week_cols.add(col_name)
            year_row[col_name] = 0

        # Fill in actual transaction data
        for _, row in year_data.iterrows():
            week_idx = row["week"] - 1  # Convert to 0-based indexing
            if 0 <= week_idx <= 15:  # Old schedule allows up to Week 15
                col_name = f"Week_{week_idx:02d}"
                year_row[col_name] = row["total_transactions"]

        matrix_data.append(year_row)

    # Modern years (2021-2024) - use actual data with new schedule
    for year in range(2021, 2025):
        year_row = {"Year": year}
        year_data = modern_totals[modern_totals["season_year"] == year]

        # Initialize weeks 0-16 (new schedule: 18 total weeks)
        for week_idx in range(17):  # Weeks 0-16 (new schedule)
            col_name = f"Week_{week_idx:02d}"
            all_week_cols.add(col_name)
            year_row[col_name] = 0

        # Fill in actual transaction data
        for _, row in year_data.iterrows():
            week_idx = row["week"] - 1  # Convert to 0-based indexing
            if 0 <= week_idx <= 16:  # New schedule allows up to Week 16
                col_name = f"Week_{week_idx:02d}"
                year_row[col_name] = row["total_transactions"]

        matrix_data.append(year_row)

    # Convert to DataFrame and ensure all week columns exist
    all_week_cols = sorted(list(all_week_cols))
    for row in matrix_data:
        for col in all_week_cols:
            if col not in row:
                row[col] = 0  # Fill missing weeks with 0

    matrix_df = pd.DataFrame(matrix_data)

    # Calculate totals for each row
    week_cols = [col for col in matrix_df.columns if col.startswith("Week_")]
    matrix_df["Year_Total"] = matrix_df[week_cols].sum(axis=1)

    # Add summary statistics
    old_schedule_years = matrix_df[matrix_df["Year"].between(2011, 2020)]  # 2011-2020
    new_schedule_years = matrix_df[matrix_df["Year"].between(2021, 2024)]  # 2021-2024
    historical_years = matrix_df[
        matrix_df["Year"].between(2011, 2018)
    ]  # Historical estimates only
    modern_years = matrix_df[matrix_df["Year"].between(2019, 2024)]  # All modern data

    # Add summary rows
    summary_rows = []

    # Historical averages (2011-2018)
    hist_avg_row = {"Year": "HIST_AVG_2011_2018"}
    for col in week_cols:
        hist_avg_row[col] = (
            int(historical_years[col].mean()) if not historical_years.empty else 0
        )
    hist_avg_row["Year_Total"] = (
        int(historical_years["Year_Total"].mean()) if not historical_years.empty else 0
    )
    summary_rows.append(hist_avg_row)

    # Old schedule averages (2011-2020)
    old_avg_row = {"Year": "OLD_SCHEDULE_AVG_2011_2020"}
    for col in week_cols:
        old_avg_row[col] = (
            int(old_schedule_years[col].mean()) if not old_schedule_years.empty else 0
        )
    old_avg_row["Year_Total"] = (
        int(old_schedule_years["Year_Total"].mean())
        if not old_schedule_years.empty
        else 0
    )
    summary_rows.append(old_avg_row)

    # New schedule averages (2021-2024)
    new_avg_row = {"Year": "NEW_SCHEDULE_AVG_2021_2024"}
    for col in week_cols:
        new_avg_row[col] = (
            int(new_schedule_years[col].mean()) if not new_schedule_years.empty else 0
        )
    new_avg_row["Year_Total"] = (
        int(new_schedule_years["Year_Total"].mean())
        if not new_schedule_years.empty
        else 0
    )
    summary_rows.append(new_avg_row)

    # Modern averages (2019-2024)
    modern_avg_row = {"Year": "MODERN_AVG_2019_2024"}
    for col in week_cols:
        modern_avg_row[col] = (
            int(modern_years[col].mean()) if not modern_years.empty else 0
        )
    modern_avg_row["Year_Total"] = (
        int(modern_years["Year_Total"].mean()) if not modern_years.empty else 0
    )
    summary_rows.append(modern_avg_row)

    # All years average
    all_avg_row = {"Year": "ALL_AVG_2011_2024"}
    for col in week_cols:
        all_avg_row[col] = int(matrix_df[col].mean())
    all_avg_row["Year_Total"] = int(matrix_df["Year_Total"].mean())
    summary_rows.append(all_avg_row)

    # Totals
    total_row = {"Year": "TOTAL_2011_2024"}
    for col in week_cols:
        total_row[col] = int(matrix_df[col].sum())
    total_row["Year_Total"] = int(matrix_df["Year_Total"].sum())
    summary_rows.append(total_row)

    # Combine all data
    final_df = pd.concat([matrix_df, pd.DataFrame(summary_rows)], ignore_index=True)

    # Generate output filename
    if not out_path:
        out_path = "comprehensive_transaction_matrix_2011-2024.csv"

    # Write CSV
    os.makedirs(
        os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True
    )
    final_df.to_csv(out_path, index=False)

    return out_path


@app.command("create-transaction-matrix")
def cmd_create_transaction_matrix(
    out: str = typer.Option(None, help="Output CSV path"),
):
    """Create comprehensive transaction matrix: years as rows, weeks as columns (2011-2024).

    Historical years (2011-2018): Estimated transactions using scaling factors
    Modern years (2019-2024): Actual transaction counts from weekly data

    Matrix format:
    - Rows: Years (2011-2024) plus summary rows
    - Columns: Week_00 through Week_15 (0-based indexing), plus totals
    - Values: Total transactions across all teams for that week/year
    """

    typer.echo(f"📊 Creating transaction matrix (years × weeks)...")
    typer.echo("   Calculating team-level weekly estimates...")

    try:
        path = _create_transaction_matrix(out_path=out)
    except Exception as e:
        typer.echo(f"❌ Transaction matrix creation failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote transaction matrix: {path}")


@app.command("audit-transaction-data")
def cmd_audit_transaction_data(
    out: str = typer.Option(None, help="Output audit report path"),
):
    """Audit transaction data for anomalies and data quality issues.

    Checks for:
    - Teams with zero draft_kept players (potential data processing errors)
    - Unusually high transaction counts per team/week
    - Missing draft data reconciliation
    - Inconsistent team participation across seasons
    """

    typer.echo("🔍 Starting comprehensive transaction data audit...")

    try:
        path = _audit_transaction_data(out_path=out)
    except Exception as e:
        typer.echo(f"❌ Audit failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote audit report: {path}")


def _audit_transaction_data(
    out_path: str | None,
) -> str:
    """Perform comprehensive audit of transaction data quality."""

    # Load transaction and draft data
    weekly_file = "/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/data/roster_changes/weekly_changes_2019-2024.csv"

    try:
        weekly_df = pd.read_csv(weekly_file)
    except FileNotFoundError as e:
        raise RuntimeError(f"Required data files not found: {e}")

    # Load draft data for comparison
    draft_files = {}
    for year in range(2019, 2025):
        draft_file = f"/Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores/build/flat/{year}_draft_snake_canonicals.csv"
        try:
            draft_files[year] = pd.read_csv(draft_file)
        except FileNotFoundError:
            typer.echo(f"⚠️  Warning: Draft file not found for {year}")

    audit_results = []
    audit_results.append("RFFL Transaction Data Audit Report")
    audit_results.append("=" * 50)
    audit_results.append("")

    # Audit 1: Teams with zero draft_kept players per year
    audit_results.append("🔍 AUDIT 1: Teams with zero draft_kept players per year")
    audit_results.append("-" * 50)

    for year in range(2019, 2025):
        year_data = weekly_df[weekly_df["season_year"] == year]
        week1_data = year_data[year_data["week"] == 1]

        # Count draft_kept vs added by team
        draft_kept_counts = (
            week1_data[week1_data["change_type"] == "draft_kept"]
            .groupby("team_code")
            .size()
        )
        added_counts = (
            week1_data[week1_data["change_type"] == "added"].groupby("team_code").size()
        )

        # Find teams with zero draft_kept
        all_teams = set(week1_data["team_code"].unique())
        teams_with_drafts = set(draft_kept_counts.index)
        teams_without_drafts = all_teams - teams_with_drafts

        if teams_without_drafts:
            audit_results.append(f"{year}: Teams with ZERO draft_kept players:")
            for team in sorted(teams_without_drafts):
                adds = added_counts.get(team, 0)
                audit_results.append(f"  - {team}: {adds} added, 0 draft_kept")
        else:
            audit_results.append(f"{year}: ✅ All teams have draft_kept players")

        # Cross-reference with draft data if available
        if year in draft_files:
            draft_teams = set(draft_files[year]["team_code"].unique())
            weekly_teams = set(week1_data["team_code"].unique())
            missing_from_weekly = draft_teams - weekly_teams
            extra_in_weekly = weekly_teams - draft_teams

            if missing_from_weekly:
                audit_results.append(
                    f"  ⚠️  Teams in draft but not in weekly: {missing_from_weekly}"
                )
            if extra_in_weekly:
                audit_results.append(
                    f"  ⚠️  Teams in weekly but not in draft: {extra_in_weekly}"
                )

    audit_results.append("")

    # Audit 2: Unusually high transaction weeks
    audit_results.append("🔍 AUDIT 2: Unusually high transaction weeks")
    audit_results.append("-" * 50)

    # Get transaction counts by year/week
    active_transactions = weekly_df[weekly_df["change_type"].isin(["added", "dropped"])]
    week_totals = (
        active_transactions.groupby(["season_year", "week"])
        .size()
        .reset_index(name="total_transactions")
    )

    # Flag weeks with > 100 transactions as potentially anomalous
    high_weeks = week_totals[week_totals["total_transactions"] > 100]

    if not high_weeks.empty:
        for _, row in high_weeks.iterrows():
            year, week, total = (
                row["season_year"],
                row["week"],
                row["total_transactions"],
            )
            audit_results.append(f"{year} Week {week}: {total} transactions (HIGH)")

            # Break down by team for high weeks
            week_data = active_transactions[
                (active_transactions["season_year"] == year)
                & (active_transactions["week"] == week)
            ]
            team_breakdown = (
                week_data.groupby(["team_code", "change_type"])
                .size()
                .unstack(fill_value=0)
            )

            for team in team_breakdown.index:
                added = (
                    team_breakdown.loc[team, "added"]
                    if "added" in team_breakdown.columns
                    else 0
                )
                dropped = (
                    team_breakdown.loc[team, "dropped"]
                    if "dropped" in team_breakdown.columns
                    else 0
                )
                if added + dropped > 10:  # Flag teams with >10 transactions in a week
                    audit_results.append(
                        f"  - {team}: {added} added, {dropped} dropped"
                    )
    else:
        audit_results.append("✅ No weeks with >100 transactions found")

    audit_results.append("")

    # Audit 3: Team consistency across seasons
    audit_results.append("🔍 AUDIT 3: Team participation consistency")
    audit_results.append("-" * 50)

    all_teams_by_year = {}
    for year in range(2019, 2025):
        year_teams = set(
            weekly_df[weekly_df["season_year"] == year]["team_code"].unique()
        )
        all_teams_by_year[year] = year_teams
        audit_results.append(f"{year}: {len(year_teams)} teams - {sorted(year_teams)}")

    # Find teams that appear/disappear
    all_teams_ever = set()
    for teams in all_teams_by_year.values():
        all_teams_ever.update(teams)

    audit_results.append("")
    audit_results.append("Team participation matrix:")
    for team in sorted(all_teams_ever):
        years_present = []
        for year in range(2019, 2025):
            if team in all_teams_by_year[year]:
                years_present.append(str(year))
            else:
                years_present.append("----")
        audit_results.append(f"{team}: {' '.join(years_present)}")

    audit_results.append("")

    # Audit 4: Data quality metrics
    audit_results.append("🔍 AUDIT 4: Data quality metrics")
    audit_results.append("-" * 50)

    total_records = len(weekly_df)
    audit_results.append(f"Total records: {total_records:,}")

    # Check for missing data
    missing_players = weekly_df["player_name"].isna().sum()
    missing_teams = weekly_df["team_code"].isna().sum()
    missing_weeks = weekly_df["week"].isna().sum()

    audit_results.append(f"Missing player names: {missing_players}")
    audit_results.append(f"Missing team codes: {missing_teams}")
    audit_results.append(f"Missing week numbers: {missing_weeks}")

    # Transaction type distribution
    change_type_counts = weekly_df["change_type"].value_counts()
    audit_results.append("")
    audit_results.append("Transaction type distribution:")
    for change_type, count in change_type_counts.items():
        pct = (count / total_records) * 100
        audit_results.append(f"  {change_type}: {count:,} ({pct:.1f}%)")

    audit_results.append("")

    # Audit 5: Recommendations
    audit_results.append("🔍 AUDIT 5: Recommendations")
    audit_results.append("-" * 50)

    recommendations = []

    # Check for draft reconciliation issues
    zero_draft_years = []
    for year in range(2019, 2025):
        year_data = weekly_df[weekly_df["season_year"] == year]
        week1_data = year_data[year_data["week"] == 1]
        teams_without_drafts = set(week1_data["team_code"].unique()) - set(
            week1_data[week1_data["change_type"] == "draft_kept"]["team_code"].unique()
        )
        if teams_without_drafts:
            zero_draft_years.append(year)

    if zero_draft_years:
        recommendations.append(
            f"⚠️  CRITICAL: Fix draft reconciliation for years: {zero_draft_years}"
        )
        recommendations.append(
            "   - Re-process weekly data to properly mark drafted players as 'draft_kept'"
        )
        recommendations.append(
            "   - This affects transaction matrix accuracy significantly"
        )

    if not high_weeks.empty:
        recommendations.append(
            f"⚠️  REVIEW: Investigate {len(high_weeks)} weeks with >100 transactions"
        )
        recommendations.append(
            "   - Verify if high activity is legitimate or data processing error"
        )

    recommendations.append("✅ Consider implementing automated data validation checks")
    recommendations.append(
        "✅ Add draft-roster reconciliation validation to data pipeline"
    )

    for rec in recommendations:
        audit_results.append(rec)

    # Write audit report
    if not out_path:
        out_path = "transaction_data_audit_report.txt"

    with open(out_path, "w") as f:
        f.write("\n".join(audit_results))

    # Print summary to console
    typer.echo("")
    typer.echo("📋 AUDIT SUMMARY:")
    if zero_draft_years:
        typer.echo(
            f"❌ CRITICAL: {len(zero_draft_years)} years with draft reconciliation issues"
        )
    if not high_weeks.empty:
        typer.echo(
            f"⚠️  WARNING: {len(high_weeks)} weeks with unusually high transaction counts"
        )
    typer.echo(f"📊 Total records audited: {total_records:,}")
    typer.echo(f"🏈 Teams tracked: {len(all_teams_ever)}")
    typer.echo(f"📅 Years covered: {2019}-{2024}")

    return out_path


if __name__ == "__main__":
    app()
