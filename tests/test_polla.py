"""
test_polla.py
=============
Permanent test suite for the polla engine. Run from the repo root:

    python tests/test_polla.py

Plain asserts, no pytest. Never touches the real data/ files: the integration
tests build synthetic CSVs in a temp directory and point compare_strategies.DATA
at it.

Covers:
  1. The 5/2/2/1 scoring rule on hand-verified cases (group + knockout).
  2. The three-strategy comparison end-to-end on the two rehearsal matches with
     hypothetical results, asserting exact totals and match counts.
  3. The Codere input guard: decimal odds mistakenly entered in the p_* columns
     must raise ValueError.
"""

import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

import compare_strategies
from polla_model import score_points

POLY_HEADER = ("capture_datetime,match_datetime,stage,match_id,home_team,"
               "away_team,p_home,p_draw,p_away,ml_volume_usd,ou_line,p_over,"
               "p_under,totals_volume_usd,submitted_home,submitted_away,"
               "actual_home,actual_away,notes")
CODERE_HEADER = ("capture_datetime,match_datetime,stage,match_id,home_team,"
                 "away_team,p_home,p_draw,p_away,ou_line,p_over,p_under,"
                 "cs_pred_home,cs_pred_away,cs_pred_odds,notes")


def test_scoring_rule():
    # (pred, actual, knockout, expected)
    cases = [
        ((1, 0), (2, 1), False, 6),   # result + goal diff
        ((1, 0), (1, 1), False, 2),   # home goals only
        ((1, 1), (1, 1), False, 10),  # exact score: all four components
        ((2, 0), (2, 1), False, 7),   # result + home goals
        ((1, 0), (2, 1), True, 12),   # knockout doubles the 6
    ]
    for pred, actual, ko, expected in cases:
        got = score_points(pred, actual, knockout=ko)
        assert got == expected, (
            f"score_points({pred}, {actual}, knockout={ko}) = {got}, "
            f"expected {expected}")
    print("  [1] scoring rule: 5 hand-verified cases pass")


def _write(path, header, rows):
    with open(path, "w") as f:
        f.write(header + "\n")
        for row in rows:
            f.write(row + "\n")


def _poly_rows():
    return [
        "2026-06-08T19:40:00-04:00,2026-06-11T15:00:00-04:00,group,A1-MEX-RSA,"
        "Mexico,South Africa,0.69,0.21,0.11,536000,2.5,0.44,0.57,21300,,,"
        "2,1,test",
        "2026-06-08T19:45:00-04:00,2026-06-11T22:00:00-04:00,group,A2-KOR-CZE,"
        "Korea Republic,Czechia,0.37,0.32,0.33,221000,2.5,0.42,0.59,11400,,,"
        "1,1,test",
    ]


def test_three_strategy_integration():
    codere_rows = [
        "2026-06-08T19:50:00-04:00,2026-06-11T15:00:00-04:00,group,A1-MEX-RSA,"
        "Mexico,South Africa,0.7143,0.2273,0.1111,2.5,0.4762,0.6061,1,0,5.00,test",
        "2026-06-08T19:55:00-04:00,2026-06-11T22:00:00-04:00,group,A2-KOR-CZE,"
        "Korea Republic,Czechia,0.3774,0.3077,0.3636,2.5,0.4545,0.6173,1,1,5.25,test",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "match_odds_polymarket.csv"), POLY_HEADER,
               _poly_rows())
        _write(os.path.join(tmp, "match_odds_codere.csv"), CODERE_HEADER,
               codere_rows)
        old_data = compare_strategies.DATA
        compare_strategies.DATA = tmp
        try:
            rows, totals, counts = compare_strategies.compare()
        finally:
            compare_strategies.DATA = old_data

    assert len(rows) == 2, f"expected 2 scored matches, got {len(rows)}"
    expected_totals = {"poly_model": 8, "codere_model": 8, "codere_exact": 16}
    expected_counts = {"poly_model": 2, "codere_model": 2, "codere_exact": 2}
    assert totals == expected_totals, (
        f"totals mismatch: got {totals}, expected {expected_totals}")
    assert counts == expected_counts, (
        f"counts mismatch: got {counts}, expected {expected_counts}")
    print("  [2] three-strategy integration: totals poly=8 codere=8 exact=16, "
          "2 matches each")


def test_guard_rejects_decimal_odds():
    # A1 Codere row wrongly carries decimal odds (1.40/4.40/9.00) in p_* columns.
    bad_codere_rows = [
        "2026-06-08T19:50:00-04:00,2026-06-11T15:00:00-04:00,group,A1-MEX-RSA,"
        "Mexico,South Africa,1.40,4.40,9.00,2.5,0.4762,0.6061,1,0,5.00,test",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "match_odds_polymarket.csv"), POLY_HEADER,
               _poly_rows())
        _write(os.path.join(tmp, "match_odds_codere.csv"), CODERE_HEADER,
               bad_codere_rows)
        old_data = compare_strategies.DATA
        compare_strategies.DATA = tmp
        raised = None
        try:
            compare_strategies.compare()
        except ValueError as e:
            raised = e
        finally:
            compare_strategies.DATA = old_data

    assert raised is not None, (
        "compare() accepted decimal odds in the Codere p_* columns — the "
        "input guard did NOT fire")
    assert "implied probabilities" in str(raised), (
        f"guard raised, but message lacks 'implied probabilities': {raised}")
    print("  [3] input guard: decimal odds in p_* columns raise ValueError")


if __name__ == "__main__":
    test_scoring_rule()
    test_three_strategy_integration()
    test_guard_rejects_decimal_odds()
    print("ALL TESTS PASS")
