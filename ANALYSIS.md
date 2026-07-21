# Post-Mortem: Was It Skill?

The tournament is over. The pool had 641 players, the pot paid the top three,
and this project finished **4th by the rules set at the start** (711 points:
671 from matches + 30 for calling Spain champion + 10 for calling England
third). Two points short of the money.

This document asks the only three questions that matter after the fact, and
answers them with the 104-match dataset this repo accumulated — every
probability captured **before** kickoff, every result recorded after, every
claim reproducible from `analysis/final_report.py`.

1. **Was the result luck?** (No — p ≈ 4.5×10⁻¹⁰ against a know-nothing picker.)
2. **Did the probabilities keep their word?** (Yes — promised 646 ± 42, delivered 671, z = +0.58.)
3. **Where did the edge actually come from?** (Not where you'd think — the
   per-match model beats smart humans only slightly; the compounding edges were
   the podium bet, the scoring-rule optimization, and the endgame pivot.)

---

## 1. The season

![position over time](analysis/figures/01_season.png)

Bottom half of the table on matchday 6 (311th of ~660). First place — briefly —
after the first knockout match. Then the knockout variance both giveth (a
doubled exact vaulting 5th→1st) and taketh (two doubled draws, 1st→9th; a
missed app entry, 17th→19th). The final week's strategy pivot climbed
19th→4th.

## 2. Did the probabilities keep their word?

The model's whole premise was: de-vig the market's probabilities, build a
Dixon-Coles score matrix, and submit the scoreline that maximizes expected
points under the pool's 5/2/2/1 rule (doubled in knockouts). If that machinery
is honest, the points it *promises* (the sum of each pick's expected value)
should match the points it *delivers* — with the difference being luck.

![promise vs delivery](analysis/figures/02_promise_vs_delivery.png)

Over the 103 entered picks the model promised **646.3 ± 42.4** points. It
delivered **671** — a **z-score of +0.58**, the 72nd percentile of its own
exact distribution (computed by convolution, no simulation). The verdict:

- **The machinery was calibrated.** Delivery sits comfortably inside one sigma
  of promise. There is no hidden overconfidence and no sandbagging.
- **The luck component was +25 points** — mild good fortune, the kind that
  shows up in one tournament out of three. Roughly: skill earned ~646 of the
  671; variance donated the rest.

## 3. Skill vs luck, quantified

Two exact distributions, one axis:

![skill vs luck](analysis/figures/03_skill_vs_luck.png)

- A **know-nothing picker** (uniform over all 0–3 scorelines, never missing an
  entry, scored against the real 104 results) earns **392 ± 43**. The
  probability of such a picker reaching 671 is **4.5×10⁻¹⁰** — about one in
  two billion. By any conventional threshold (p < 0.05, p < 0.001, pick one),
  the result is not luck.
- Against the **real field**: 641 humans — many of whom watch far more
  football than the author — produced exactly 3 total scores above 711. Under
  the null hypothesis that this project was an average pool member, finishing
  4th or better has probability **4/641 ≈ 0.006**.
- On **raw match points alone** (no podium bonus) the project's 671 ranked
  roughly 12th of 641 — top 2% — while carrying a 14-point self-inflicted
  wound (§5).

## 4. Every strategy, same matches, same results

The shadow data makes honest baselines possible: every strategy below is
scored on the identical 104 real results.

![strategies](analysis/figures/04_strategies.png)

| Strategy | Points | What it represents |
|---|---:|---|
| Submitted + the missed SF entry | **685** | the model + strategy, executed perfectly |
| **Submitted (as it happened)** | **671** | what actually went to the scoreboard |
| Codere correct-score board | 661 | "just copy the bookmaker's most likely score" |
| Pure model argmax | 655 | the engine with no strategic overlay |
| Favorite 1-0 chalk | 650 | a disciplined fan: favorite wins, 1-0, every time |
| Favorite 2-1 chalk | 632 | the most common human instinct |
| Always 1-1 | 424 | the draw troll |
| Know-nothing (expected) | 392 | random scorelines |

Three honest observations:

- **The per-match model's edge over a disciplined human is real but thin**:
  argmax 655 vs favorite-1-0 chalk 650. Anyone who mechanically picked the
  favorite 1-0 for a month would have been near the top of this pool. The
  model's per-match advantage comes from knowing *when* the favorite's modal
  scoreline isn't 1-0 (totals-informed lambdas) — worth about +5 over 104
  matches. Nobody should sell this as alpha.
- **The strategic overlay was worth +16** (671 vs 655): all of it from the
  final four matches, where the objective switched from maximizing expected
  points to maximizing P(top-3) — picking outcomes *correlated* with the
  live podium slots instead of the most likely ones. The deviations went
  3-for-3 on direction (needed Argentina, got it; needed England, got it;
  needed Spain, got it).
- **Execution is a strategy too**: the gap between 685 and 671 is one missed
  phone entry. It out-weighed the entire per-match model edge.

## 5. Calibration — trusting the market was correct

![calibration](analysis/figures/05_calibration.png)

The 312 de-vigged outcome probabilities (H/D/A × 104 matches) against what
happened:

- **Multiclass Brier score 0.503** vs 0.667 for the uniform baseline — a
  **+24.5% skill score**.
- **Favorites hit 62.5% of the time, predicted 61.1%** — a 1.4-point gap, i.e.
  the market was neither over- nor under-confident this tournament.
- **Exact scorelines: 15 hits vs 13.0 expected.** Result type: 67 vs 62.8
  expected. Both within noise of promise — again, calibrated.
- The reliability curve hugs the diagonal in every bucket that has data.

This is the quiet, load-bearing result of the whole project: **the
market-implied probabilities were trustworthy, so every downstream decision
built on them was built on rock.** The edge never came from disagreeing with
the market — it came from *optimizing what the market doesn't care about*:
the pool's scoring rule and payout structure.

## 6. The two points

The money was missed by two points. The complete, honest decomposition:

| Event | Swing | Nature |
|---|---|---|
| The missed semifinal app entry | −14 (725 → 711 world) | human error |
| The final landing 0-0 (1-1 pickers +8 on us) | variance | priced, accepted |
| A rank-11+ rival's champion+runner-up podium (+50) | rival skill | intel blind spot |
| The endgame pivot (correlation over chalk) | +16 | strategy |
| The podium bet (Spain champion, England third) | +40 | model |

The enumeration before the final modeled the five visible threats and
correctly identified the max-P(money) pick — but pulled rival podiums only
for the visible top-10. A player sitting 11th+ with a locked +50 podium bonus
was effectively **2nd all along, invisible**. With that one extra screenshot,
the optimal pick flips from defending chalk to differentiating — and the
differentiated pick would have cashed. Lesson recorded: *in any endgame,
enumerate everyone within maximum-remaining-bonus of the cut, not everyone
you can see.*

## 7. What this project actually demonstrates

- **Markets are calibrated; use them.** Free, sharp probability estimates
  beat anything an individual can produce (§5).
- **The edge is in the scoring rule, not the probabilities.** Optimizing
  5/2/2/1-doubled expected value ≠ predicting the most likely score (§4).
- **When the payout is top-k, expected points is the wrong objective.** The
  endgame pivot from max-E to max-P(top-3) — picking correlated outcomes —
  was worth more than the entire per-match model edge (§4).
- **Variance is the product, not the enemy.** A 641-player pool is won in the
  tails; the strategy that finishes 4th repeatably will sometimes lose to
  someone's hot month, and that is the correct trade.
- **Process beats model.** The single largest controllable loss was not a
  probability estimate — it was a save button (§6).

---

*Every number here regenerates from the committed CSVs:*
`python analysis/final_report.py`. *Every pick predates its match — see the
release timestamps on the `picks-*` tags.*
