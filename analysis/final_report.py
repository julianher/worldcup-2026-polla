"""Tournament post-mortem: skill vs luck, calibration, and baselines.

Reads data/match_odds_polymarket.csv (104 matches, complete), computes:
  1. Promise vs delivery — expected points of the submitted picks under the
     model's own probabilities vs the 671 actually earned (exact convolution
     PMF, no Monte Carlo needed).
  2. Luck benchmark — the exact PMF of a know-nothing picker (uniform over
     0-3 x 0-3 scorelines) on the REAL results, and where 671 falls in it.
  3. Baseline strategies — pure argmax, Codere shadow bots, chalk heuristics.
  4. Probability calibration — Brier score, reliability curve, favorite hit
     rate, exact-score expectation vs realization.
Figures land in analysis/figures/, stats print to stdout.
"""
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from polla_model import pick_from_raw, score_matrix, score_points  # noqa: E402

# ---------------------------------------------------------------- load
rows = list(csv.DictReader(open(ROOT / "data" / "match_odds_polymarket.csv")))
rows.sort(key=lambda r: r["match_datetime"])
assert len(rows) == 104

matches = []          # every match, chronological
for r in rows:
    ko = r["stage"] != "group"
    rp = pick_from_raw(float(r["p_home"]), float(r["p_draw"]), float(r["p_away"]),
                       ou_line=float(r["ou_line"]), p_over_raw=float(r["p_over"]),
                       p_under_raw=float(r["p_under"]), knockout=ko)
    M = score_matrix(rp.lam_home, rp.lam_away, rp.rho)
    actual = (int(r["actual_home"]), int(r["actual_away"]))
    sub = None
    if r["submitted_home"] != "":
        sub = (int(r["submitted_home"]), int(r["submitted_away"]))
    matches.append(dict(id=r["match_id"], stage=r["stage"], ko=ko, M=M, rp=rp,
                        actual=actual, sub=sub, dt=r["match_datetime"]))

# ------------------------------------------------- helpers (exact PMFs)
def pick_pmf(pick, M, ko):
    """PMF of points earned by `pick` when the world is drawn from M."""
    pmf = {}
    for i in range(11):
        for j in range(11):
            p = M[i][j]
            if p < 1e-12:
                continue
            pts = score_points(pick, (i, j), knockout=ko)
            pmf[pts] = pmf.get(pts, 0.0) + p
    return pmf

def convolve(pmfs, size):
    """Exact distribution of the sum of independent integer-valued PMFs."""
    dist = np.zeros(size); dist[0] = 1.0
    for pmf in pmfs:
        nxt = np.zeros(size)
        for pts, p in pmf.items():
            nxt[pts:] += p * dist[:size - pts]
        dist = nxt
    return dist

def stats_of(dist):
    xs = np.arange(len(dist))
    mu = float((xs * dist).sum())
    var = float(((xs - mu) ** 2 * dist).sum())
    return mu, var ** 0.5

SIZE = 1600  # > max possible 72*10 + 32*20 = 1360

# ---------------------------------------------- 1. promise vs delivery
entered = [m for m in matches if m["sub"] is not None]          # 103
actual_total = sum(score_points(m["sub"], m["actual"], knockout=m["ko"])
                   for m in entered)
promise_pmfs = [pick_pmf(m["sub"], m["M"], m["ko"]) for m in entered]
promise = convolve(promise_pmfs, SIZE)
mu_p, sd_p = stats_of(promise)
pct = float(promise[:actual_total + 1].sum())
z = (actual_total - mu_p) / sd_p
print("== PROMISE vs DELIVERY (103 entered picks) ==")
print(f"expected {mu_p:.1f} +- {sd_p:.1f}   actual {actual_total}   "
      f"luck {actual_total - mu_p:+.1f} pts   z={z:+.2f}   percentile {100*pct:.1f}%")

# cumulative series for the figure
cum_e, cum_v, cum_a = [], [], []
e = v = a = 0.0
for m in entered:
    pmf = pick_pmf(m["sub"], m["M"], m["ko"])
    mu = sum(k * p for k, p in pmf.items())
    var = sum(k * k * p for k, p in pmf.items()) - mu * mu
    e += mu; v += var
    a += score_points(m["sub"], m["actual"], knockout=m["ko"])
    cum_e.append(e); cum_v.append(v); cum_a.append(a)

# ------------------------------------------------- 2. luck benchmark
# know-nothing picker: uniform over the 16 scorelines 0-3 x 0-3, real results
# fixed, ALL 104 matches (a colleague never misses an entry).
rand_pmfs = []
for m in matches:
    vals = {}
    for i in range(4):
        for j in range(4):
            pts = score_points((i, j), m["actual"], knockout=m["ko"])
            vals[pts] = vals.get(pts, 0.0) + 1 / 16
    rand_pmfs.append(vals)
rand = convolve(rand_pmfs, SIZE)
mu_r, sd_r = stats_of(rand)
p_rand = float(rand[actual_total:].sum())
print("\n== LUCK BENCHMARK (uniform 0-3 picker, real results, 104 matches) ==")
print(f"random picker {mu_r:.1f} +- {sd_r:.1f}   P(random >= {actual_total}) = {p_rand:.2e}")

# --------------------------------------------------- 3. baselines
def bot_total(pickers):
    return sum(score_points(pickers(m), m["actual"], knockout=m["ko"]) for m in matches)

def favorite_pick(m, hi, lo):
    return (hi, lo) if m["rp"].p_home >= m["rp"].p_away else (lo, hi)

bots = {
    "Submitted (with the human error)": actual_total,           # SF counted as 0
    "Submitted + the missed SF entry": actual_total + 14,
    "Pure model argmax": bot_total(lambda m: m["rp"].best_pred),
    "Favorite 2-1 chalk": bot_total(lambda m: favorite_pick(m, 2, 1)),
    "Favorite 1-0 chalk": bot_total(lambda m: favorite_pick(m, 1, 0)),
    "Always 1-1": bot_total(lambda m: (1, 1)),
    "Know-nothing (expected)": mu_r,
}
# codere shadow bots from the shadow CSV
crows = {r["match_id"]: r for r in csv.DictReader(open(ROOT / "data" / "match_odds_codere.csv"))}
cs_total = sum(score_points((int(crows[m["id"]]["cs_pred_home"]),
                             int(crows[m["id"]]["cs_pred_away"])),
                            m["actual"], knockout=m["ko"]) for m in matches)
bots["Codere correct-score board"] = cs_total
print("\n== STRATEGY TOTALS (104 matches, real results) ==")
for k, val in sorted(bots.items(), key=lambda t: -t[1]):
    print(f"  {k:36} {val:7.1f}")

# --------------------------------------------------- 4. calibration
briers, unis = [], []
fav_ps, fav_hits = [], []
bucket_pred, bucket_obs = [], []
for m in matches:
    ah, aa = m["actual"]
    o = [ah > aa, ah == aa, ah < aa]
    p = [m["rp"].p_home, m["rp"].p_draw, m["rp"].p_away]
    briers.append(sum((pi - oi) ** 2 for pi, oi in zip(p, o)))
    unis.append(sum((1 / 3 - oi) ** 2 for oi in o))
    k = int(np.argmax(p))
    fav_ps.append(p[k]); fav_hits.append(o[k])
    for pi, oi in zip(p, o):
        bucket_pred.append(pi); bucket_obs.append(float(oi))
print("\n== CALIBRATION (104 matches, de-vigged model probabilities) ==")
print(f"multiclass Brier {np.mean(briers):.4f}  (uniform 1/3 baseline {np.mean(unis):.4f}; "
      f"skill {1 - np.mean(briers)/np.mean(unis):+.1%})")
print(f"favorite hit rate {np.mean(fav_hits):.1%} observed vs {np.mean(fav_ps):.1%} predicted "
      f"({sum(fav_hits)}/104)")

exp_exact = sum(m["M"][m["sub"][0]][m["sub"][1]] for m in entered)
act_exact = sum(m["sub"] == m["actual"] for m in entered)
res = lambda s: (s[0] > s[1]) - (s[0] < s[1])
exp_res = sum((m["rp"].p_home if res(m["sub"]) > 0 else
               m["rp"].p_draw if res(m["sub"]) == 0 else m["rp"].p_away)
              for m in entered)
act_res = sum(res(m["sub"]) == res(m["actual"]) for m in entered)
print(f"exact scorelines: {act_exact} hit vs {exp_exact:.1f} expected")
print(f"result type:      {act_res} hit vs {exp_res:.1f} expected  (of 103)")

# reliability buckets (312 outcome probabilities)
bp, bo = np.array(bucket_pred), np.array(bucket_obs)
edges = [0, .1, .2, .3, .4, .5, .65, 1.0]
rel = []
for lo, hi in zip(edges[:-1], edges[1:]):
    sel = (bp >= lo) & (bp < hi)
    if sel.sum() >= 5:
        rel.append((float(bp[sel].mean()), float(bo[sel].mean()), int(sel.sum())))
print("reliability buckets (predicted -> observed, n):")
for pr, ob, n in rel:
    print(f"  {pr:.2f} -> {ob:.2f}  (n={n})")

# per-stage promise vs delivery
print("\n== BY STAGE ==")
for st in ["group", "R32", "R16", "QF", "SF", "3rd", "F"]:
    ms = [m for m in entered if m["stage"] == st]
    ee = sum(sum(k * p for k, p in pick_pmf(m["sub"], m["M"], m["ko"]).items()) for m in ms)
    aa_ = sum(score_points(m["sub"], m["actual"], knockout=m["ko"]) for m in ms)
    print(f"  {st:6} n={len(ms):3}  E {ee:6.1f}  actual {aa_:4}  luck {aa_-ee:+6.1f}")

# ---------------------------------------------------------------- figures
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURF, INK, SEC, MUT = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, BLUE, GREEN = "#e1e0d9", "#c3c2b7", "#2a78d6", "#008300"
BAND, LBLUE = "#cde2fb", "#9ec5f4"
plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "figure.facecolor": SURF, "axes.facecolor": SURF,
    "axes.edgecolor": AXIS, "axes.labelcolor": SEC,
    "xtick.color": MUT, "ytick.color": MUT,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlecolor": INK, "font.size": 11,
})
FIG = ROOT / "analysis" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

def save(fig, name):
    fig.savefig(FIG / name, dpi=200, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)
    print(f"wrote analysis/figures/{name}")

# F1 — the season: pool position over time
srows = list(csv.DictReader(open(ROOT / "data" / "pool_standings.csv")))
pos = [int(r["position"]) for r in srows]
dates = [r["date"][5:] for r in srows]
fig, ax = plt.subplots(figsize=(9.6, 5.0))
x = range(len(pos))
ax.plot(x, pos, color=BLUE, lw=2, marker="o", ms=5,
        markerfacecolor=BLUE, markeredgecolor=SURF, markeredgewidth=1.2, zorder=3)
ax.set_yscale("log")
ax.set_yticks([1, 3, 10, 30, 100, 300])
ax.set_yticklabels(["1st", "3rd", "10th", "30th", "100th", "300th"])
ax.invert_yaxis()
ax.grid(axis="x", visible=False)
ann = [(5, "311th — matchday 6 low", (0, -16), "center"),
       (19, "1st after the R32 opener", (12, -4), "left"),
       (33, "19th — the missed\nsemifinal entry", (0, -26), "center"),
       (len(pos) - 1, "4th of 641\n(original rules)", (-10, 16), "center")]
for i, txt, (dx, dy), ha in ann:
    ax.annotate(txt, (i, pos[i]), textcoords="offset points", xytext=(dx, dy),
                fontsize=9, color=SEC, ha=ha)
    ax.plot(i, pos[i], "o", ms=8, mfc="none", mec=INK, mew=1.2, zorder=4)
step = max(1, len(pos) // 9)
ax.set_xticks(list(x)[::step]); ax.set_xticklabels(dates[::step])
ax.set_title("A season in the pool — position among 641 players", loc="left", fontsize=14)
ax.set_xlabel("2026 (month-day)")
save(fig, "01_season.png")

# F2 — promise vs delivery, cumulative
fig, ax = plt.subplots(figsize=(9.6, 5.0))
xs = np.arange(1, len(cum_e) + 1)
sd_band = np.sqrt(np.array(cum_v))
ax.fill_between(xs, np.array(cum_e) - sd_band, np.array(cum_e) + sd_band,
                color=BAND, alpha=0.7, lw=0, label="model promise ±1σ")
ax.plot(xs, cum_e, color=BLUE, lw=2, label="expected (model promise)")
ax.plot(xs, cum_a, color=GREEN, lw=2, label="actually earned")
ax.annotate(f"expected {cum_e[-1]:.0f}", (xs[-1], cum_e[-1]),
            textcoords="offset points", xytext=(8, -4), color=BLUE, fontsize=10,
            fontweight="bold")
ax.annotate(f"actual {cum_a[-1]:.0f}", (xs[-1], cum_a[-1]),
            textcoords="offset points", xytext=(8, 6), color=GREEN, fontsize=10,
            fontweight="bold")
ax.axvline(72.5, color=AXIS, lw=1, ls=":")
ax.text(72.5, ax.get_ylim()[1] * 0.02, " knockouts (points ×2) ",
        color=MUT, fontsize=9, ha="left")
ax.legend(loc="upper left", frameon=False, labelcolor=SEC)
ax.set_title("Promise vs delivery — the probabilities kept their word", loc="left", fontsize=14)
ax.set_xlabel("entered picks, chronological (103 of 104)")
ax.set_xlim(0, 118)
save(fig, "02_promise_vs_delivery.png")

# F3 — skill vs luck: two exact distributions and where 671 sits
fig, ax = plt.subplots(figsize=(9.6, 5.0))
lo, hi = 380, 780
xr = np.arange(lo, hi)
ax.fill_between(xr, rand[lo:hi] * 100, color=GRID, lw=0)
ax.plot(xr, rand[lo:hi] * 100, color=MUT, lw=2)
ax.fill_between(xr, promise[lo:hi] * 100, color=BAND, alpha=0.8, lw=0)
ax.plot(xr, promise[lo:hi] * 100, color=BLUE, lw=2)
ax.axvline(actual_total, color=INK, lw=1.6, ls="--")
ax.annotate(f"actual: {actual_total}", (actual_total, ax.get_ylim()[1] * 0.94),
            xytext=(8, 0), textcoords="offset points", color=INK,
            fontsize=11, fontweight="bold")
exp10 = int(np.floor(np.log10(p_rand)))
mant = p_rand / 10 ** exp10
ax.annotate(f"know-nothing picker\n{mu_r:.0f} ± {sd_r:.0f}\n"
            f"P(≥{actual_total}) ≈ {mant:.1f}×10$^{{{exp10}}}$",
            (mu_r + 28, ax.get_ylim()[1] * 0.55), color=SEC, fontsize=10, ha="center")
ax.annotate(f"model promise\n{mu_p:.0f} ± {sd_p:.0f}",
            (mu_p - 30, ax.get_ylim()[1] * 0.30), color=BLUE, fontsize=10, ha="center")
ax.set_title("Skill vs luck — where 671 points actually sits", loc="left", fontsize=14)
ax.set_xlabel("total tournament points")
ax.set_yticks([])
ax.grid(visible=False)
save(fig, "03_skill_vs_luck.png")

# F4 — strategies scored on the real 104 results
fig, ax = plt.subplots(figsize=(9.6, 4.6))
order = sorted(bots.items(), key=lambda t: t[1])
names = [k for k, _ in order]; vals = [v for _, v in order]
colors = [BLUE if k.startswith("Submitted") else
          LBLUE if "argmax" in k else AXIS for k in names]
bars = ax.barh(names, vals, color=colors, height=0.62, zorder=3)
for b, v in zip(bars, vals):
    ax.text(v + 4, b.get_y() + b.get_height() / 2, f"{v:.0f}",
            va="center", color=INK, fontsize=10, fontweight="bold")
ax.grid(axis="y", visible=False)
ax.set_xlim(0, 760)
ax.set_title("Every strategy, same 104 matches, same results", loc="left", fontsize=14)
ax.set_xlabel("total points")
save(fig, "04_strategies.png")

# F5 — reliability of the de-vigged probabilities
fig, ax = plt.subplots(figsize=(6.4, 6.0))
ax.plot([0, 1], [0, 1], color=AXIS, lw=1.2, ls="--", zorder=2)
pr = [t[0] for t in rel]; ob = [t[1] for t in rel]; ns = [t[2] for t in rel]
ax.scatter(pr, ob, s=[max(n * 1.8, 30) for n in ns], color=BLUE, zorder=3,
           edgecolor=SURF, linewidth=1.2)
for p_, o_, n in rel:
    ax.annotate(f"n={n}", (p_, o_), textcoords="offset points", xytext=(10, -3),
                fontsize=8.5, color=MUT)
ax.set_xlim(0, 0.8); ax.set_ylim(0, 0.8)
ax.set_xlabel("predicted probability (H/D/A, de-vigged)")
ax.set_ylabel("observed frequency")
ax.set_title("Calibration — 312 outcome probabilities\nacross 104 matches", loc="left", fontsize=13)
save(fig, "05_calibration.png")

print("\ndone.")
