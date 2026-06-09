"""
compare_strategies.py
=====================
End-of-tournament comparison of the three prediction strategies, scored against
actual results under the pool's rule. Answers: "which approach would have placed
best in la polla?"

The three strategies
--------------------
  1. poly_model     : the Poisson/Dixon-Coles engine fed by POLYMARKET 1X2 + O/U
                      (this is the one actually submitted — the primary)
  2. codere_model   : the same engine fed by CODERE 1X2 + O/U (the shadow source)
  3. codere_exact   : CODERE's own correct-score market, read directly (the most
                      likely scoreline Codere prices), with NO model in between

Each match's predicted scoreline is scored against the real 90' result using the
identical 5/2/2/1 rule (doubled in knockouts). Strategy totals are then compared.

Inputs
------
  data/match_odds_polymarket.csv   (carries the actual results)
  data/match_odds_codere.csv       (carries Codere odds + Codere exact-score pick)
Joined on match_id.

Usage
-----
  python compare_strategies.py            # scores all matches with a result logged
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from polla_model import pick_from_raw, score_points

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def _is_knockout(stage: str) -> bool:
    return str(stage).strip().lower() not in ("group", "")


def _has_result(row) -> bool:
    return pd.notna(row.get("actual_home")) and pd.notna(row.get("actual_away"))


@dataclass
class MatchComparison:
    match_id: str
    label: str
    actual: tuple[int, int]
    poly_pred: tuple[int, int] | None
    codere_pred: tuple[int, int] | None
    cexact_pred: tuple[int, int] | None
    poly_pts: int | None
    codere_pts: int | None
    cexact_pts: int | None


def compare() -> tuple[list[MatchComparison], dict[str, int]]:
    poly = pd.read_csv(os.path.join(DATA, "match_odds_polymarket.csv"))
    try:
        cod = pd.read_csv(os.path.join(DATA, "match_odds_codere.csv"))
    except Exception:
        cod = pd.DataFrame()
    cod_by_id = {r["match_id"]: r for _, r in cod.iterrows()} if len(cod) else {}

    rows: list[MatchComparison] = []
    totals = {"poly_model": 0, "codere_model": 0, "codere_exact": 0}

    for _, r in poly.iterrows():
        if not _has_result(r):
            continue  # only score matches that have been played
        ko = _is_knockout(r["stage"])
        actual = (int(r["actual_home"]), int(r["actual_away"]))
        label = f"{r['home_team']} v {r['away_team']}"

        # --- Strategy 1: model on Polymarket ---
        rp = pick_from_raw(r["p_home"], r["p_draw"], r["p_away"],
                           ou_line=r.get("ou_line"), p_over_raw=r.get("p_over"),
                           p_under_raw=r.get("p_under"), knockout=ko)
        poly_pred = rp.best_pred
        poly_pts = score_points(poly_pred, actual, knockout=ko)
        totals["poly_model"] += poly_pts

        # --- Strategies 2 & 3: require a matching Codere row ---
        codere_pred = cexact_pred = None
        codere_pts = cexact_pts = None
        cr = cod_by_id.get(r["match_id"])
        if cr is not None:
            if pd.notna(cr.get("p_home")):
                rc = pick_from_raw(cr["p_home"], cr["p_draw"], cr["p_away"],
                                   ou_line=cr.get("ou_line"), p_over_raw=cr.get("p_over"),
                                   p_under_raw=cr.get("p_under"), knockout=ko)
                codere_pred = rc.best_pred
                codere_pts = score_points(codere_pred, actual, knockout=ko)
                totals["codere_model"] += codere_pts
            if pd.notna(cr.get("cs_pred_home")) and pd.notna(cr.get("cs_pred_away")):
                cexact_pred = (int(cr["cs_pred_home"]), int(cr["cs_pred_away"]))
                cexact_pts = score_points(cexact_pred, actual, knockout=ko)
                totals["codere_exact"] += cexact_pts

        rows.append(MatchComparison(
            match_id=r["match_id"], label=label, actual=actual,
            poly_pred=poly_pred, codere_pred=codere_pred, cexact_pred=cexact_pred,
            poly_pts=poly_pts, codere_pts=codere_pts, cexact_pts=cexact_pts,
        ))
    return rows, totals


def _fmt(pred, pts):
    if pred is None:
        return "    —    "
    return f"{pred[0]}-{pred[1]} ({pts:>2})"


if __name__ == "__main__":
    rows, totals = compare()
    if not rows:
        print("No played matches logged yet (fill actual_home / actual_away "
              "in match_odds_polymarket.csv after each match).")
    else:
        print(f"{'Match':<26}{'Actual':>8}   {'Poly-model':>12}{'Codere-model':>14}{'Codere-exact':>14}")
        print("-" * 88)
        for m in rows:
            print(f"{m.label:<26}{m.actual[0]}-{m.actual[1]:>1}     "
                  f"{_fmt(m.poly_pred, m.poly_pts):>12}{_fmt(m.codere_pred, m.codere_pts):>14}"
                  f"{_fmt(m.cexact_pred, m.cexact_pts):>14}")
        print("-" * 88)
        print(f"{'TOTAL POINTS':<26}{'':>8}   "
              f"{totals['poly_model']:>12}{totals['codere_model']:>14}{totals['codere_exact']:>14}")
        print("\nStrategy ranking:")
        for name, pts in sorted(totals.items(), key=lambda x: -x[1]):
            print(f"  {name:<16} {pts} pts")
