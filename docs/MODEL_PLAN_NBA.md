# NBA plan: the fourth sport, priced on Polymarket

From 23 October 2026. The NBA joins college football, the NFL and the NHL
as a sport Atlas projects and prices on Polymarket (`docs/POLYMARKET.md`).
What was built, and what each piece is measured by.

## What the NBA needed

The three sports before it each came with a warehouse, a model fitted and
scored walk-forward, a record of the model against the closing line, and a
place in the live tracker. The NBA needed all four and got them in one pass,
because every piece but the data is the NFL's, reused:

| Step | What | Where | Measured by |
|---|---|---|---|
| 0 | **Data.** ESPN's schedule and team box scores as hoopR mirrors them (sportsdataverse), 2002 on, keyed by ESPN's event id - the id the live tracker already uses; SportsBookReviewsOnline's odds archive, 2007-08 to 2022-23, for the closing spread, total and moneyline | `atlas/sources/nba.py` | 25,707 games cached, 19,623 with a close |
| 1 | **Warehouse.** One row per game in Atlas's conventions: the season by its start year, the week from the first regular-season tip, the home handicap as the closing spread, rest and back-to-backs; the All-Star weekend dropped; a team-game table with a possessions estimate | `atlas/staging/nba/` | `data/warehouse/nba.duckdb` |
| 2 | **Model.** The NFL's joint Kalman state (`atlas/models/kalman.py`) on points: every team's offence and defence with a full covariance, process noise by the week, a between-season regression, the two sides' noise correlation measured; the total calibrated on the state's own total with the line-given reading of P(over) fitted on the archive's closing totals | `atlas/models/nba_state.py` | `reports/nba_state.md`: CRPS, MAE and Brier against naive, Elo and the closing line, 2012-13 to 2022-23, each season tuned only on the seasons before it |
| 3 | **Record.** Each game's claimed probability at the close and what happened, spread and total, in `tracking/calibration.csv` | `nba_state.calibration` | the share of Atlas's disagreement the Polymarket pricing takes (`atlas/polymarket/pricing.py`) |
| 4 | **Projector.** The state carried through the season in progress with the saved hyperparameters, the games inside eight days projected into `tracking/projections.csv`, `sport = "nba"` | `atlas/models/nba_projection.py` | the live refresh |
| 5 | **Live.** ESPN's NBA scoreboard polled with the others (games, finals; ESPN quotes no NBA odds); a Sunday-night game-day window, the one evening football and hockey leave uncovered | `atlas/live/provider.py`, `atlas/ops/schedule.py` | `tracking/games.csv` |
| 6 | **Polymarket.** The NBA series read with the others; NBA contracts priced the football way, in centre space off the ladder, anchored by the record's share | `atlas/polymarket/` | `reports/polymarket_model.md` |
| 7 | **Player props.** Points, rebounds, assists and threes for every rostered player: minutes times a per-minute rate times the game (home, the opponent's allowance, the pace), negative binomial around the expectation; the hoopR player box from 2015-16, half-lives tuned walk-forward; the snapshot the Polymarket run prices the props off, written by the heavy refresh; ESPN's injury report read every run and applied to it (`atlas/sources/nba_availability.py`), with the venue's rule that a player who does not take the court resolves No | `atlas/models/nba_props.py`, `atlas/polymarket/props.py` | `reports/nba_props.md` |

Not built: an NBA page on the public site. The site publishes cards only
for sports whose grade has a calibration study behind it; the NBA's record
exists for the pricing, and the card can follow when there is a reason to
show one.

## The market the record is measured against

The odds archive stops after the first half of 2022-23. The seasons since
have no sportsbook close in the warehouse, so the state learns from their
results but they are not scored, and the record the pricing reads ends
there. From opening night 2026 the live run keeps Polymarket's own close
for every NBA game (`tracking/polymarket_quotes.csv`); a retune that scores
the model against those closes is the next step once a season of them
exists.

## Retuning

`make nba-state` walks the model forward and saves the hyperparameters the
live projector reads (`reports/nba_state_choices.json`); the retune workflow
runs it with the others (Actions → retune → `nba`). A retune moves live
numbers, so a person asks for it and a person reviews what it proposes.
