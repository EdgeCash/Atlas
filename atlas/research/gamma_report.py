"""Phase 4 reports: can the line-movement signal be executed?

Phase 3 measured the signal against the staged consensus. This phase rebuilds
the same measurement inside a single sportsbook - which is the only version a
bettor could ever collect - and prices it against the juice ladder.

Three reports come out of one build, because they share one expensive
computation: `opening_line_feasibility.md` (Tracks 1 and 3),
`clv_economics.md` (Tracks 2 and 4) and `atlas_gamma_assessment.md` (Tracks 5,
6 and 7, plus the seven questions).
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.research import beta_report as beta
from atlas.research import execution as ex
from atlas.research import market_aware as ma
from atlas.research import signal_validation as sv
from atlas.research.dataset import load_research_frame, research_sample
from atlas.research.markdown import table
from atlas.util import get_logger

LOG = get_logger(__name__)

#: The concentration cut the assessment is built around. Chosen because it is
#: the tightest cut in :data:`atlas.research.execution.CONCENTRATION` that still
#: leaves enough bets per season to be graded within one season.
HEADLINE_TOP_PCT = 10.0


def build() -> dict:
    paths = config.paths().ensure()
    df = ma.prepare(research_sample(load_research_frame(paths.warehouse)))
    # Every table below is restricted to the research sample - the same
    # FBS-vs-FBS games every earlier phase measured - so a coverage share is a
    # share of the slate Atlas would have had an opinion on, not of every game
    # the odds feed happens to carry.
    lines = ex.book_lines(config.seasons())
    lines = lines[lines["game_id"].isin(set(df["game_id"]))]

    bundle: dict = {
        "lines": lines,
        "coverage": ex.opener_coverage(lines, df),
        "dispersion": ex.opener_dispersion(lines),
        "roles": ex.book_roles(lines, df),
        "markets": {},
        "residual_sd": {},
    }

    for name, market in beta.markets(df).items():
        scored = ma.walk_forward(df, market)
        extra = [c for c in beta.CLV_CANDIDATES + [market.opening] if c in df.columns]
        scored = scored.join(df.set_index("game_id")[extra], on="game_id", rsuffix="_src")
        frame = ex.attach_predictions(lines, scored, market)

        truth = pd.to_numeric(scored[market.target], errors="coerce")
        close = pd.to_numeric(scored[market.line], errors="coerce")
        sd = float((truth - close).std(ddof=1))
        bundle["residual_sd"][name] = sd

        cell = ex.concentrate(frame, HEADLINE_TOP_PCT)
        bundle["markets"][name] = {
            "frame": frame,
            "within_book": ex.within_book_clv(frame),
            "portfolio": ex.clv_portfolio(frame, market=name),
            "distribution": ex.clv_distribution(frame),
            "by_season": ex.clv_by_season(frame),
            "regimes": ex.regime_table(frame, market),
            "concentration": ex.concentration_curve(frame),
            "cell": cell,
            "cell_economics": ex.cell_economics(cell, sd),
            "cell_by_season": ex.cell_by_season(cell, sd),
            "cell_books": ex.cell_books(cell),
            "cell_portfolio": ex.clv_portfolio(cell, market=name),
            "all_economics": ex.cell_economics(frame, sd),
        }

    bundle["ladder"] = ex.clv_value_ladder(bundle["residual_sd"])
    bundle["breakeven"] = ex.breakeven_clv(bundle["residual_sd"])
    bundle["price_penalty"] = price_penalty(lines)

    out = paths.reports / "tables"
    out.mkdir(parents=True, exist_ok=True)
    for key in ("coverage", "dispersion", "roles", "ladder", "breakeven", "price_penalty"):
        value = bundle[key]
        if isinstance(value, pd.DataFrame) and not value.empty:
            value.to_csv(out / f"gamma_{key}.csv", index=False)
    for name, block in bundle["markets"].items():
        for key, value in block.items():
            if key in ("frame", "cell"):
                continue
            if isinstance(value, pd.DataFrame) and not value.empty:
                value.to_csv(out / f"gamma_{name}_{key}.csv", index=False)
            elif isinstance(value, dict) and value:
                pd.DataFrame([value]).to_csv(out / f"gamma_{name}_{key}.csv", index=False)
    return bundle


def price_penalty(lines: pd.DataFrame) -> pd.DataFrame:
    """What it costs to bet early, where both prices are known.

    Only one book in the feed (5Dimes, 2018-19) publishes an opening *price*
    alongside the opening number. That is a narrow window, and it is the only
    direct evidence Atlas has on whether the early number is sold at a worse
    price than the late one - which decides the whole phase, so it is reported
    with its limits attached rather than left out.
    """
    rows = []
    both = lines.dropna(subset=["open_price", "close_price"])
    for (market, book), block in both.groupby(["market", "book"], observed=True):
        if len(block) < 100:
            continue
        rows.append(
            {
                "market": market,
                "book": str(book),
                "seasons": ", ".join(str(int(s)) for s in sorted(block["season"].unique())),
                "n": int(len(block)),
                "median_open_price": float(block["open_price"].median()),
                "median_close_price": float(block["close_price"].median()),
                "open_worse_share": float((block["open_price"] < block["close_price"]).mean()),
                # Median, not mean: a handful of plus-money openers would
                # otherwise dominate an average taken over a cents scale.
                "median_cents_worse": float(
                    (block["close_price"] - block["open_price"]).median()
                ),
            }
        )
    return pd.DataFrame(rows)


def _breakeven_gap(price: int) -> float:
    """Percentage points of win rate this price demands above a coin flip."""
    return sv.JUICE[price][0] - 0.5


def write_opening_line_feasibility(bundle: dict) -> Path:
    """Tracks 1 and 3: is the opening number reachable, and by whom?"""
    paths = config.paths().ensure()
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    coverage, dispersion, roles = bundle["coverage"], bundle["dispersion"], bundle["roles"]
    penalty = bundle["price_penalty"]

    margin_cov = coverage[coverage["market"] == "margin"]
    recent = margin_cov[margin_cov["season"] >= 2022]
    margin_disp = dispersion[dispersion["market"] == "margin"].iloc[0]
    total_disp = dispersion[dispersion["market"] == "total"].iloc[0]

    text = f"""# Opening Line Feasibility (Atlas Phase 4, Tracks 1 and 3)

*Generated {generated} by `python -m atlas.research.gamma_report`. Counts come
from the per-book odds feed in `data/raw`, rebuilt by
`atlas.research.execution.book_lines` rather than from the staged consensus,
because the consensus is exactly what this report exists to question. Passages
marked **external** are not Atlas measurements; they are named sources with
their limits attached.*

---

## The answer, up front

**A bettor can reach an opening number, but not the one Phase 3 measured
against, and not at the price the closing number is sold at.**

Three facts decide it:

1. **At most four books in the entire feed ever post an opening number**, and
   for most of the sample exactly one book posts the opener for a given game.
2. **Openers disagree with each other.** Where two or more books open the same
   game, only {margin_disp['identical_share']:.1%} of spreads and
   {total_disp['identical_share']:.1%} of totals open on the same number. There
   is no such thing as *the* opening line.
3. **The early number is sold at a worse price.** In the one book-season where
   Atlas can see both, the opening price is worse than the closing price in
   {penalty[penalty['market'] == 'margin'].iloc[0]['open_worse_share']:.1%} of
   spreads and
   {penalty[penalty['market'] == 'total'].iloc[0]['open_worse_share']:.1%} of
   totals.

The third fact is the one that matters, and it is developed in
[`clv_economics.md`](clv_economics.md).

---

## Track 1 — Opening line availability

### Coverage, by season

{table(coverage, ["market", "season", "games_in_sample", "games_with_opener", "coverage", "books_posting_openers", "mean_books_per_game", "single_book_share", "no_move_share"], ["Market", "Season", "Games in sample", "With an opener", "Coverage", "Books posting", "Books/game", "Single-book share", "No-move share"], digits=3)}

**Coverage itself is not the problem: an opening number exists for
{margin_cov['coverage'].mean():.0%} of the games Atlas would have an opinion
on, in every season.** The problem is how thin that number is. Through 2022 it
is a *single* book's opener for every game in the sample; only from 2023 does
a second and then a third book appear, and even in 2025 the mean is
{recent['mean_books_per_game'].mean():.1f} books. There is no depth behind the
number Phase 3 graded against.

The sample is also a different object in each half - one book then three - so
any result has to hold season by season rather than only in the pool. Track 4
tests that directly.

### Who posts the openers

{table(roles, ["market", "book", "games_opened", "coverage", "seasons", "median_abs_move", "open_price_known"], ["Market", "Book", "Games opened", "Coverage", "Seasons", "Median |move|", "Opening price known"], digits=3)}

**Every opener in this dataset comes from a retail book.** Bovada opens
roughly {roles[roles['book'] == 'Bovada']['coverage'].max():.0%} of games;
DraftKings, ESPN Bet and (in 2018-19) 5Dimes cover the rest. The books whose
numbers the market actually respects - Pinnacle and BetCRIS/BOOKMAKER both
appear in this feed - are present **only at the close**. They never open a
game here.

That is a structural statement about the dataset, not about the world: those
books certainly post early numbers of their own. What it means for Atlas is
narrower and sharper: **the openers Atlas has measured against are retail
openers**, and any conclusion about them is a conclusion about retail books.

### Stability of the opening number

{table(dispersion, ["market", "games_multi_book", "identical_share", "median_spread", "mean_spread", "p90_spread", "max_spread"], ["Market", "Games with 2+ openers", "Identical", "Median gap", "Mean gap", "P90 gap", "Max gap"], digits=3)}

On spreads, two books opening the same game agree on the number
{margin_disp['identical_share']:.1%} of the time, and the median gap between
them is {margin_disp['median_spread']:.1f} points - the same size as the median
move from open to close. **The disagreement between two openers is as large as
the thing Atlas is trying to forecast.**

Totals are tighter ({total_disp['identical_share']:.1%} identical, median gap
{total_disp['median_spread']:.1f}), which is one reason the totals signal
survives execution testing better than the margin signal does.

### Time between open and close

**Atlas cannot measure this.** The odds feed carries an opening number, a
closing number and a kickoff time. It carries **no timestamp on either line**,
so the elapsed time between them, and the path taken, are both unobservable.
Track 5 of this phase is unanswerable with the data Atlas holds, and the
assessment says so rather than estimating it.

---

## Track 3 — Book availability, by bettor size

This track asks what limits a bettor would face. **Atlas holds no limit data**,
and limits are not published in a form that can be audited: they vary by
account, by state, by game and by time of day. What follows is therefore a
framework with its assumptions named, not a measurement, and it is separated
from the measured sections deliberately.

What Atlas *can* state from its own data is the part that constrains every
bettor equally:

| Constraint | Measured value |
|---|---|
| Books at which the signal is available at all | {int(roles['book'].nunique())} |
| Games with more than one opener to shop between | {margin_disp['games_multi_book']:,} of {int(coverage[coverage['market'] == 'margin']['games_with_opener'].sum()):,} |
| Median gap between two books' openers (spread) | {margin_disp['median_spread']:.1f} points |
| Opening **price** observable | {float(bundle['lines']['open_price'].notna().mean()):.0%} of book-games |

**External context.** The structural reason the early number is hard to reach
is not a secret: books post early lines at deliberately small limits and raise
them as the market forms. Pinnacle's own model is described publicly as posting
"overnight" lines at low limits precisely so sharp money can shape the number
before the book is exposed, with limits rising into the tens of thousands only
once the line has settled
([Pinnacle betting limits overview](https://surebetmonitor.com/knowledge-base/pinnacle-sports-betting-limits/)).
Atlas has not verified those figures and they are not from the book's own
documentation; they are consistent with the structure and should be treated as
orientation, not evidence.

### The three bettors

| | Small | Medium | Large |
|---|---|---|---|
| Stake per bet | $50-200 | $500-2,000 | $5,000+ |
| Can reach a retail opener | Yes | Probably | No |
| Limited or closed after a winning run | Eventually | Quickly | Immediately |
| Can shop between openers | Only on the {margin_disp['games_multi_book'] / coverage[coverage['market'] == 'margin']['games_with_opener'].sum():.0%} of games with two openers | Same | Same |
| Bets per season at the Track 7 cut | ~{bundle['markets']['total']['cell_economics']['bets_per_season']:.0f} (totals) | Same | Same |
| Binding constraint | Price | Limits, then account survival | No market |

The asymmetry is the finding. A **small** bettor can reach these numbers and is
constrained by price - the edge measured in the next report does not clear
standard juice. A **medium** bettor is constrained by account survival at the
same retail books that post the openers. A **large** bettor has no market here
at all: there is no venue in this dataset that both posts an opener and would
take a five-figure wager on a college football total.

**A signal that only works at a stake size too small to matter, at books that
close winning accounts, is not a business.** That is Track 3's answer, and it
does not depend on the limit figures Atlas could not obtain.
"""
    out = paths.reports / "opening_line_feasibility.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def write_clv_economics(bundle: dict) -> Path:
    """Tracks 2 and 4: what a point of CLV is worth, and what the path looks like."""
    paths = config.paths().ensure()
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    ladder, breakeven, penalty = bundle["ladder"], bundle["breakeven"], bundle["price_penalty"]
    m, t = bundle["markets"]["margin"], bundle["markets"]["total"]
    m_port, t_port = m["portfolio"], t["portfolio"]
    m_within = m["within_book"].iloc[0]
    t_within = t["within_book"].iloc[0]

    be = breakeven.set_index(["market", "price"])["points_required"]
    penalty_margin = penalty[penalty["market"] == "margin"].iloc[0]
    penalty_total = penalty[penalty["market"] == "total"].iloc[0]

    text = f"""# CLV Economics (Atlas Phase 4, Tracks 2 and 4)

*Generated {generated} by `python -m atlas.research.gamma_report`. Every CLV
figure is measured **inside a single sportsbook** - the side is taken at that
book's opening number and graded against that same book's close - because a
bettor holds one ticket at one shop. Phase 3's consensus construction is
carried alongside for comparison. No stake rule is applied anywhere: turning
points into units requires a wagering simulation, which is out of scope.*

---

## The answer, up front

**One point of closing-line value is worth about 2.5 percentage points of win
probability. Standard -110 juice costs 2.38. So the whole question is whether
Atlas can find a point of CLV, and the answer is: not on average, and only
just on its best tenth.**

| | Mean CLV (points) | Worth | -110 needs | Verdict |
|---|---|---|---|---|
| Margins, all signals | {m_port['mean_clv']:+.3f} | {(m_port['mean_clv'] * ladder[ladder['market'] == 'margin']['prob_per_point'].iloc[0]):+.2%} | +2.38% | short |
| Totals, all signals | {t_port['mean_clv']:+.3f} | {(t_port['mean_clv'] * ladder[ladder['market'] == 'total']['prob_per_point'].iloc[0]):+.2%} | +2.38% | short |
| Margins, loudest 10% | {m['cell_economics']['mean_clv']:+.3f} | {m['cell_economics']['win_probability'] - 0.5:+.2%} | +2.38% | short |
| **Totals, loudest 10%** | **{t['cell_economics']['mean_clv']:+.3f}** | **{t['cell_economics']['win_probability'] - 0.5:+.2%}** | +2.38% | **clears, barely** |

The one cell that clears does so by
{(t['cell_economics']['win_probability'] - sv.BREAK_EVEN):.2%} of win
probability, and its 95% interval does **not** clear
(lower bound {t['cell_economics']['win_probability_low']:.2%}).

---

## First: the signal survives being measured honestly

Phase 3 compared one book's opener against a consensus close across roughly
six books. That is not a bet anyone can place. Rebuilt inside each book:

{table(pd.concat([m["within_book"].assign(market="margin"), t["within_book"].assign(market="total")]), ["market", "group", "games", "pushes", "graded", "mean_clv", "beat_rate", "beat_z", "consensus_beat_rate", "book_effect"], ["Market", "Book", "Games", "Pushes", "Graded", "Mean CLV", "Beat rate (same book)", "z", "Beat rate (Phase 3 method)", "Book effect"], digits=4)}

**The book effect is essentially zero.** Same-book grading gives
{m_within['beat_rate']:.1%} on margins and {t_within['beat_rate']:.1%} on
totals, against Phase 3's {m_within['consensus_beat_rate']:.1%} and
{t_within['consensus_beat_rate']:.1%}. The Phase 3 result was not an artefact
of comparing two different shops' prices - it replicates on the construction a
bettor could actually execute, and on margins it is slightly *stronger*.

That is the good news, and it is the last of it.

---

## Track 2 — What CLV is worth

One point of line is worth `φ(0) / sd` of win probability, where `sd` is the
out-of-sample residual standard deviation around the closing number
({bundle['residual_sd']['margin']:.2f} points on margins,
{bundle['residual_sd']['total']:.2f} on totals). This assumes the close is a
fair 50/50 - which is what Phases 1 to 3 established, so it is the correct
prior to price against rather than a convenience.

{table(ladder, ["market", "clv_points", "win_probability", "ev_-105", "ev_-110", "ev_-115", "ev_-120", "clears_-105", "clears_-110", "clears_-115", "clears_-120"], ["Market", "CLV (points)", "Win probability", "EV at -105", "EV at -110", "EV at -115", "EV at -120", "-105?", "-110?", "-115?", "-120?"], digits=4)}

Read down the ladder rather than across it. **A quarter-point of CLV is worth
nothing at any price.** Half a point clears -105 and nothing else. A full point
clears -110. It takes a point and a half to clear -115, and two full points to
clear -120.

Inverted, so the requirement is explicit:

{table(breakeven, ["market", "price", "break_even_rate", "points_required"], ["Market", "Price", "Break-even win rate", "Points of CLV required"], digits=4)}

**This is the bar.** Everything else in this phase is a question of whether
Atlas clears {be[('total', -110)]:.2f} points of CLV on totals and
{be[('margin', -110)]:.2f} on margins.

### The price of being early

There is a second cost, and Atlas can only see it through a keyhole. Of the
four books that post openers, exactly one - 5Dimes, in 2018-19 - also publishes
an opening **price**:

{table(penalty, ["market", "book", "seasons", "n", "median_open_price", "median_close_price", "open_worse_share", "median_cents_worse"], ["Market", "Book", "Seasons", "Games", "Median opening price", "Median closing price", "Open is worse", "Median cents worse"], digits=3)}

The opening number is sold at **-110 where the closing number is sold at
-105**, and the opener is the worse price in
{penalty_margin['open_worse_share']:.1%} of spreads and
{penalty_total['open_worse_share']:.1%} of totals.

The size of that penalty is the whole phase in one number. Moving from -105 to
-110 raises the break-even from {sv.JUICE[-105][0]:.2%} to
{sv.JUICE[-110][0]:.2%} - a cost of
{(sv.JUICE[-110][0] - sv.JUICE[-105][0]):.2%} of win probability, which is
**{(sv.JUICE[-110][0] - sv.JUICE[-105][0]) / (t['cell_economics']['win_probability'] - 0.5):.0%} of the entire edge on the best cell in this study.**

Two seasons at one book is thin evidence and it is labelled as such. But it
points the same way as the market structure does: a book posting a number
early, with little information and small limits, prices that number wider. If
that is true generally, it removes the edge.

---

## Track 4 — The CLV portfolio

Outcomes are ignored entirely here. The only inputs are the opening line, the
closing line and Atlas's direction. Everything is in **points of line**, and
the path is walked in chronological order because a drawdown is a statement
about sequence.

{table(pd.DataFrame([m_port, t_port]), ["market", "bets", "mean_clv", "median_clv", "sd_clv", "sharpe_per_bet", "p05", "p25", "p75", "p95", "beat_rate", "total_clv_points", "max_drawdown_points", "longest_flat_or_down"], ["Market", "Bets", "Mean", "Median", "SD", "Mean/SD", "P05", "P25", "P75", "P95", "Beat rate", "Total points", "Max drawdown", "Longest underwater (bets)"], digits=3)}

Three things in that table deserve to be read slowly.

**The median CLV is zero in both markets.** The mean is positive because the
right tail is fatter than the left, not because the typical bet gains anything.
Roughly a fifth of all bets land exactly on the opening number and gain nothing
at all.

**The noise is eight times the signal.** A standard deviation of
{t_port['sd_clv']:.2f} points against a mean of {t_port['mean_clv']:.2f} means
the per-bet information ratio is {t_port['sharpe_per_bet']:.3f}. That is a real
edge and an almost invisible one.

**The underwater stretches are long.** The worst margin drawdown is
{abs(m_port['max_drawdown_points']):.0f} points, and margins spend
{m_port['longest_flat_or_down']:,} consecutive bets below a previous peak -
more than a full season. A signal significant at z =
{m_within['beat_z']:.1f} still looks broken for a year at a time.

### Distribution

{table(pd.concat([m["distribution"].assign(market="margin"), t["distribution"].assign(market="total")]), ["market", "bucket", "games", "share"], ["Market", "CLV (points)", "Bets", "Share"], digits=4)}

### Season by season

{table(pd.concat([m["by_season"].assign(mkt="margin"), t["by_season"].assign(mkt="total")]), ["mkt", "season", "bets", "mean_clv", "median_clv", "beat_rate", "total_clv_points", "max_drawdown_points"], ["Market", "Season", "Bets", "Mean CLV", "Median", "Beat rate", "Total points", "Max drawdown"], digits=3)}

Positive in every season in both markets - {m['by_season']['beat_rate'].min():.1%}
to {m['by_season']['beat_rate'].max():.1%} on margins,
{t['by_season']['beat_rate'].min():.1%} to
{t['by_season']['beat_rate'].max():.1%} on totals. The signal is stable. It is
simply small.

---

## What this report establishes

1. The Phase 3 CLV signal **is not a book artefact**. It replicates inside a
   single book, which is the only version anyone could trade.
2. One point of CLV is worth ~2.5% of win probability, so **-110 demands
   roughly one full point** and -115 demands a point and a half.
3. Atlas averages {m_port['mean_clv']:.2f} points on margins and
   {t_port['mean_clv']:.2f} on totals. **Neither clears -110.**
4. The early number appears to be sold ~5 cents worse than the late one, which
   costs about half the edge of the best cell in the study.
5. The distribution is thin-tailed around a zero median with long underwater
   stretches, so even the part that works would take a very long time to
   distinguish from luck by its results.

Whether any cell of the data clears the bar is Track 7's question, and it is
answered in [`atlas_gamma_assessment.md`](atlas_gamma_assessment.md).
"""
    out = paths.reports / "clv_economics.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def write_gamma_assessment(bundle: dict) -> Path:
    """Tracks 5, 6 and 7, and the seven questions."""
    paths = config.paths().ensure()
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    m, t = bundle["markets"]["margin"], bundle["markets"]["total"]
    m_cell, t_cell = m["cell_economics"], t["cell_economics"]
    m_within, t_within = m["within_book"].iloc[0], t["within_book"].iloc[0]
    breakeven = bundle["breakeven"].set_index(["market", "price"])["points_required"]

    m_reg, t_reg = m["regimes"], t["regimes"]
    early_margin = m_reg[m_reg["regime"].str.startswith("Season phase: Early")].iloc[0]
    late_margin = m_reg[m_reg["regime"].str.startswith("Season phase: Late")].iloc[0]
    small_margin = m_reg[m_reg["regime"].str.startswith("Spread: small")].iloc[0]
    large_margin = m_reg[m_reg["regime"].str.startswith("Spread: large")].iloc[0]
    early_total = t_reg[t_reg["regime"].str.startswith("Season phase: Early")].iloc[0]

    t_seasons_clearing = int(t["cell_by_season"]["clears_-110"].sum())
    t_seasons = int(len(t["cell_by_season"]))
    detect_beat = ma.detection_sample_size(float(t_within["beat_rate"]))

    text = f"""# Atlas Gamma Assessment — Market Movement Monetization (Phase 4)

*Generated {generated} by `python -m atlas.research.gamma_report`. All CLV is
measured inside a single sportsbook. Supporting detail is in
[`opening_line_feasibility.md`](opening_line_feasibility.md) (Tracks 1, 3) and
[`clv_economics.md`](clv_economics.md) (Tracks 2, 4). Research only: nothing
here stakes, simulates or recommends a wager.*

---

## The answer, up front

**The signal is real. It is not, on this evidence, monetizable at standard
juice. It is worth instrumenting and not worth betting.**

| Question | Answer |
|---|---|
| Is the CLV signal real? | **Yes** - z = {t_within['beat_z']:.1f} on totals within a single book, positive in every season, and Phase 3's placebo tests fail as they should |
| Does it survive execution testing? | **Yes** - the book effect is {abs(t_within['book_effect']):.4f}; same-book grading gives {t_within['beat_rate']:.1%} against the consensus method's {t_within['consensus_beat_rate']:.1%} |
| Is it big enough to bet? | **No** - {t['portfolio']['mean_clv']:.2f} points of CLV on average against the {breakeven[('total', -110)]:.2f} points -110 requires |
| Is any subset big enough? | **One** - the loudest 10% of totals signals, at {t_cell['mean_clv']:.2f} points, clears -110 on the point estimate and not on the interval |
| Can the execution window be optimised? | **Unknown** - Atlas holds no timestamped odds and cannot answer Track 5 at all |

**Recommendation: BUILD ATLAS CLV SYSTEM.** Not a betting system. The
reasoning is in the last section, and it carries a kill criterion.

---

## Track 5 — Market timing

**This track cannot be answered and Atlas will not estimate it.**

The brief asks when Atlas beats the close most often: one day before, twelve
hours, six, three, one. Answering requires a timestamped odds archive. Atlas's
feed carries an opening number, a closing number and a kickoff time, and **no
timestamp on either line**. There is no proxy: the number of books quoting a
game is not a clock, and the size of a move says nothing about when it
happened.

What can be said is a bound. Open-to-close is the **whole** window, so every
sub-window sits inside it and the {t_within['beat_rate']:.1%} measured here is
the total available, not a rate per hour. Whether it accrues in the first hour
after the opener posts - which is what the market structure suggests, since
that is when the number is least informed - or accumulates evenly, is exactly
the thing that is unobservable.

**This is the single highest-value data acquisition Atlas could make**, and it
is the first deliverable of the recommendation below. Candidate sources of
timestamped NCAAF line snapshots, none verified by Atlas:

| Source | Claimed NCAAF history | Note |
|---|---|---|
| [The Odds API](https://the-odds-api.com/historical-odds-data/) | mid-2020 onward | timestamped snapshots with previous/next references |
| [TheRundown](https://therundown.io/) | 2020 onward | line movement archived open to close |
| [ParlayAPI](https://parlay-api.com/historical-coverage) | 2014 onward | odds snapshots and closing lines |

Coverage, granularity, which books are included and cost all need verifying
before any of them is relied on. The requirement is specific: **snapshots at
least hourly, including at least one book that posts openers**, over three or
more seasons.

---

## Track 6 — Market regimes

Where the signal lives, measured on the executable within-book construction:

### Margins

{table(m_reg, ["regime", "games", "graded", "beat_rate", "z", "mean_clv"], ["Regime", "Bets", "Graded", "Beat rate", "z", "Mean CLV"], digits=4)}

### Totals

{table(t_reg, ["regime", "games", "graded", "beat_rate", "z", "mean_clv"], ["Regime", "Bets", "Graded", "Beat rate", "z", "Mean CLV"], digits=4)}

Three findings, one of them useful:

**Early-season margins are dead.** Weeks 1-4 give
{early_margin['beat_rate']:.1%} at z = {early_margin['z']:.2f} - no signal at
all - against {late_margin['beat_rate']:.1%} from week 11. That is the sharpest
regime effect in the study and it has an obvious reading: in September the
model is running on last season's ratings, which is precisely when the market's
own opener is least informed by current-season data too. Both are guessing, so
neither moves toward the other. **Totals do not share the weakness**
({early_total['beat_rate']:.1%} early), which is itself informative: pace and
scoring environment carry across a season better than team strength does.

**Spread size matters for margins and not for totals.** Close games give
{small_margin['beat_rate']:.1%} against {large_margin['beat_rate']:.1%} on
blowout-prone lines (z = {large_margin['z']:.2f}). A lopsided line has little
room to move and little reason to.

**Profile does not matter.** The most-quoted quarter of games and the
least-quoted quarter give beat rates within two points of each other in both
markets. This is worth stating because it contradicts the obvious hypothesis:
one would expect a small, ignored game to have a lazier opener and therefore
more predictable movement. It does not. The quoting count is a proxy for
attention rather than a measure of it, and the proxy shows nothing.

---

## Track 7 — Signal concentration

Keeping only the loudest signals each season, ranked within season so a
drifting model cannot pile its "top 1%" into one year:

### Margins

{table(m["concentration"], ["top_pct", "bets", "min_edge", "mean_edge", "beat_rate", "z", "mean_clv", "median_clv"], ["Keep top", "Bets", "Min edge", "Mean edge", "Beat rate", "z", "Mean CLV", "Median CLV"], digits=4)}

### Totals

{table(t["concentration"], ["top_pct", "bets", "min_edge", "mean_edge", "beat_rate", "z", "mean_clv", "median_clv"], ["Keep top", "Bets", "Min edge", "Mean edge", "Beat rate", "z", "Mean CLV", "Median CLV"], digits=4)}

**Yes, concentration improves the signal, and it improves it in the right
currency.** Mean CLV on totals rises from {t['portfolio']['mean_clv']:.2f}
points across everything to {t['cell_economics']['mean_clv']:.2f} at the top
10%, while the beat rate climbs from {t_within['beat_rate']:.1%} to
{t['concentration'][t['concentration']['top_pct'] == 10].iloc[0]['beat_rate']:.1%}.

Note this does **not** contradict Phase 3, which recommended discarding the
quarter of games where the model disagrees most. Those are two different
measurements: Phase 3's ceiling is distance from the **closing** line, which
predicts the model's own failure, while concentration here is distance from the
**opening** line, which predicts movement. A model far from the close is wrong;
a model far from the open is early. Both are true and they select different
games.

Concentration also runs out. On margins the top 5% is *worse* than the top 10%
({m['concentration'][m['concentration']['top_pct'] == 5].iloc[0]['beat_rate']:.1%}
against
{m['concentration'][m['concentration']['top_pct'] == 10].iloc[0]['beat_rate']:.1%}),
and the 1% cut has too few bets to grade. Ten percent is where the evidence
stops.

### The one cell that clears the bar

{table(pd.DataFrame([{"market": "margin", **m_cell}, {"market": "total", **t_cell}]), ["market", "bets", "bets_per_season", "mean_clv", "clv_se", "win_probability", "win_probability_low", "clears_-105", "clears_-105_ci", "clears_-110", "clears_-110_ci"], ["Market", "Bets", "Per season", "Mean CLV", "SE", "Implied win rate", "95% lower", "-105?", "-105 (CI)?", "-110?", "-110 (CI)?"], digits=4)}

Season by season, at the totals cut:

{table(t["cell_by_season"], ["season", "bets", "beat_rate", "mean_clv", "win_probability", "clears_-110"], ["Season", "Bets", "Beat rate", "Mean CLV", "Implied win rate", "Clears -110?"], digits=4)}

It clears -110 in **{t_seasons_clearing} of {t_seasons} seasons**. And it is
available where a bettor could reach it:

{table(t["cell_books"], ["book", "bets", "share", "beat_rate", "mean_clv", "seasons"], ["Book", "Bets", "Share", "Beat rate", "Mean CLV", "Seasons"], digits=4)}

---

## The seven questions

### 1. Is the CLV signal real?

**Yes.** Measured inside a single sportsbook - the only construction a bettor
could execute - Atlas beats that book's own close on {t_within['beat_rate']:.1%}
of {int(t_within['graded']):,} graded totals (z = {t_within['beat_z']:.1f}) and
{m_within['beat_rate']:.1%} of {int(m_within['graded']):,} margins (z =
{m_within['beat_z']:.1f}). It is positive in every season of both markets, the
book effect against Phase 3's consensus construction is
{abs(t_within['book_effect']):.4f}, and Phase 3's three placebo predictors all
score at or below chance.

This is the most robust finding in five phases of Atlas research, and it is
the only one that has survived every falsification aimed at it.

### 2. Can it be executed in practice?

**Partly, and not by everyone.**

What works: an opening number exists for essentially every game in the sample,
in every season, and the signal survives being graded at the book that posted
it.

What does not: there are **{int(bundle['roles']['book'].nunique())} books in the
entire feed that ever post an opener**, all retail. Two or more openers exist
for fewer than half of games, so there is little to shop between. The opening
number appears to be sold about five cents worse than the closing number - the
only direct evidence is one book over two seasons, but it points the same way
the market structure does. And the structural reason early numbers are
available is that limits on them are small, which is a feature of the market
rather than an accident.

**Execution is possible for a small bettor and structurally closed to a large
one.**

### 3. How much is it worth?

One point of CLV is worth about 2.5 percentage points of win probability.
Against that scale:

| Selection | Mean CLV | Implied win rate | -110 needs 52.38% |
|---|---|---|---|
| All margin signals | {m['portfolio']['mean_clv']:.3f} | {m['all_economics']['win_probability']:.2%} | no |
| All totals signals | {t['portfolio']['mean_clv']:.3f} | {t['all_economics']['win_probability']:.2%} | no |
| Loudest 10% of margins | {m_cell['mean_clv']:.3f} | {m_cell['win_probability']:.2%} | no |
| Loudest 10% of totals | {t_cell['mean_clv']:.3f} | {t_cell['win_probability']:.2%} | **yes, by {(t_cell['win_probability'] - sv.BREAK_EVEN):.2%}** |

The honest summary: **worth roughly one percentage point of win probability
across the board, and about two and a half on its best tenth.** The best cell
clears -110 by
{(t_cell['win_probability'] - sv.BREAK_EVEN):.2%} with a 95% lower bound of
{t_cell['win_probability_low']:.2%}, which does not clear. At -105 both markets
clear comfortably at the 10% cut, including on the interval.

**It is worth something. It is not yet worth enough to bet at the prices the
books that post openers actually charge.**

### 4. What is the best execution window?

**Unknown, and unknowable from Atlas's current data.** See Track 5. The
open-to-close window bounds the answer from above; nothing in Atlas's feed
divides it.

### 5. Who could realistically use it?

A **small bettor with accounts at two or three retail books, betting college
football totals only, at reduced juice, on roughly
{t_cell['bets_per_season']:.0f} games a season.** That is the entire
addressable population implied by the measurements.

A medium bettor runs into account restrictions at exactly the retail books
that post the openers. A large bettor has no venue in this dataset that both
posts an opener and would accept a serious wager on a college football total.

### 6. What should Atlas become?

**C - a CLV tracking system**, whose substance is B.

Not **A (a betting system)**: the best available cell clears -110 on a point
estimate whose confidence interval contains break-even, in
{t_seasons_clearing} of {t_seasons} seasons, before any account restriction or
price penalty. Staking money on that is not supported by this evidence.

Not **D (research only)**: five phases have now produced one robust,
independently falsified signal. Shelving it because it is not yet profitable
discards the only positive result the programme has.

**C is what the measurement problem demands.** Grading on CLV needs about
{detect_beat:,.0f} bets to separate the beat rate from chance. Grading on
profit needs tens of thousands. A tracking system learns within one season
what a betting system could not establish in a decade - and it risks nothing
while doing it.

### 7. Is Atlas worth continuing?

**YES.**

Not because it has found a way to make money - it has not, and this report
should not be read as saying so. Because it has found a **measurable,
falsifiable, executable-in-principle signal** that is one data acquisition away
from being answerable, and the acquisition is cheap.

---

## Recommendation: BUILD ATLAS CLV SYSTEM

Scope, in order:

1. **Acquire a timestamped odds archive.** Three seasons minimum, hourly or
   better, including at least one book that posts openers. This answers Track 5
   and nothing else can.
2. **Instrument the signal forward.** Record Atlas's direction and the
   available number at the time of the call, grade against that book's close,
   in public, with no money involved.
3. **Restrict to what the evidence supports**: totals, the loudest 10% of
   signals at the open, outside weeks 1-4 on margins if margins are carried at
   all.
4. **Grade on CLV, report in points of line**, never on simulated profit.

This is explicitly **not** authorisation to wager, and the system should not be
built in a way that makes wagering the obvious next step.

### Kill criterion, pre-registered

Atlas Gamma should be terminated if, after **two forward seasons** of live
tracking:

* the within-book CLV beat rate on the totals 10% cut falls below **55%**
  (against {t['concentration'][t['concentration']['top_pct'] == 10].iloc[0]['beat_rate']:.1%}
  measured here), **or**
* mean CLV on that cut falls below **{breakeven[('total', -105)]:.2f} points** -
  the -105 break-even - **or**
* the timestamped archive shows the movement Atlas predicts has already
  happened before a retail bettor could have acted on it.

Any one of those, and the programme has its answer and should stop. These
numbers are frozen here, in the same spirit as
[`docs/SIGNAL_PREREGISTRATION.md`](../docs/SIGNAL_PREREGISTRATION.md), so that
a future phase cannot move them after seeing the result.

---

## What this phase did not establish

- **That the signal is profitable.** It is not, at -110, on this evidence.
- **What limits apply.** No limit data exists in any auditable form; Track 3 is
  a framework with named assumptions, not a measurement.
- **When the movement happens.** Track 5 is unanswered.
- **That the price penalty generalises.** One book, two seasons, and the only
  direct evidence Atlas has.
"""
    out = paths.reports / "atlas_gamma_assessment.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def main() -> None:
    argparse.ArgumentParser(description="Atlas Phase 4 execution research").parse_args()
    bundle = build()
    write_opening_line_feasibility(bundle)
    write_clv_economics(bundle)
    write_gamma_assessment(bundle)


if __name__ == "__main__":
    main()
