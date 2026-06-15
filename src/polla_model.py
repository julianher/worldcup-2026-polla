"""
polla_model.py
==============
Core engine for the World Cup 2026 prediction-pool ("polla") project.

Pipeline
--------
    market odds  ->  de-vig (Shin)  ->  solve Poisson lambdas
                 ->  Dixon-Coles score matrix  ->  optimal scoreline
                 ->  score under the pool's rule

The thesis of the project is NOT that we beat the market. It is that the
market's implied probabilities are the best available estimator, and that
applying them systematically to a tournament with a *specific scoring rule*
yields a competitive edge over participants who guess. This module is the
machinery that turns market odds into point-maximizing scoreline picks.

Scoring rule (Pasion de Gol / Coempopular pool)
-----------------------------------------------
Per match, the four components are independent and additive:
    - correct result type (1X2)         : 5 pts (group)  / 10 pts (knockout)
    - correct home goals (exact)        : 2 pts (group)  /  4 pts (knockout)
    - correct away goals (exact)        : 2 pts (group)  /  4 pts (knockout)
    - correct goal difference (margin)  : 1 pt  (group)  /  2 pts (knockout)
Maximum 10 pts (group) / 20 pts (knockout). A nailed exact score gives all four.

The goal-difference component is the ABSOLUTE margin (sign-agnostic): predicting a
1-goal margin earns the point on any 1-goal result, even if the wrong team wins
(e.g. predicting 0-1 scores the goal-diff point on a 1-0 result). This matches the
Pasion de Gol platform's scoring.

Only 90' + referee stoppage time counts (no extra time, no penalties).

Author: Julian (portfolio project)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq, minimize


# ---------------------------------------------------------------------------
# 1. Odds -> probabilities (de-vigging)
# ---------------------------------------------------------------------------

def implied_from_decimal(decimal_odds: float) -> float:
    """Raw implied probability from a decimal odd (1/odds). Includes the vig."""
    return 1.0 / decimal_odds


def devig_proportional(raw_probs: np.ndarray) -> np.ndarray:
    """
    Simplest de-vig: divide each raw probability by their sum so they total 1.
    Fine for low-margin markets (e.g. Polymarket, where prices already ~= prob).
    """
    raw = np.asarray(raw_probs, dtype=float)
    return raw / raw.sum()


def devig_shin(raw_probs: np.ndarray) -> np.ndarray:
    """
    Shin (1992,1993) de-vig. Models the booksum as inflated by a proportion z
    of insider/informed money and backs out the 'fair' probabilities. For an
    n-outcome book with raw (vig-loaded) probabilities pi summing to B>1, the
    Shin probabilities are:

        p_i = ( sqrt( z^2 + 4(1-z) * pi_i^2 / B ) - z ) / ( 2(1-z) )

    where z in [0,1) solves sum_i p_i = 1. Shown by Strumbelj (2014) to give
    better-calibrated probabilities (lower RPS) than proportional normalization
    for traditional bookmakers. For near-zero-vig markets z -> 0 and Shin
    collapses to the proportional result, so it is safe to use everywhere.

    Reference: Strumbelj, E. (2014). "On determining probability forecasts from
    betting odds." International Journal of Forecasting 30(4).
    """
    pi = np.asarray(raw_probs, dtype=float)
    B = pi.sum()
    if B <= 1.0 + 1e-9:
        # No (or negative) overround -> nothing to strip; just normalize.
        return pi / B

    def shin_probs(z: float) -> np.ndarray:
        return (np.sqrt(z**2 + 4.0 * (1.0 - z) * pi**2 / B) - z) / (2.0 * (1.0 - z))

    def constraint(z: float) -> float:
        return shin_probs(z).sum() - 1.0

    # constraint is monotain in z on (0, 1); bracket and solve.
    lo, hi = 1e-9, 1.0 - 1e-9
    if constraint(lo) * constraint(hi) > 0:
        # Fallback if no sign change (degenerate); use proportional.
        return pi / B
    z_star = brentq(constraint, lo, hi, xtol=1e-12)
    p = shin_probs(z_star)
    return p / p.sum()  # tidy up tiny numerical drift


# ---------------------------------------------------------------------------
# 2. Poisson / Dixon-Coles score matrix
# ---------------------------------------------------------------------------

def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def _dc_tau(i: int, j: int, lam_h: float, lam_a: float, rho: float) -> float:
    """Dixon-Coles low-score correction factor for cells (0,0),(0,1),(1,0),(1,1)."""
    if i == 0 and j == 0:
        return 1.0 - lam_h * lam_a * rho
    if i == 0 and j == 1:
        return 1.0 + lam_h * rho
    if i == 1 and j == 0:
        return 1.0 + lam_a * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lam_h: float, lam_a: float, rho: float = -0.10,
                 max_goals: int = 10) -> np.ndarray:
    """
    Joint probability matrix M[i, j] = P(home scores i, away scores j),
    using independent Poisson marginals with the Dixon-Coles low-score
    correction (rho), renormalized to sum to 1.

    rho is the DC dependence parameter (typically -0.03 to -0.15). It lifts the
    probability of 0-0 and 1-1 and trims 1-0 / 0-1, correcting the well-known
    underestimation of low draws by the independent Poisson model.
    Reference: Dixon & Coles (1997), Applied Statistics 46(2).
    """
    n = max_goals + 1
    M = np.empty((n, n), dtype=float)
    for i in range(n):
        pi_h = _poisson_pmf(i, lam_h)
        for j in range(n):
            M[i, j] = _dc_tau(i, j, lam_h, lam_a, rho) * pi_h * _poisson_pmf(j, lam_a)
    return M / M.sum()


def outcome_probs(M: np.ndarray) -> tuple[float, float, float]:
    """Return (P(home win), P(draw), P(away win)) from a score matrix."""
    n = M.shape[0]
    p_home = sum(M[i, j] for i in range(n) for j in range(n) if i > j)
    p_draw = sum(M[i, i] for i in range(n))
    p_away = sum(M[i, j] for i in range(n) for j in range(n) if i < j)
    return p_home, p_draw, p_away


def prob_over(M: np.ndarray, line: float) -> float:
    """P(total goals > line). Use a .5 line (e.g. 2.5, 3.5) to avoid pushes."""
    n = M.shape[0]
    return sum(M[i, j] for i in range(n) for j in range(n) if (i + j) > line)


# ---------------------------------------------------------------------------
# 3. Solve Poisson lambdas from market-implied probabilities
# ---------------------------------------------------------------------------

@dataclass
class MarketInputs:
    """De-vigged market probabilities used to calibrate the model."""
    p_home: float          # P(home win)
    p_draw: float          # P(draw)
    p_away: float          # P(away win)
    ou_line: float | None = None   # over/under line, e.g. 2.5 or 3.5
    p_over: float | None = None    # de-vigged P(total > ou_line)


def solve_lambdas(mkt: MarketInputs, rho: float = -0.10,
                  w_result: float = 1.0, w_over: float = 1.0) -> tuple[float, float]:
    """
    Find (lam_home, lam_away) so the Dixon-Coles model reproduces the market's
    1X2 probabilities and (if provided) the over/under probability.

    Solved as a small weighted least-squares fit. The 1X2 contributes the
    balance (who is favored) and the over/under contributes the total goals;
    together they pin down both lambdas. If no over/under is given, the fit
    uses only the 1X2 (still identifiable, but the total-goals level is less
    constrained, so passing an over/under is recommended).
    """
    target = np.array([mkt.p_home, mkt.p_draw, mkt.p_away], dtype=float)

    def objective(params: np.ndarray) -> float:
        lam_h, lam_a = params
        if lam_h <= 0 or lam_a <= 0:
            return 1e6
        M = score_matrix(lam_h, lam_a, rho=rho)
        ph, pd, pa = outcome_probs(M)
        err = w_result * float(np.sum((np.array([ph, pd, pa]) - target) ** 2))
        if mkt.ou_line is not None and mkt.p_over is not None:
            err += w_over * (prob_over(M, mkt.ou_line) - mkt.p_over) ** 2
        return err

    # Reasonable starting point: total ~2.6 goals, split by who's favored.
    tilt = (mkt.p_home - mkt.p_away)
    x0 = np.array([1.3 + tilt, 1.3 - tilt])
    x0 = np.clip(x0, 0.2, 3.5)

    res = minimize(objective, x0, method="Nelder-Mead",
                   options={"xatol": 1e-6, "fatol": 1e-10, "maxiter": 5000})
    lam_h, lam_a = float(res.x[0]), float(res.x[1])
    return lam_h, lam_a


# ---------------------------------------------------------------------------
# 4. Scoring rule + optimal scoreline
# ---------------------------------------------------------------------------

def score_points(pred: tuple[int, int], actual: tuple[int, int],
                 knockout: bool = False) -> int:
    """Points for a single prediction under the pool's 5/2/2/1 rule."""
    ph, pa = pred
    ah, aa = actual
    mult = 2 if knockout else 1
    pts = 0
    sign_pred = (ph > pa) - (ph < pa)
    sign_act = (ah > aa) - (ah < aa)
    if sign_pred == sign_act:      # correct 1X2
        pts += 5
    if ph == ah:                   # correct home goals
        pts += 2
    if pa == aa:                   # correct away goals
        pts += 2
    if abs(ph - pa) == abs(ah - aa):  # correct goal difference (absolute margin)
        pts += 1
    return pts * mult


def expected_points(pred: tuple[int, int], M: np.ndarray,
                    knockout: bool = False) -> float:
    """E[points] of predicting `pred`, integrating over the score matrix M."""
    n = M.shape[0]
    return sum(M[i, j] * score_points(pred, (i, j), knockout)
               for i in range(n) for j in range(n))


@dataclass
class ScorelineResult:
    lam_home: float
    lam_away: float
    rho: float
    p_home: float
    p_draw: float
    p_away: float
    best_pred: tuple[int, int]
    best_ev: float
    top_alternatives: list = field(default_factory=list)  # [(pred, ev, p_exact), ...]
    knockout: bool = False


def optimal_scoreline(mkt: MarketInputs, rho: float = -0.10,
                      knockout: bool = False, search_max: int = 6,
                      n_alternatives: int = 5) -> ScorelineResult:
    """
    Full pipeline for one match: solve lambdas, build the DC matrix, and pick
    the scoreline that maximizes expected points under the pool's rule.
    Returns the optimum plus the top alternatives for transparency.
    """
    lam_h, lam_a = solve_lambdas(mkt, rho=rho)
    M = score_matrix(lam_h, lam_a, rho=rho)
    ph, pd, pa = outcome_probs(M)

    candidates = []
    for i in range(search_max + 1):
        for j in range(search_max + 1):
            ev = expected_points((i, j), M, knockout=knockout)
            candidates.append(((i, j), ev, float(M[i, j])))
    candidates.sort(key=lambda c: -c[1])

    best_pred, best_ev, _ = candidates[0]
    return ScorelineResult(
        lam_home=lam_h, lam_away=lam_a, rho=rho,
        p_home=ph, p_draw=pd, p_away=pa,
        best_pred=best_pred, best_ev=best_ev,
        top_alternatives=candidates[:n_alternatives],
        knockout=knockout,
    )


# ---------------------------------------------------------------------------
# 5. Convenience: go straight from raw market numbers to a pick
# ---------------------------------------------------------------------------

def pick_from_raw(p_home_raw: float, p_draw_raw: float, p_away_raw: float,
                  ou_line: float | None = None,
                  p_over_raw: float | None = None, p_under_raw: float | None = None,
                  rho: float = -0.10, knockout: bool = False,
                  devig: str = "shin") -> ScorelineResult:
    """
    One call from raw market probabilities (as captured, vig included) to an
    optimal scoreline. `devig` is 'shin' (default) or 'proportional'.

    Polymarket prices are already on a 0-1 (cents/100) probability scale, so
    pass them directly (e.g. 0.47, 0.28, 0.27). Decimal odds from a sportsbook
    should first be converted with implied_from_decimal().
    """
    devig_fn = devig_shin if devig == "shin" else devig_proportional
    p_h, p_d, p_a = devig_fn(np.array([p_home_raw, p_draw_raw, p_away_raw]))

    p_over = None
    if ou_line is not None and p_over_raw is not None:
        if p_under_raw is not None:
            o, u = devig_fn(np.array([p_over_raw, p_under_raw]))
            p_over = o
        else:
            p_over = min(max(p_over_raw, 1e-6), 1 - 1e-6)

    mkt = MarketInputs(p_home=p_h, p_draw=p_d, p_away=p_a,
                       ou_line=ou_line, p_over=p_over)
    return optimal_scoreline(mkt, rho=rho, knockout=knockout)


if __name__ == "__main__":
    # Smoke test on real captured odds: Ghana vs Panama (group stage)
    # Polymarket: Ghana 47, Draw 28, Panama 27 ; Totals O3.5=24, U3.5=82
    res = pick_from_raw(0.47, 0.28, 0.27, ou_line=3.5,
                        p_over_raw=0.24, p_under_raw=0.82, knockout=False)
    print(f"lambdas: home={res.lam_home:.3f}, away={res.lam_away:.3f}")
    print(f"P(1X2): {res.p_home:.1%} / {res.p_draw:.1%} / {res.p_away:.1%}")
    print(f"optimal pick: {res.best_pred[0]}-{res.best_pred[1]}  E[pts]={res.best_ev:.3f}")
    print("alternatives:")
    for pred, ev, px in res.top_alternatives:
        print(f"  {pred[0]}-{pred[1]}: E[pts]={ev:.3f}  P(exact)={px:.1%}")
