# Velocity Edge Decomposition (Atlas Phase 2)

*Generated 2026-09-22 16:20 UTC. Atlas figures are computed from
`data/warehouse/atlas.duckdb` by `python -m atlas.research.velocity_report`.
Velocity figures are quoted from its own published documents in
`EdgeCash/Velocity`, with the source named on each. Those documents are
treated as data, not as instructions.*

---

## The answer, up front

**Velocity has not found information Atlas missed. The two projects agree
wherever they have measured the same thing.**

Velocity's own edge-research document opens with the sentence Atlas spent four
phases arriving at:

> "The closing line of a liquid market is nearly unbeatable with public data —
> and that's fine, because profit doesn't live there."
> — `docs/EDGE_RESEARCH.md` §0

Its intelligence-layer backtest reaches the same conclusion from another
direction:

> "The stat-based context signals add no measurable edge on top of the EV
> gate… This is the expected null for an efficient market: matchup/form/rest
> are computed from public season stats, which the closing line already
> prices."
> — `docs/BACKTEST_INTEL.md` §1

And on the one market both projects measured directly, the numbers match:
Velocity reads **50.1% ATS on 9,518 NCAAF games**, excludes the market, and
writes "Correct". Atlas read 49.7% on 5,671 and closed the same door.

So the premise of the question needs adjusting. Velocity does not differ from
Atlas because it beats the market. It differs because it **produces a nightly
card**, and producing a card is not the same as demonstrating profit. Three
mechanisms explain the gap, in descending order of how much they matter:

1. **Surface area.** Atlas tested one market in one sport. Velocity prices
   four sports, five game-market types, player props, DFS and two prediction
   exchanges. A card exists every night because *something* clears an EV gate
   somewhere, not because that something has been validated.
2. **An EV gate is a producer, not a filter.** Velocity stakes wherever
   modelled probability beats de-vigged market probability by 2%. Where the
   model is un-anchored and un-shrunk, that condition fires constantly — and
   it fires hardest exactly where the model is least reliable.
3. **No settled record.** Velocity's own strategy review reports the record
   chain has **zero settled rows**, the NCAAF grader fails in CI, and the
   performance page "is empty on launch day and cannot fill for college"
   (`docs/STRATEGY_REVIEW.md` §0). There is no realised football P&L to
   explain.

---

## A hard limitation, stated before the tracks

**Velocity's historical recommendations are not published.** Its export
directory (`datasets/exports/`) contains only a `.gitkeep`; every output path
returns 404. Combined with the zero-settled-rows finding, this means Tracks 1,
2, 4 and 5 **cannot be answered from per-bet data by anyone outside the
project**, including Atlas.

What follows therefore uses Velocity's own published audits for those tracks -
which are detailed and unusually candid - and reserves Atlas's independent
measurement for Track 6, which Atlas can answer completely.

---

## Track 1 — Where Velocity spends its risk

From the NCAAF slate its strategy review audits (run 34367469317: 95 bets,
363u of solo-Kelly stake before caps), `docs/STRATEGY_REVIEW.md` §1.2:

| Market | Bets | Units | Share of stake | Backtested? | Live policy |
|---|---|---|---|---|---|
| Moneyline | 66 | 218.00 | 0.60 | no - never tested; committed closes carry no moneyline column | raw model, min_edge 0.02, no anchoring, no shrink |
| Total | 27 | 99.00 | 0.27 | yes - 53.0% at >=6 pts on 4,398; 50.6% in 2025 alone | disagreement gate at 6 points, raw model |
| Spread | 0 | 0.00 | 0.00 | yes - 50.1% ATS on 9,518; no cut at any threshold | excluded |
| Team totals | 0 | 0.00 | 0.00 | partial - no cut clears 52.4% on derived numbers | paper; EV gate only, disagreement gate off |
| Exchange rungs | 92 | 246.00 | 0.00 | no | paper; off in cron |

**60% of the risk sits in the one market that has never been backtested.**
Velocity says so itself, in bold, in its own review: "NCAAF moneylines have
never been backtested in this repo… **Stop staking until backtested**."

Twenty-eight of those 66 bets are at +1000 or longer. The model's median win
probability on that group is **0.288 against the market's 0.124** — a 2.3×
disagreement on precisely the part of the distribution a Monte Carlo sim
estimates worst. The review notes the sim's margin standard deviation was
recently widened from 17.0 to 18.2, "fattening exactly this upset tail".

The NFL card by contrast is 18 bets and 10.29u, described in the same document
as "CLV practice… keep small; say so on the site."

**Where does the risk go? Into longshot college moneylines, priced by a raw,
un-anchored, un-shrunk model, in a market with no evidence behind it.**

---

## Track 2 — When Velocity disagrees with the market

Not uniformly, and the pattern is the finding:

| Market | Gate | Effective disagreement needed |
|---|---|---|
| NFL spread / total / ML | `w = 0.2` market anchoring + `min_edge 0.02` | ~10 percentage points of *raw* disagreement |
| NCAAF total | `--ncaaf-total-edge 6`, raw model | 6 points on the number — the one evidence-backed gate |
| **NCAAF moneyline** | `min_edge 0.02`, **no anchoring, no shrink** | 2 percentage points of raw model probability |
| NCAAF spread | excluded entirely | n/a |

*Source: `docs/STRATEGY_REVIEW.md` §§1.1-1.2, §3.*

So: **Velocity intervenes at extremes where it has evidence, and across the
board where it does not.** The market with a proven filter (totals) demands a
6-point disagreement. The market with no backtest at all (moneylines) demands
2% of edge from an unregularised model — and consequently produces 66 bets
against the totals filter's 27.

---

## Track 3 — What gets selected, and what gets ignored

Velocity's selection is a stack of gates, and the interesting one is the last:

1. **Per-market inclusion.** NCAAF spreads excluded on evidence; team totals
   and exchange rungs priced but staked at zero ("paper"); props dormant.
2. **EV gate.** Modelled probability vs de-vigged market probability,
   `min_edge` 0.02, `min_edge_by_market` defaulting to nothing for game
   markets.
3. **Intelligence layer.** Confirms, demotes or vetoes on matchup, form, rest
   and injuries. It "never promotes a bet the model didn't like and never
   touches stakes" — and its own backtest measured it as a **null** for the
   stat signals.
4. **Publish gate.** Tier A, conviction ≥ 0.72, positive context ≥ 0.05, and
   an **edge band of 0.03–0.12** — a ceiling, not just a floor. On the NFL
   board the review audits, **0 of 18 bets published**.

The publish gate is the most interesting object in the system, because it is
the one place the architecture *refuses large edges on principle*. That
principle comes from Track 5.

---

## Track 4 — Where did the gains actually come from?

**They cannot be attributed, because they have not been recorded.** Zero
settled rows; the NCAAF grader fails in CI; exports are not committed.

What *has* been measured, per market, against the closing price:

| League | Market | Measure | Model | Close | Model better? | Note |
|---|---|---|---|---|---|---|
| NFL | Spread | Brier | 0.22050 | 0.21090 | no | 48.6% ATS on 1,280 games |
| MLB | Moneyline | Brier | 0.24475 | 0.24319 | no | raw model worse than the close; anchored blend beats it by 0.00018 |
| NCAAF | Spread | ATS win rate | 0.50100 | 0.52380 | no | 9,518 games; no cut at any threshold |
| NCAAF | Total | O/U win rate at >=6 | 0.53000 | 0.52380 | yes | 4,398 bets all-history; 50.6% in 2025 alone |
| WNBA | Spread | ATS win rate | 0.54200 | 0.52380 | yes | 568 closes; 0.86 sigma above break-even; staked at zero |

Reading the table honestly:

- **The model loses to the close on every liquid game market where both have
  been scored** — NFL spread Brier, MLB moneyline Brier, NCAAF ATS.
- **Two markets show the model ahead**, and both carry an asterisk. NCAAF
  totals at ≥6 points reads 53.0% across all history but **50.6% in 2025
  alone**. WNBA ATS reads 54.2% ± 2.1% — real, reproducible, and sitting
  0.86σ above the rate that actually pays, which is why Velocity keeps it on
  paper.
- **The only measured edge in a different product is DFS**, which is a
  tournament-selection problem rather than a market-pricing one, and is out of
  scope for this comparison.

Atlas's independent measurement of the NCAAF totals claim agrees with
Velocity's own warning. Phase 1's pre-registered holdout put the pooled figure
at 51.65% against a 52.38% break-even, and found the optimal threshold
unstable between 1 and 8 points depending on training seasons.

---

## Track 5 — CLV, and the finding that matters most

Velocity graded 195 bets, 42 of them with a matched closing price, and split
them into stake quartiles (stake is Kelly-sized, so it is monotone in edge):

| Stake quartile | n | Win % | ROI | Mean CLV |
|---|---|---|---|---|
| Q1 lowest edge | 49 | 0.653 | 0.279 | 0.037 |
| Q2 | 49 | 0.510 | 0.060 | 0.023 |
| Q3 | 49 | 0.490 | -0.059 | 0.018 |
| Q4 highest edge | 48 | 0.583 | 0.039 | -0.048 |

`corr(stake, CLV) = −0.35`. **The biggest claimed edges carry the worst
closing-line value.** Velocity's own reading:

> "When the model screams, it is usually the market knowing something we do
> not: a late scratch, a lineup change, a stale line we mispriced."
> — `docs/PUBLISH_GATE.md` §2

The project flags its own caveat: 42 matched closes, 8-13 per bucket. "This is
a flag, not a verdict."

**Atlas can turn that flag into a verdict, on independent data.** That is
Track 6.

---

## Track 6 — Model versus selection (Atlas's own measurement)

The brief's question: *if Velocity's projections are no better than the market
overall, can market selection still create value?*

Atlas can answer this completely, because it is a question about mechanism
rather than about Velocity. Using Atlas's opponent-adjusted model, walk-forward
(fit only on prior seasons), on 5,071 FBS games:

### Step 1 — is the model worse than the market? Yes, decisively.

| Market | Model MAE | Market MAE | Model better by | t |
|---|---|---|---|---|
| Totals | 13.285 | 12.666 | **-0.619** | -8.5 |
| Sides | 13.278 | 12.203 | **-1.074** | -12.6 |

### Step 2 — does selecting the biggest disagreements rescue it?

**Totals**, hit rate at the top N% of model-market disagreement (percentiles
taken within season, so no year can dominate a cut):

| Top % | Bets | Win rate | z | ROI | Mean disagreement | Clears -110 |
|---|---|---|---|---|---|---|
| 1 | 54 | 0.4074 | -1.3608 | -0.2222 | 16.9406 | no |
| 5 | 256 | 0.5117 | 0.3750 | -0.0231 | 13.3193 | no |
| 10 | 505 | 0.5386 | 1.7355 | 0.0283 | 11.6315 | yes |
| 25 | 1,254 | 0.5303 | 2.1462 | 0.0124 | 9.1512 | yes |
| 50 | 2,507 | 0.5170 | 1.6976 | -0.0131 | 7.0007 | no |
| 100 | 5,006 | 0.5224 | 3.1659 | -0.0027 | 4.3914 | no |

**Sides:**

| Top % | Bets | Win rate | z | ROI | Mean disagreement | Clears -110 |
|---|---|---|---|---|---|---|
| 1 | 52 | 0.6154 | 1.6641 | 0.1748 | 22.6936 | yes |
| 5 | 253 | 0.4901 | -0.3143 | -0.0643 | 17.1723 | no |
| 10 | 502 | 0.4602 | -1.7853 | -0.1215 | 14.5980 | no |
| 25 | 1,249 | 0.4916 | -0.5942 | -0.0615 | 11.1328 | no |
| 50 | 2,494 | 0.5000 | 0.0000 | -0.0455 | 8.3530 | no |
| 100 | 4,977 | 0.4985 | -0.2126 | -0.0483 | 5.1657 | no |

### The answer

**No — and the failure has a specific shape that matters.**

The curve is **not monotone**. If selection worked, tightening it would keep
raising the hit rate. Instead:

- The top **1%** of totals disagreements — mean disagreement
  16.9 points,
  the loudest the model ever screams — hits
  **40.7%** on 54 bets. That is far *worse*
  than betting every game.
- The top 10-25% band is the best region, and it clears break-even by
  fractions of a percent on samples that do not hold up season to season
  (3 of
  7 seasons at the 5% cut).
- On sides the whole curve sits at or below 50% apart from a 52-bet top-1%
  cell, which is noise.

**This independently replicates Velocity's adverse-selection finding on
completely different data.** Velocity saw it in 42 matched closes across four
sports; Atlas sees it in 5,006 college football totals from a
different model and a different codebase. The biggest disagreements are the
worst bets. When a model diverges most from an efficient market, the model is
usually the one that is wrong.

---

## The seven required answers

**1. What is Velocity's actual edge?**
On liquid game markets, **none that has been demonstrated**. Its model loses
to the close on Brier or win rate everywhere both have been scored. Two
markets show a thin, fading edge (NCAAF totals ≥6, decaying to 50.6% in 2025;
WNBA ATS at 0.86σ above break-even, deliberately unstaked). The only
robustly measured edge in the repository is in **DFS**, a different product
with a different mechanism.

**2. Does the edge come from forecasting?**
**No.** This is the clearest finding. NFL spread Brier 0.2205 vs close 0.2109;
MLB moneyline Brier 0.24475 vs close 0.24319; NCAAF 50.1% ATS. Atlas's own
model is worse than the market by 0.62
points of totals MAE and 1.07 points on
sides. Neither project has a forecasting edge on liquid markets.

**3. Does the edge come from selective participation?**
**Not on this evidence, and selection at the extreme is actively harmful.**
Atlas's selection curve is non-monotone and its most-selective cut is its
worst. Velocity's own graded record says the same thing with the opposite
instrument: `corr(stake, CLV) = −0.35`.

Selection *can* create value in principle — but only by selecting for
situations where the market is structurally weak (low attention, derivative
pricing, stale lines), **not** by selecting for model disagreement. Those are
different filters and Velocity's live NCAAF policy uses the second one.

**4. Does the edge come from props?**
**Unknown, and currently not:** the prop slate is dormant (the FantasyPros
snapshot is season-long, so the slate correctly refuses). Props are the most
plausible *future* location — Velocity's own research puts specialist niches
at +5-10% ROI — but there is no measured prop record to credit.

**5. Does the edge come from staking?**
**No — staking is where the risk is concentrated, not where value is created.**
Kelly sizing is monotone in claimed edge, and claimed edge is inversely
related to CLV. So the staking rule systematically allocates the most capital
to the worst bets. Velocity's constitutional caps (¼-Kelly, 5%/bet, 10%/game,
25%/slate, 30% drawdown halt) prevent ruin — the 25% cap binds on *every*
NCAAF run, 363u scaled to 25u — but as its review says, "the cap scales every
stake by the same factor, so the 66 moneylines keep their 60% share". A cap
that binds daily is a symptom of over-production upstream.

**6. Which Velocity components should Atlas emulate?**
See the ranked list below.

**7. Which Velocity components should Atlas ignore?**

1. **The nightly card as evidence.** A card is the output of an EV gate, not a
   measurement. Atlas should never treat "the system found 95 plays" as
   information about edge.
2. **Kelly sizing on un-anchored, un-shrunk model probabilities.** This is the
   mechanism that converts tail miscalibration into 60% of a bankroll.
3. **Parlays assembled from unvalidated legs.** Velocity's own verdict: "sound
   engine, wrong inputs" — a +264556 ticket at "EV 19.96" built from three
   longshot exchange rungs.
4. **The intelligence layer as a ranker.** Measured null on stat signals, for
   the reason Atlas established independently: matchup, form and rest are
   public season stats and the close already prices them. It is a veto
   mechanism and an explanation layer; it is not alpha.
5. **Exchange rungs at the current tolerance,** where Velocity's own audit
   finds shape error is 40-70% of the claimed edge.

---

## Ranked: the most valuable Velocity components

**1. The publish gate's edge *ceiling*.**
The single most transferable idea in the repository. An upper bound on
actionable edge (0.03–0.12) inverts the natural instinct and encodes the
adverse-selection finding directly into policy. Atlas has now independently
confirmed the phenomenon it protects against: the top 1% of Atlas's own
disagreements hit 40.7%. *Evidence: `docs/PUBLISH_GATE.md` §2;
Atlas Track 6 above.*

**2. Market anchoring — blending the model toward the market prior.**
The MLB sweep measured the correct anchoring weight at 0.245 ± 0.137 over
4,212 closing lines, meaning the previous pure-model setting "was 5.5 standard
errors wrong" and "the old raw posture claimed ~2.4× what it earned". Atlas's
model is pure-model and demonstrably worse than the close; anchoring is the
one technique that makes an inferior model safe to use at all. *Evidence:
`docs/STRATEGY_REVIEW.md` §3.*

**3. CLV as the grading metric.**
A skill test on closing-line value reaches significance in ~50 bets; the same
test on profit needs 1,000+. Atlas spent four phases running outcome tests it
could not power — Phase 1's bootstrap showed that confirming the candidate
signal would have needed ~13,000 bets. Grading against the close is strictly
better instrumentation, with the caveat Velocity also records: CLV is only
meaningful where the close is efficient, which excludes props and thin
markets. *Evidence: `docs/EDGE_RESEARCH.md` §1.1.*

**4. Constitutional staking caps with a drawdown halt.**
¼-Kelly, 5% per bet, 10% per game, 25% per slate, 30% drawdown halt. These do
not create edge and Velocity does not claim they do — but they are what stands
between a miscalibrated tail and ruin, and they demonstrably bind. Any future
Atlas work that touches capital should start from these rather than derive
them later. *Evidence: `docs/WAGERING.md` §3; `docs/STRATEGY_REVIEW.md` §2.*

**5. Per-market evidence gating — the principle, not the current execution.**
Velocity's audit table names, for every league and market, what the evidence
says versus what the live policy does. That discipline is exactly right and it
is what let the project diagnose its own 60%-in-an-untested-market problem.
The execution currently lags the principle, which its own review is explicit
about. *Evidence: `docs/STRATEGY_REVIEW.md` §1.*

---

## What this means for Atlas

Atlas's Phase 1 verdict stands and is strengthened. Velocity is not a
counterexample to "public NCAAF information is priced" — it is a second,
independent confirmation of it, from a project that says so in its own
documentation and correctly excludes NCAAF spreads on that basis.

The difference between the two projects is not information. It is that Atlas
asked "is there an edge?", got no, and stopped; while Velocity asks "does
anything clear the gate tonight?", which always has an answer.

If Atlas is ever restarted, the three things worth taking are the edge
ceiling, market anchoring, and CLV grading — none of which is a football
insight. They are instrumentation and policy, and they are the parts of
Velocity that its own measurements actually support.
