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


if __name__ == "__main__":
    app()
