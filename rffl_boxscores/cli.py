# SPDX-License-Identifier: MIT
# rffl_boxscores/cli.py
from __future__ import annotations
import os
import math
import csv
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Iterable, Tuple
import pandas as pd
import typer
from espn_api.football import League
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

app = typer.Typer(add_completion=False, help="RFFL clean exporter + validator")

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
    "K": 1
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
    for attr in ['abbrev', 'team_abbrev', 'abbreviation', 'team_id', 'name']:
        if hasattr(team, attr):
            value = getattr(team, attr)
            if value and isinstance(value, str):
                return value
    # Fallback to team name if no abbreviation found
    return getattr(team, 'name', 'Unknown')


def _validate_rffl_lineup(starters_df: pd.DataFrame) -> Dict[str, Any]:
    """Validate RFFL lineup compliance and return issues found."""
    issues = []
    
    # Count starters by slot
    slot_counts = starters_df['slot'].value_counts().to_dict()
    
    # Check each required position
    for position, required_count in RFFL_LINEUP_REQUIREMENTS.items():
        actual_count = slot_counts.get(position, 0)
        if actual_count != required_count:
            issues.append({
                'type': 'count_mismatch',
                'position': position,
                'required': required_count,
                'actual': actual_count,
                'description': f"Expected {required_count} {position}, found {actual_count}"
            })
    
    # Check FLEX eligibility
    flex_players = starters_df[starters_df['slot'] == 'FLEX']
    for _, player in flex_players.iterrows():
        player_position = player['position']
        if player_position not in FLEX_ELIGIBLE_POSITIONS:
            issues.append({
                'type': 'flex_ineligible',
                'position': player_position,
                'player': player['player_name'],
                'description': f"FLEX player {player['player_name']} has position {player_position} (not RB/WR/TE)"
            })
    
    # Check for duplicate players
    player_counts = starters_df['player_name'].value_counts()
    duplicates = player_counts[player_counts > 1]
    for player, count in duplicates.items():
        issues.append({
            'type': 'duplicate_player',
            'player': player,
            'count': count,
            'description': f"Player {player} appears {count} times in starters"
        })
    
    # Check for invalid positions in specific slots
    for _, player in starters_df.iterrows():
        slot = player['slot']
        position = player['position']
        
        # QB slot should only have QB position
        if slot == 'QB' and position != 'QB':
            issues.append({
                'type': 'invalid_position_in_slot',
                'slot': slot,
                'position': position,
                'player': player['player_name'],
                'description': f"QB slot contains {position} player {player['player_name']}"
            })
        
        # K slot should only have K position
        if slot == 'K' and position != 'K':
            issues.append({
                'type': 'invalid_position_in_slot',
                'slot': slot,
                'position': position,
                'player': player['player_name'],
                'description': f"K slot contains {position} player {player['player_name']}"
            })
        
        # D/ST slot should only have D/ST position
        if slot == 'D/ST' and position != 'D/ST':
            issues.append({
                'type': 'invalid_position_in_slot',
                'slot': slot,
                'position': position,
                'player': player['player_name'],
                'description': f"D/ST slot contains {position} player {player['player_name']}"
            })
    
    return {
        'is_valid': len(issues) == 0,
        'issues': issues,
        'total_issues': len(issues)
    }


@dataclass
class Row:
    week: int
    matchup: int
    team_abbrev: str
    team_proj_total: float
    team_actual_total: float
    slot: str
    slot_type: str
    player_name: str
    position: str | None
    injured: bool | None
    injury_status: str | None
    bye_week: bool | None
    projected_points: float
    actual_points: float


def _export(
    league_id: int,
    year: int,
    espn_s2: str | None,
    swid: str | None,
    start_week: int | None,
    end_week: int | None,
    out_path: str,
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
        for week, boxscores in _iter_weeks(lg, start_week, end_week):
            for m_idx, bs in enumerate(boxscores, start=1):
                for side in ("home", "away"):
                    team = getattr(bs, f"{side}_team", None)
                    lineup = getattr(bs, f"{side}_lineup", None) or []
                    if not team:
                        continue

                    # Build starter list (we round per-player first, then sum -> totals match rows exactly)
                    starters = []
                    stamped = []
                    for bp in lineup:
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
                            "position": getattr(bp, "position", None),
                            "injured": getattr(bp, "injured", False),
                            "injury_status": getattr(bp, "injuryStatus", None)
                            or getattr(bp, "injury_status", "ACTIVE"),
                            "bye_week": getattr(bp, "on_bye_week", False),
                            "projected_points": proj,
                            "actual_points": act,
                        }
                        stamped.append(row)
                        if row["slot_type"] == "starters":
                            starters.append(row)

                    team_proj = round(sum(r["projected_points"] for r in starters), 2)
                    team_act = round(sum(r["actual_points"] for r in starters), 2)

                    for r in stamped:
                        rows.append(
                            Row(
                                week=week,
                                matchup=m_idx,
                                team_abbrev=_get_team_abbrev(team),
                                team_proj_total=team_proj,
                                team_actual_total=team_act,
                                **r,
                            )
                        )
    except Exception as e:
        raise RuntimeError(
            f"Failed while fetching box scores. Consider checking weeks or cookies. Error: {e}"
        ) from e

    out = out_path or f"validated_boxscores_{year}.csv"
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
    espn_s2: str = typer.Option(None, help="Cookie (private leagues). Falls back to $ESPN_S2"),
    swid: str = typer.Option(None, help="Cookie (private leagues). Falls back to $SWID"),
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
        )
    except Exception as e:
        typer.echo(f"❌ Export failed: {e}")
        raise typer.Exit(1)

    typer.echo(f"✅ Wrote {path}")


@app.command("validate")
def cmd_validate(
    csv_path: str = typer.Argument(..., help="validated_boxscores_YYYY.csv"),
    tolerance: float = typer.Option(0.0, help="Allowed |proj_sum - team_proj_total| (e.g., 0.02)"),
):
    """Validate exported boxscore data for consistency and completeness."""
    df = pd.read_csv(csv_path)
    starters = df[df["slot_type"] == "starters"].copy()
    agg = starters.groupby(["week", "matchup", "team_abbrev"], as_index=False).agg(
        team_proj_total=("team_proj_total", "first"),
        team_actual_total=("team_actual_total", "first"),
        starters_proj_sum=("projected_points", "sum"),
        starters_actual_sum=("actual_points", "sum"),
        starter_count=("slot", "count"),
        slots_list=("slot", lambda s: ",".join(sorted(s))),
    )
    agg["proj_diff"] = (agg["starters_proj_sum"] - agg["team_proj_total"]).round(2)
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
    
    for (week, matchup, team), lineup_df in starters.groupby(["week", "matchup", "team_abbrev"]):
        total_lineups += 1
        validation = _validate_rffl_lineup(lineup_df)
        
        if validation['is_valid']:
            valid_lineups += 1
        else:
            for issue in validation['issues']:
                lineup_issues.append({
                    'week': week,
                    'matchup': matchup,
                    'team_abbrev': team,
                    'issue_type': issue['type'],
                    'description': issue['description'],
                    **{k: v for k, v in issue.items() if k not in ['type', 'description']}
                })
    
    # Print summary
    typer.echo(f"RFFL Lineup Validation Report")
    typer.echo(f"=" * 50)
    typer.echo(f"Total lineups checked: {total_lineups}")
    typer.echo(f"✅ Valid lineups: {valid_lineups}")
    typer.echo(f"❌ Invalid lineups: {total_lineups - valid_lineups}")
    typer.echo(f"Total issues found: {len(lineup_issues)}")
    
    if lineup_issues:
        typer.echo(f"\nIssues by type:")
        issue_types = {}
        for issue in lineup_issues:
            issue_type = issue['issue_type']
            issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
        
        for issue_type, count in sorted(issue_types.items()):
            typer.echo(f"  {issue_type}: {count}")
        
        # Write detailed report
        report_path = out or os.path.splitext(csv_path)[0] + "_lineup_validation_report.csv"
        pd.DataFrame(lineup_issues).to_csv(report_path, index=False)
        typer.echo(f"\n📄 Detailed report written to: {report_path}")
        
        # Show first few issues
        typer.echo(f"\nFirst 5 issues:")
        for i, issue in enumerate(lineup_issues[:5]):
            typer.echo(f"  {i+1}. Week {issue['week']} Matchup {issue['matchup']} {issue['team_abbrev']}: {issue['description']}")
    else:
        typer.echo(f"\n🎉 All lineups are RFFL compliant!")


if __name__ == "__main__":
    app()
