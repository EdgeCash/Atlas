# Warehouse data dictionary

Seven tables, one row per game in each, keyed on `game_id` (the ESPN/CFBD
event id). Written as parquet to `data/warehouse/` and loaded into
`data/warehouse/atlas.duckdb`, which also exposes a joined `research_games`
view.

The columns required by the Phase 1A brief come first in every table; Atlas
additions follow. `atlas/warehouse/schema.py` is the machine-readable version
and the test suite asserts against it.

---

## `games`

| Column | Type | Meaning |
|---|---|---|
| `game_id` | int64 | Event id, primary key |
| `season` | int64 | Season year |
| `week` | int64 | Week number within the season |
| `date` | string | Kickoff date, UTC |
| `away_team`, `home_team` | string | School names |
| `away_score`, `home_score` | int64 | Final scores |
| `margin` | int64 | `home_score - away_score` |
| `total_points` | int64 | `home_score + away_score` |
| `home_win` | int8 | 1 if `margin > 0` |
| `home_cover` | float | 1 cover, 0 no cover, null on push or no line |
| `over_result` | float | 1 over, 0 under, null on push or no line |
| *additions* | | `season_type`, `kickoff` (UTC timestamp), team ids, divisions, conferences, `neutral_site`, `conference_game`, `venue_id`, `venue`, `home_pregame_elo`, `away_pregame_elo` |

Only completed regular-season and postseason games are included.

## `market_lines`

| Column | Type | Meaning |
|---|---|---|
| `game_id` | int64 | |
| `closing_spread` | float | Consensus closing spread, **home-oriented**: negative means the home side is favoured |
| `closing_total` | float | Consensus closing total |
| `opening_spread`, `opening_total` | float | Same, at open |
| `moneyline_home`, `moneyline_away` | float | Consensus American odds |
| `spread_movement` | float | `closing_spread - opening_spread` |
| `total_movement` | float | `closing_total - opening_total` |
| *additions* | | `spread_books`, `total_books` - how many sportsbooks contributed |

Consensus is the **median across sportsbooks**, not a single book. Sportsbook
abbreviations in the source feed match no team-id table, so they are resolved
by constraint: the team id present in ~100% of the games carrying an
abbreviation is that abbreviation's team. Resolution covered 97% of team-side
rows and the resulting orientation agrees with the independent spread carried
in the play-by-play feed on 98-99% of games to within 3 points.

## `ratings`

| Column | Type | Meaning |
|---|---|---|
| `game_id` | int64 | |
| `home_sp_plus`, `away_sp_plus`, `sp_plus_diff` | float | SP+ overall, **previous season's** rating. Null unless `CFBD_API_KEY` is set |
| `home_fpi`, `away_fpi`, `fpi_diff` | float | ESPN FPI, **previous season's** rating, net-points scale |
| *additions* | | `home_sp_plus_off` / `away_sp_plus_off` / `sp_plus_off_diff`, `home_sp_plus_def` / `away_sp_plus_def` / `sp_plus_def_diff`, `fpi_home_win_prob` (ESPN pre-game matchup projection), `home_pregame_elo`, `away_pregame_elo`, `elo_diff` |

The SP+ offence/defence split matters: a sum of two *overall* ratings says
nothing about a scoring environment, and carrying the components separately
is what turns SP+ from the weakest margin rating in the study into the best
non-market totals rating.

`*_diff` is always home minus away.

## `efficiency_metrics`

One `home_*` / `away_*` / `*_diff` triple per metric. **Every value is
point-in-time**: it averages that team's strictly earlier games, shrunk toward
its previous-season mean. See [POINT_IN_TIME.md](POINT_IN_TIME.md).

| Metric | Meaning |
|---|---|
| `off_epa` | Mean expected points added per scrimmage play on offense |
| `def_epa` | Mean EPA allowed per scrimmage play. Lower is better |
| `success_rate` | Share of plays gaining 50% of needed yards on 1st down, 70% on 2nd, 100% on 3rd/4th |
| `explosiveness` | Mean EPA on *successful* plays only (IsoPPP) |
| `havoc` | Share of defensive plays with a run stuff, sack, interception, pass breakup or forced fumble |
| `finishing_drives` | Points per scoring opportunity, where an opportunity is a drive reaching the opponent's 40 |
| `pace` | Seconds of game clock per offensive scrimmage play |
| *additions* | `def_success_rate`, `def_explosiveness`, `plays_per_game` (clock-free pace proxy), `home_prior_games`, `away_prior_games`, `min_prior_games` |

A scrimmage play is a rush or pass not wiped out by penalty. Garbage-time
plays are excluded (per-quarter margin thresholds 38/28/22/16; overtime is
never garbage time).

## `adjusted_efficiency_metrics`

Added in Phase 1B. Same `home_*` / `away_*` / `*_diff` shape as
`efficiency_metrics`, but every value is **opponent-adjusted**: the rating a
team held before that week kicked off, solved from the schedule graph rather
than averaged blind. See
[`reports/opponent_adjustment_report.md`](../reports/opponent_adjustment_report.md).

| Metric | Meaning |
|---|---|
| `adj_off_epa` | EPA per play this team produces **against an average defence** |
| `adj_def_epa` | EPA per play it allows **to an average offence**. Lower is better |
| `adj_success_rate` / `adj_def_success_rate` | Same, for success rate |
| `adj_explosiveness` / `adj_def_explosiveness` | Same, for EPA on successful plays |
| `adj_havoc` / `adj_havoc_allowed` | Havoc a defence generates / an offence concedes. Here the **defence is the actor** |
| `adj_finishing_drives` / `adj_def_finishing_drives` | Points per scoring opportunity, produced and allowed |
| `adj_pace` / `adj_def_pace` | Seconds per play, own and forced |

Each name above appears three times, once per adjustment method: unsuffixed is
the primary **network** solve (Method C, Massey/SRS ridge least squares),
`_iterative` is Method B (Gauss-Seidel), `_simple` is Method A (one-pass
schedule-strength subtraction). Methods B and C agree to four decimals;
Method A under-corrects and is kept only so the report can show the cost of
choosing it.

Extras: `home_prior_games`, `away_prior_games` are carried on
`efficiency_metrics`; the adjusted table's own history indicator is
`n_prior_observations` in `staging/adjusted_efficiency.parquet`.

## `talent`

| Column | Type | Meaning |
|---|---|---|
| `game_id` | int64 | |
| `home_returning_production`, `away_returning_production` | float | Share of production returning (CFBD `percentPPA`) |
| `home_recruiting_rank`, `away_recruiting_rank` | float | National recruiting class rank |
| `talent_diff` | float | Roster talent composite, home minus away |
| *additions* | | `recruiting_rank_diff` (away minus home, so positive always favours the home side), `returning_production_diff`, `home_talent`, `away_talent` |

All CFBD-only. Null without `CFBD_API_KEY`. Same-season values are used: both
are fixed before the season starts.

## `context`

| Column | Type | Meaning |
|---|---|---|
| `game_id` | int64 | |
| `rest_diff` | float | Home days rest minus away days rest |
| `travel_distance` | float | Great-circle miles travelled by the **visiting** side |
| `weather_temp`, `weather_wind`, `weather_precip` | float | Kickoff conditions in °F, mph and inches, from the nearest Meteostat station (free, no key). CFBD `/games/weather` remains a fallback but needs a paid tier |
| `neutral_site` | bool | |
| *additions* | | `home_days_rest`, `away_days_rest`, `home_travel_distance`, `away_travel_distance`, `travel_distance_diff`, `weather_humidity`, `weather_temp_effective`, `weather_wind_effective`, `weather_precip_effective`, `venue_dome`, `weather_station_id`, `weather_station_miles` |

The `_effective` weather columns model what players experience rather than
what the sky is doing: indoors they are room temperature, no wind and no rain.
`weather_station_miles` is how far the observing station sits from the
stadium - the median is about five miles.

`home_travel_distance` is zero at a true home game and non-zero at a neutral
site, which is the point of carrying both.

## `outcomes`

| Column | Type | Meaning |
|---|---|---|
| `game_id` | int64 | |
| `actual_margin` | float | `home_score - away_score` |
| `actual_total` | float | `home_score + away_score` |
| `home_cover` | float | 1 / 0 / null on push |
| `over_hit` | float | 1 / 0 / null on push |
| *additions* | | `ats_margin` (`margin + closing_spread`), `total_error` (`total_points - closing_total`) |

A push is recorded as **null**, never as a loss.

---

## `research_games` (DuckDB view)

Every table joined on `game_id`, plus the derived columns the research layer
uses (`market_margin = -closing_spread`, `*_sum` features for totals,
`neutral_site_flag`, `closing_spread_abs`, `rest_abs`). This is the table to
query for analysis.

```sql
SELECT season, count(*) AS games, avg(abs(actual_margin + closing_spread)) AS ats_mae
FROM research_games
WHERE home_division = 'fbs' AND away_division = 'fbs'
GROUP BY 1 ORDER BY 1;
```

---

## Source provenance

| Source | Needs a key | Provides |
|---|---|---|
| sportsdataverse `cfbfastR-data` (CFBD mirror) | no | schedules, results, team info and venue geography, historical sportsbook lines |
| sportsdataverse `cfbfastR_cfb_pbp` release | no | play-by-play with EPA and success |
| ESPN public endpoints | no | FPI season ratings, pre-game matchup projections |
| CollegeFootballData API | **yes**, free key | SP+ (overall, offence, defence), recruiting rankings, roster talent, returning production |
| Meteostat bulk files | no | hourly station weather - free, unmetered, used for all kickoff conditions |
| CollegeFootballData API | **yes**, paid tier | kickoff weather (`/games/weather`) - superseded by Meteostat |

Without a CFBD key the warehouse still builds completely; the CFBD-only
columns are present and null, and the research report reports them as
unavailable rather than dropping them.
