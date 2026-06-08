# Market-Implied Probabilities Applied to a World Cup Prediction Pool

A decision-science logbook (*bitácora*) for the 2026 FIFA World Cup pool ("polla")
run at Coempopular — **250 participants, one custom scoring rule.**

## Thesis

This project does **not** claim to beat the betting market. The opposite: it
treats market-implied probabilities as the best available estimator of match
outcomes — already efficient, already incorporating injuries, form, and lineups
faster than any individual could — and asks a narrower, answerable question:

> Given that the market is efficient and I cannot improve on it, how much
> competitive edge comes from (a) applying its probabilities *systematically*
> across all 104 matches when most rivals guess, and (b) optimizing picks for
> the pool's specific scoring rule rather than for predicting the most likely
> scoreline?

Two structural facts make this edge real without any claim of superior
information:

1. **No structural vig drag.** Unlike a bet at fair odds (where the bookmaker's
   margin makes expected value negative by construction), the pool charges no
   per-pick "commission." A small informational edge that the vig would eat in
   betting translates directly into points here.
2. **A scoring rule the market does not optimize for.** The pool rewards points
   on a 5/2/2/1 structure (result type / exact home goals / exact away goals /
   goal difference), not profit. The point-maximizing scoreline is generally
   *not* the most likely scoreline — so there is room to optimize on top of the
   market's probabilities.

The logbook is judged on **decision quality, not outcome.** Winning a 250-person
pool is improbable for anyone in a single tournament (variance dominates a single
run). The value here is a documented, reproducible decision process — whether it
wins or not.

## Method

```
  market odds  ->  de-vig (Shin)  ->  solve Poisson lambdas (1X2 + over/under)
               ->  Dixon-Coles score matrix  ->  argmax expected points
```

- **Source (official):** Polymarket 1X2 + over/under per match. Polymarket's
  liquid markets are kept aligned with sharp books (Pinnacle) by arbitrage bots,
  so they inherit sharp-book efficiency — useful because direct Pinnacle access
  is blocked from the US.
- **Source (shadow, for comparison only):** Codere, captured in parallel but
  never used for live picks — purely to measure, after the fact, which source
  would have scored better. The official source stays constant all tournament.
- **De-vigging:** Shin (1992) method, which collapses to proportional
  normalization for near-zero-vig markets and is better-calibrated for
  higher-margin ones (Štrumbelj 2014).
- **Scoreline model:** independent Poisson with the Dixon-Coles (1997) low-score
  correction (ρ ≈ −0.10), which lifts the probability of 0-0 and 1-1.
- **Optimization:** for each match, pick the scoreline maximizing expected points
  under the pool rule — empirically a slight win for the favorite in group play
  (e.g. 1-0, 2-1), never a draw; a draw becomes optimal only in genuinely even
  knockout matches, where 90-minute draws spike.

The **podium** (champion / runner-up / third) is a separate, irreversible,
one-time pick scored 30/20/10. Its methodology is fixed (market futures for
champion / reach-final / reach-semis, weighed against the competitive landscape),
but the three teams are locked only the **day before the opener**, on the freshest
odds.

## Capture discipline (the credibility backbone)

Every odds capture is timestamped and committed to Git **before** the relevant
match is played. The commit history is the tamper-evident proof that picks were
made on prior information — which is what makes a logbook about *decision quality*
credible. Two recurring captures:

- **Day before the opener:** futures markets → lock the podium.
- **Day before each match:** that match's 1X2 + over/under → generate the pick.
  (Capture ~1h before kickoff only for matches with a real lineup question.)

Screenshots are saved under `data/screenshots/` as visual backups alongside the
CSV rows.

## Repository layout

```
worldcup-2026-polla/
├── README.md
├── data/
│   ├── match_odds_log.csv      # append-only raw captures (1X2 + O/U per match)
│   ├── podium_odds_log.csv     # futures snapshot (day-before-opener)
│   └── screenshots/            # visual backups of each capture
├── src/
│   └── polla_model.py          # engine: odds -> probabilities -> optimal scoreline
├── notebooks/
│   └── bitacora.ipynb          # the deliverable: methodology + live logbook
└── outputs/                    # figures and computed results
```

## Engine quickstart

```python
from src.polla_model import pick_from_raw

# Ghana vs Panama, group stage. Polymarket: 1X2 = 47/28/27, totals O3.5=24 U3.5=82
res = pick_from_raw(0.47, 0.28, 0.27, ou_line=3.5,
                    p_over_raw=0.24, p_under_raw=0.82, knockout=False)

print(res.best_pred)   # (1, 0)  -> predict Ghana 1-0
print(res.best_ev)     # ~3.94 expected points
```

## References

- Dixon, M. & Coles, S. (1997). *Modelling association football scores and
  inefficiencies in the football betting market.* Applied Statistics 46(2).
- Štrumbelj, E. (2014). *On determining probability forecasts from betting odds.*
  International Journal of Forecasting 30(4).
- Shin, H. S. (1993). *Measuring the incidence of insider trading in a market for
  state-contingent claims.* Economic Journal 103.
- Baker, R. & McHale, I. (2013). *Forecasting exact scores in National Football
  League games.* International Journal of Forecasting 29(1).
