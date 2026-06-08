"""
podium_model.py
===============
Podium (champion / runner-up / third) calculation for the World Cup pool.

The podium is a separate, one-time, IRREVERSIBLE pick scored:
    champion   correct -> 30 pts
    runner-up  correct -> 20 pts
    third      correct -> 10 pts

This module turns three market futures into expected-points-optimal podium
picks:
    - "champion"      market -> P(team wins the tournament)
    - "reach_final"   market -> P(team reaches the final)
    - "reach_semis"   market -> P(team reaches the semifinals)

From those we derive, per team:
    P(runner-up) = P(reach final) - P(champion)            [reaches final, loses it]
    P(lose semi) = P(reach semis) - P(reach final)
    P(third)     = P(lose semi) * 0.5                       [wins 3rd-place playoff]

Normalization is market-aware: champion probs sum to 1 (one champion),
reach-final to 2 (two finalists), reach-semis to 4 (four semifinalists).

NOTE on the 2026 bracket: with 48 teams the bracket assignment is flexible
enough that no rigid "two halves" constraint binds the top contenders (Codere's
finalist-pair odds confirmed any top pair can meet in the final). So the podium
is computed from marginals without a hard same-half/opposite-half restriction.
The expected-points figure is therefore an approximation that ignores the small
positive correlation between champion and third when they share a bracket region;
joint finalist-pair odds can refine it if desired.

Author: Julian (portfolio project)
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

import numpy as np


def _to_prob(value: float, value_type: str) -> float:
    """Convert a captured value to a raw implied probability."""
    if value_type == "decimal":
        return 1.0 / value
    if value_type == "prob":
        return float(value)
    raise ValueError(f"value_type must be 'decimal' or 'prob', got {value_type!r}")


def normalize_to(target_sum: float, raw: dict[str, float],
                 market_name: str = "") -> dict[str, float]:
    """
    Scale raw probabilities so they sum to `target_sum` (de-vig for a market
    with a known number of qualifying slots: 1 champion, 2 finalists, 4 semis).

    Guard: a *complete* market's raw (vig-loaded) probabilities should sum to
    MORE than the slot count (slot count + vig). If the raw sum is below the
    slot count, the captured list is almost certainly truncated (missing teams),
    which would inflate every probability after normalization. Warn loudly so a
    truncated capture never silently produces inflated podium numbers.
    """
    s = sum(raw.values())
    if s <= 0:
        return {k: 0.0 for k in raw}
    if s < target_sum:
        import warnings
        warnings.warn(
            f"[{market_name or 'market'}] raw probability sum is {s:.3f}, "
            f"below the expected slot count of {target_sum:.0f}. The captured "
            f"team list is likely TRUNCATED — capture ALL teams in this market, "
            f"not just the top ones, or probabilities will be inflated.",
            stacklevel=2,
        )
    factor = target_sum / s
    return {k: v * factor for k, v in raw.items()}


@dataclass
class PodiumProbs:
    champion: dict[str, float]
    runner_up: dict[str, float]
    third: dict[str, float]


def derive_podium_probs(champion_odds: dict[str, float],
                        reach_final_odds: dict[str, float],
                        reach_semis_odds: dict[str, float]) -> PodiumProbs:
    """
    ANCHOR METHOD (recommended, robust to partial capture).

    Inputs are DECIMAL ODDS, not probabilities:
      - champion_odds:    FULL team list (the headline market; easy to capture
                          in full). De-vigged to P(champion) summing to 1.
      - reach_final_odds: per-team decimal odds; top ~8 teams is enough.
      - reach_semis_odds: per-team decimal odds; top ~8 teams is enough.

    For each team we scale its champion probability by the odds ratio between
    markets:

        P(reach final) = P(champion) * (champion_odds / reach_final_odds)
        P(reach semis) = P(champion) * (champion_odds / reach_semis_odds)

    The per-team odds ratio cancels the (roughly proportional) vig, so this does
    NOT require the full team list for the reach-final / reach-semis markets and
    is robust to truncation — unlike normalizing each market to its slot count.

    Then:
        P(runner-up) = P(reach final) - P(champion)
        P(third)     = 0.5 * ( P(reach semis) - P(reach final) )
    """
    champ_raw = {t: 1.0 / o for t, o in champion_odds.items()}
    p_champ = normalize_to(1.0, champ_raw, "champion")

    runner_up, third = {}, {}
    for t, pc in p_champ.items():
        of = reach_final_odds.get(t)
        os = reach_semis_odds.get(t)
        if of is None or os is None:
            continue  # need both futures odds to place a team on the podium
        co = champion_odds[t]
        p_final = pc * (co / of)
        p_semis = pc * (co / os)
        runner_up[t] = max(p_final - pc, 0.0)
        third[t] = max(p_semis - p_final, 0.0) * 0.5
    champ_placed = {t: p_champ[t] for t in runner_up}
    return PodiumProbs(champion=champ_placed, runner_up=runner_up, third=third)


@dataclass
class PodiumPick:
    champion: str
    runner_up: str
    third: str
    ev: float
    breakdown: tuple[float, float, float]  # (30*Pc, 20*Pr, 10*Pt)


def expected_podium_points(champion: str, runner_up: str, third: str,
                           probs: PodiumProbs) -> float:
    pc = probs.champion.get(champion, 0.0)
    pr = probs.runner_up.get(runner_up, 0.0)
    pt = probs.third.get(third, 0.0)
    return 30 * pc + 20 * pr + 10 * pt


def rank_podiums(probs: PodiumProbs, top_n: int = 10) -> list[PodiumPick]:
    """
    Rank all (champion, runner-up, third) triples by expected points.
    Teams must be distinct. Uses the union of teams present in any market.
    """
    teams = sorted(
        set(probs.champion) | set(probs.runner_up) | set(probs.third),
        key=lambda t: -probs.champion.get(t, 0.0),
    )
    picks = []
    for champ, run, thi in permutations(teams, 3):
        pc = probs.champion.get(champ, 0.0)
        pr = probs.runner_up.get(run, 0.0)
        pt = probs.third.get(thi, 0.0)
        ev = 30 * pc + 20 * pr + 10 * pt
        picks.append(PodiumPick(champ, run, thi, ev, (30 * pc, 20 * pr, 10 * pt)))
    picks.sort(key=lambda p: -p.ev)
    return picks[:top_n]


if __name__ == "__main__":
    # Dry run on odds captured during the project (DECIMAL ODDS).
    # Anchor method: champion must be the FULL team list; reach_final /
    # reach_semis need only the top contenders (per-team odds ratios).
    champion_odds = {
        "Spain":5.50,"France":6.00,"England":7.00,"Argentina":9.00,"Brazil":9.00,
        "Portugal":10.00,"Germany":15.00,"Netherlands":20.00,"Norway":27.00,"Belgium":35.00,
        "Colombia":35.00,"Japan":50.00,"Morocco":50.00,"USA":65.00,"Uruguay":65.00,
        "Ecuador":75.00,"Croatia":80.00,"Mexico":80.00,"Switzerland":80.00,"Turkey":80.00,
        "Senegal":120.00,"Sweden":125.00,"Austria":150.00,"Canada":160.00,"Paraguay":160.00,
        "Saudi Arabia":250.,"Algeria":250.,"Australia":250.,"Bosnia":250.,"Cape Verde":250.,
        "Qatar":250.,"South Korea":250.,"Ivory Coast":250.,"Curacao":250.,"Egypt":250.,
        "Scotland":250.,"Ghana":250.,"Haiti":250.,"Iraq":250.,"Iran":250.,"Jordan":250.,
        "New Zealand":250.,"Panama":250.,"DR Congo":250.,"Czech Republic":250.,
        "South Africa":250.,"Tunisia":250.,"Uzbekistan":250.,
    }
    reach_final_odds = {
        "Spain":3.25,"France":3.75,"England":4.00,"Argentina":5.00,"Brazil":5.00,"Portugal":5.60,
    }
    reach_semis_odds = {
        "Spain":2.35,"France":2.60,"England":2.75,"Argentina":3.25,"Brazil":3.25,"Portugal":3.50,
    }

    probs = derive_podium_probs(champion_odds, reach_final_odds, reach_semis_odds)

    print("\nPer-team probabilities (anchor method, de-vigged):")
    print(f"  {'Team':<11}{'P(champ)':>9}{'P(runner)':>10}{'P(third)':>10}")
    for t in sorted(probs.champion, key=lambda x: -probs.champion[x])[:6]:
        print(f"  {t:<11}{probs.champion[t]*100:>8.1f}%"
              f"{probs.runner_up[t]*100:>9.1f}%{probs.third[t]*100:>9.1f}%")

    print("\nTop podium picks by expected points:")
    print(f"  {'#':<3}{'Champion':<11}{'Runner-up':<11}{'Third':<11}{'E[pts]':>7}")
    for i, p in enumerate(rank_podiums(probs, top_n=6), 1):
        print(f"  {i:<3}{p.champion:<11}{p.runner_up:<11}{p.third:<11}{p.ev:>7.2f}")
