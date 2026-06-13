# CLAUDE.md — Operating procedure for the World Cup 2026 polla

This file is the fixed procedure for running picks. Follow it exactly every time.
Do not improvise the numbers, the source, or the steps. When in doubt, stop and
ask rather than guess. We will repeat this for 100+ matches; consistency is the
whole point.

## Golden rules (never violate)

1. **Polymarket is the ONLY source for picks submitted to Pasión de Gol.**
   Codere is shadow-only — captured for the end-of-tournament comparison
   (`compare_strategies.py`), and NEVER submitted. Never tell the user to enter a
   Codere-derived pick in Pasión de Gol.
2. **The pick is always `max E` (highest expected points)** from the model — for
   both the podium and each match. Do not second-guess the model's argmax.
3. **Data lives in the CSVs; code never holds the numbers.** All numbers go into
   `data/*.csv`. The committed CSV + commit timestamp is the audit trail.
4. **Never renormalize Polymarket probabilities.** Enter them as captured and use
   `value_type="prob"`. (Codere decimal odds ARE de-vigged by the model.)
5. **Read numbers from the screenshots only** — never recall odds from memory.
6. **After any code change, run `python tests/test_polla.py`** — all tests must
   pass before committing.

## Polymarket capture rule (how to read the numbers)

Polymarket shows a bold headline % (the mid = true probability) and a green "buy"
button (the ask, inflated by the spread). **Always use the headline %, never the
ask ¢.**
- **champion**: use the one-decimal headline (e.g. France 16.2% -> 0.162). Integer
  rounding would erase the gap that decides the title.
- **reach_final / reach_semis**: use the integer headline % (e.g. Spain 44% -> 0.44).
- **Codere**: record decimal odds exactly as shown. For each Codere match also
  record its correct-score pick = the single LOWEST-odds (most likely) scoreline.
  **cs tie-break:** if two scorelines share the lowest odds, take the one whose
  1X2 outcome is more likely per Codere's own 1X2 (e.g. favorite's 1:0 over a
  1:1 draw when the favorite's win is priced shorter than the draw). If the tied
  scorelines have the SAME 1X2 outcome (e.g. 3:0 vs 4:0, both home wins), take
  the lower-scoring one (fewer total goals is more probable). Note the tie in the
  notes column.
  Convert Codere decimal odds to implied probs (1/odds) when filling its
  p_home/p_draw/p_away/p_over/p_under (the model de-vigs them).
- **Codere champion must always be the FULL 48-team field** — its de-vig requires
  the complete list; a truncated list silently inflates the favorites.

## Workflow — MATCHES (repeat for every match, ~104 times)

1. **Screenshots in:** user drops images into `Images/`. (Inbox.)
2. **Read** every screenshot. For each match capture: Polymarket Moneyline (1X2) +
   2.5 Totals + volumes; Codere 1X2 + 2.5 Totals + top correct-score line + odds.
3. **Fill `data/match_odds_polymarket.csv`** (primary). One row per match:
   `capture_datetime, match_datetime, stage, match_id, home_team, away_team,
   p_home, p_draw, p_away, ml_volume_usd, ou_line, p_over, p_under,
   totals_volume_usd, submitted_home, submitted_away, actual_home, actual_away,
   notes`. Leave submitted_* / actual_* blank for now.
   - If updated odds arrive for a match before kickoff, OVERWRITE that row with
     the fresh capture (and update capture_datetime).
4. **Fill `data/match_odds_codere.csv`** (shadow): `..., p_home, p_draw, p_away,
   ou_line, p_over, p_under, cs_pred_home, cs_pred_away, cs_pred_odds, notes`.
5. **Run the engine** on each Polymarket row via an ephemeral inline script (do
   NOT create a persistent runner file). Import from `src/`:
   `from polla_model import pick_from_raw` and call
   `pick_from_raw(p_home, p_draw, p_away, ou_line=ou_line, p_over_raw=p_over,
   p_under_raw=p_under, knockout=(stage != "group"))`. The pick is `res.best_pred`.
6. **Give the user the picks** to enter in Pasión de Gol: for each match,
   `home_team H-A away_team` with its E[pts]. Polymarket only.
7. **Record what was submitted:** write the chosen scoreline into
   `submitted_home` / `submitted_away` of the Polymarket row.
8. **File the screenshots:** move them from `Images/` to `data/screenshots/` with
   dated, sourced names (e.g. `2026-06-11_match_<id>_polymarket.jpg`). The move
   marks the capture as processed.
9. **Commit + push** with an honest pre-game message, e.g.
   `Picks locked before kickoff — <match(es)> <date>`. The push timestamp is the
   proof the pick preceded the match.
10. **Tag + GitHub Release per pick-lock day**: create annotated tag
    `picks-YYYY-MM-DD`, push it, then create a Release from it — the release's
    server-generated timestamp makes the locked-before-kickoff claim
    independently verifiable. Tooling: `gh` binary at `~/.local/bin/gh`, token at
    `~/.config/polla/gh_token` (repo scope only); invoke as
    `GH_TOKEN=$(cat ~/.config/polla/gh_token) ~/.local/bin/gh release create ...`.
    (`gh auth login` rejects this token for lacking read:org — always use the
    GH_TOKEN env var instead.)

### After matches are played (results)
- Fill `actual_home` / `actual_away` in `data/match_odds_polymarket.csv`.
- When the user reports their pool standing, append a row to
  `data/pool_standings.csv` (`date,total_players,position,notes`) — it is a
  time series of position in the 641-player pool.
- Commit + push (e.g. `Results: <date>`).
- Run `python src/compare_strategies.py` to score poly_model vs codere_model vs
  codere_exact once results have accumulated.

## Workflow — PODIUM (one time only, day before the opener)

1. Read the six podium screenshots (champion / reach_final / reach_semis, on both
   Polymarket and Codere).
2. Fill `data/podium_odds_polymarket.csv` (`market, team, prob, volume_usd`) with
   the Polymarket headline probabilities per the capture rule, and
   `data/podium_odds_codere.csv` (`market, team, decimal_odds`) with Codere odds.
   Champion should be as full a field as practical; reach_final / reach_semis need
   only the top contenders. Keep the same team set across all three markets so a
   team can be placed.
3. Compute with the podium model via inline script:
   `from podium_model import derive_podium_probs, rank_podiums`, build the three
   `{team: prob}` dicts from the Polymarket CSV, call
   `derive_podium_probs(champion, reach_final, reach_semis, value_type="prob")`,
   then `rank_podiums(probs)`. The pick is rank #1 (champion / runner-up / third).
   - **Champion tie rule:** if the top two teams are within noise at capture time,
     the higher one-decimal headline % is champion, period — no discretion. Record
     both prices in notes.
4. Give the user the podium to submit in Pasión de Gol (Polymarket only).
5. File screenshots to `data/screenshots/`, commit + push.
6. **After the real June 10 push, create a GitHub Release tagged
   `picks-2026-06-10`** — release timestamps are server-generated, making the
   locked-before-kickoff claim independently verifiable.

## Determinism / anti-hallucination checklist

- Picks come from the model's `max E`, computed from the committed CSV — not from
  intuition.
- Polymarket = picks; Codere = shadow comparison only.
- Headline % (mid), not buy-¢ (ask); champion to one decimal.
- Never renormalize Polymarket probs.
- If a screenshot is ambiguous or a number can't be read confidently, STOP and ask.
- Every capture is committed BEFORE the match; results committed AFTER.
