import math
import pandas as pd

from rffl_boxscores.cli import _norm_slot, _f, _validate_rffl_lineup


def test_norm_slot_basic():
    assert _norm_slot("QB", None) == "QB"
    assert _norm_slot("rb/wr/te", None) == "FLEX"
    assert _norm_slot("dst", None) == "D/ST"
    assert _norm_slot("be", None) == "Bench"
    assert _norm_slot(None, "WR") == "WR"


def test__f_coercion():
    assert _f(1) == 1.0
    assert _f(1.25) == 1.25
    assert _f(None) == 0.0
    assert _f(float("nan")) == 0.0
    assert _f("3.2") == 3.2
    assert _f("bad", default=7.0) == 7.0


def _mk_lineup(rows):
    return pd.DataFrame(rows, columns=[
        "slot", "player_name", "position", "projected_points", "actual_points"
    ])


def test_validate_rffl_lineup_valid():
    starters = _mk_lineup([
        ("QB", "QB1", "QB", 10, 12),
        ("RB", "RB1", "RB", 10, 10),
        ("RB", "RB2", "RB", 10, 9),
        ("WR", "WR1", "WR", 10, 8),
        ("WR", "WR2", "WR", 10, 7),
        ("TE", "TE1", "TE", 10, 6),
        ("FLEX", "RB3", "RB", 8, 5),
        ("D/ST", "DST1", "D/ST", 5, 5),
        ("K", "K1", "K", 5, 5),
    ])
    result = _validate_rffl_lineup(starters)
    assert result["is_valid"] is True
    assert result["total_issues"] == 0


def test_validate_rffl_lineup_issues():
    starters = _mk_lineup([
        ("QB", "QB1", "QB", 10, 12),
        ("RB", "RB1", "RB", 10, 10),
        ("WR", "WR1", "WR", 10, 8),
        ("WR", "WR2", "WR", 10, 7),
        ("TE", "TE1", "TE", 10, 6),
        ("FLEX", "QB2", "QB", 8, 5),  # invalid flex
        ("D/ST", "DST1", "D/ST", 5, 5),
        ("K", "K1", "K", 5, 5),
        ("K", "K2", "K", 5, 5),  # wrong slot count
    ])
    result = _validate_rffl_lineup(starters)
    assert result["is_valid"] is False
    assert result["total_issues"] > 0

