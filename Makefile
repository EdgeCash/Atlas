PYTHON ?= python3

.PHONY: help install ingest warehouse research all test lint clean-data dfs-capture dfs-history dfs-staging dfs-scoring dfs-benchmarks dfs-model dfs-lineups dfs-slate dfs-kickers cfb-players cfb-scoring cfb-baseline cfb-model cfb-participation cfb-slate cfb-record owner-paper owner-plays ncaaf-qb availability \
	live-refresh live-run live-report live-check live-reproduce \
	site site-full site-serve site-audit site-shots launch-check \
	ops-heavy ops-poll ops-social ops-health ops-status ops-crontab \
	ops-backup ops-analytics perf seo ncaaf-benchmarks ncaaf-prior ncaaf-state ncaaf-total nfl-ingest nfl-warehouse nfl-benchmarks nfl-state nfl-total

help:
	@echo "Atlas Phase 1A - research warehouse"
	@echo ""
	@echo "  make install    install the package and dev dependencies"
	@echo "  make ingest     stage 1: pull every source into data/raw"
	@echo "  make warehouse  stage 2+3: staging tables and the DuckDB warehouse"
	@echo "  make research   stage 4: benchmarks, importance, research report"
	@echo "  make phase1b    opponent-adjustment, weather and QB reports"
	@echo "  make phase1c    information-edge tracks and synthesis"
	@echo "  make validate   signal validation: holdout, bootstrap, final verdict"
	@echo "  make velocity   Phase 2: decompose where Velocity's edge comes from"
	@echo "  make beta       Phase 3: market-aware framework and the beta report"
	@echo "  make gamma      Phase 4: can the line-movement signal be executed?"
	@echo ""
	@echo "  make live-refresh  Phase 5: rebuild with scheduled games, publish numbers"
	@echo "  make live-run      Phase 5: poll lines, form signals, grade, report"
	@echo "  make live-check    Ops: data quality, drift, anomalies, reproducibility"
	@echo "  make live-reproduce  Ops: replay random periods and verify they match"
	@echo ""
	@echo "  make site       build the Atlas Sports Intelligence site into site/"
	@echo "  make site-audit run the launch audit over every built page"
	@echo "  make launch-check  audit + tests + lint, the pre-publish gate"
	@echo "  make ops-heavy  daily 04:00 ET rebuild of everything"
	@echo "  make ops-poll   the light market poller (every 15 min)"
	@echo "  make ops-health check freshness; non-zero exit when stale"
	@echo "  make ops-status what the public status page says"
	@echo "  make ops-backup back up the live record and verify the copy"
	@echo "  make ncaaf-benchmarks  score the reference models the NCAAF model must beat"
	@echo "  make ncaaf-prior       fit and score the NCAAF preseason prior"
	@echo "  make ncaaf-state       run and score the NCAAF Kalman state model"
	@echo "  make ncaaf-total       calibrate the NCAAF total and score the joint score grid"
	@echo "  make nfl-ingest        fetch and cache nflverse play-by-play, schedules, injuries, depth charts, snaps"
	@echo "  make nfl-warehouse     stage the NFL team-game tables and build data/warehouse/nfl.duckdb"
	@echo "  make nfl-benchmarks    score the reference models the NFL model must beat"
	@echo "  make nfl-state         run and score the NFL Kalman state model"
	@echo "  make nfl-total         calibrate the NFL total and score the joint score grid"
	@echo "  make perf       measure load time and LCP at three viewports"
	@echo "  make seo        validate canonicals, meta, OpenGraph and sitemap"
	@echo "  make site-full  warehouse + numbers + market + site, from scratch"
	@echo "  make qb-data    extract the QB of record (research only, ~1 GB transient)"
	@echo "  make all        ingest -> warehouse -> research -> phase1b -> phase1c"
	@echo "  make test       run the offline test suite"
	@echo "  make lint       ruff check"
	@echo "  make clean-data remove generated data (sources are re-downloadable)"

install:
	$(PYTHON) -m pip install -e ".[dev]"

ingest:
	$(PYTHON) -m atlas.ingest

warehouse:
	$(PYTHON) -m atlas.warehouse.build

research:
	$(PYTHON) -m atlas.research.report

phase1b:
	$(PYTHON) -m atlas.research.phase1b_report

# Research only: the quarterback of record is post-kickoff data and is never
# read by the warehouse build. Cached after the first run.
qb-data:
	$(PYTHON) -m atlas.ingest --with-qb --no-pbp --no-predictors --no-cfbd

qb-research:
	$(PYTHON) scripts/research_qb_availability.py

phase1c: qb-data
	$(PYTHON) -m atlas.research.phase1c_report

# Each experiment is scored exactly once against criteria frozen in
# docs/SIGNAL_PREREGISTRATION.md. Re-running reproduces the same verdict; it
# does not constitute a second attempt.
validate:
	$(PYTHON) -m atlas.research.validation_report

velocity:
	$(PYTHON) -m atlas.research.velocity_report

# Phase 3 treats the market as the prior rather than the benchmark. The CLV
# measurements it produces are graded at the OPEN, so they depend on the
# opening lines staged by `make warehouse`, not just the closing ones.
beta:
	$(PYTHON) -m atlas.research.beta_report

# Phase 4 rebuilds the line table per sportsbook from data/raw rather than
# reading the staged consensus, so it needs the raw odds feed present - not
# just the warehouse.
gamma:
	$(PYTHON) -m atlas.research.gamma_report

# ---------------------------------------------------------------------------
# Phase 5: the live tracker. Atlas generates opinions, not bets.
# ---------------------------------------------------------------------------

# Expensive, weekly: needs the whole warehouse including scheduled games.
live-refresh:
	$(PYTHON) -m atlas.ingest
	$(PYTHON) -m atlas.live refresh

# Cheap, hourly: reads tracking/numbers.csv, never touches the warehouse.
live-run:
	$(PYTHON) -m atlas.live run

live-report:
	$(PYTHON) -m atlas.live report

# Operations checks: data quality, drift, anomalies, reproducibility. No network.
live-check:
	$(PYTHON) -m atlas.live check

live-reproduce:
	$(PYTHON) -m atlas.live reproduce --sample 5

# ---------------------------------------------------------------------------
# Atlas Sports Intelligence - the product
# ---------------------------------------------------------------------------

# Static HTML from the warehouse and the tracking store. No server.
site:
	$(PYTHON) -m atlas.site.build

# Everything the site needs, from a cold repository.
site-full:
	$(PYTHON) -m atlas.warehouse.build --include-scheduled
	$(PYTHON) -m atlas.live refresh --no-rebuild
	$(PYTHON) -m atlas.live run
	$(PYTHON) -m atlas.site.build

site-serve: site
	$(PYTHON) -m http.server 8000 --directory site

# ---------------------------------------------------------------------------
# Live operations - the three scheduled tasks. `make ops-crontab` prints the
# schedule these are wired to; see docs/OPERATIONS_SCHEDULE.md.
# ---------------------------------------------------------------------------

# 04:00 ET daily. Warehouse, model, market, every page.
ops-heavy:
	$(PYTHON) -m atlas.ops heavy

# Every 15 minutes. The task decides whether this minute is a poll minute,
# so one crontab line covers the hourly and the game-day cadences.
ops-poll:
	$(PYTHON) -m atlas.ops poll

# 05:00 ET daily. The featured card assets.
ops-social:
	$(PYTHON) -m atlas.ops social

# Non-zero exit when a blocking check fails, so it can drive an alert.
ops-health:
	$(PYTHON) -m atlas.ops health

# What the public status page says, in the terminal.
ops-status:
	$(PYTHON) -m atlas.ops status

# Copy the live record, read the copy back, prune old ones. Daily 03:00 ET.
ops-backup:
	$(PYTHON) -m atlas.ops backup

# Traffic from the web server's access log. No client-side anything.
# make ops-analytics LOGS="--access-log /var/log/atlas/access.log"
ops-analytics:
	$(PYTHON) -m atlas.ops analytics $(LOGS)

# Measure the built site in a real browser at three viewports.
# The numbers a candidate NCAAF model has to beat, walk-forward, out of sample.
ncaaf-benchmarks:
	$(PYTHON) -m atlas.models.ncaaf_benchmarks

# The preseason prior, walk-forward, scored where priors matter.
ncaaf-prior:
	$(PYTHON) -m atlas.models.ncaaf_prior

# The state model: the prior updated by every game, walk-forward.
ncaaf-state:
	$(PYTHON) -m atlas.models.ncaaf_state

# The total and the joint (home, away) grid on top of the state.
ncaaf-total:
	$(PYTHON) -m atlas.models.ncaaf_total

# NFL plan, step 0: the raw data, cached one season per file, no key.
nfl-ingest:
	$(PYTHON) -m atlas.sources.nflverse

# DFS plan, step 0: DraftKings' Classic slates and salaries into the record
# (daily in the heavy refresh), and RotoGuru's 2014-2021 DraftKings archive.
dfs-capture:
	$(PYTHON) -m atlas.sources.draftkings

dfs-history:
	$(PYTHON) -m atlas.sources.rotoguru

# DFS plan, step 1: the player-game and defense-game tables, and Atlas's
# DraftKings scoring reconciled against DraftKings' own record.
dfs-staging:
	$(PYTHON) -m atlas.dfs.players

dfs-scoring:
	$(PYTHON) -m atlas.dfs.reconcile

# DFS plan, step 2: the baseline and salary benchmarks, walk-forward.
dfs-benchmarks:
	$(PYTHON) -m atlas.dfs.benchmarks

# DFS plan, step 3: the game environment and the week's news per player,
# then the player model, walk-forward, beside its Atlas-only version.
dfs-model:
	$(PYTHON) -m atlas.dfs.environment
	$(PYTHON) -m atlas.dfs.context
	$(PYTHON) -m atlas.dfs.model --atlas-only

# DFS plan, step 5: the optimizer's lineups backtested on 2015-2021, and this
# week's slate projected with lineups under data/dfs/ (never committed).
dfs-lineups:
	$(PYTHON) -m atlas.dfs.backtest

dfs-slate:
	$(PYTHON) -m atlas.dfs.slate --capture

# DFS, the NFL formats: the kicker model Showdown needs, walk-forward, with
# its scoring checked against DraftKings' live points-per-game.
dfs-kickers:
	$(PYTHON) -m atlas.dfs.kicker --reconcile

# College DFS, step 1: ESPN's college box scores (budgeted; newest first) and
# DraftKings' college scoring checked against its live points per game.
cfb-players:
	$(PYTHON) -m atlas.sources.espn_cfb

cfb-scoring:
	$(PYTHON) -m atlas.dfs.cfb --reconcile

# College DFS, step 2: the player-game table and the baseline, walk-forward.
cfb-baseline:
	$(PYTHON) -m atlas.dfs.cfb_players

# College DFS, step 3: the model and its ranges, walk-forward.
cfb-model:
	$(PYTHON) -m atlas.dfs.cfb_model

# College DFS, step 5: who records a stat, walk-forward; then this week's
# college slates projected and their lineups written under data/dfs/.
cfb-participation:
	$(PYTHON) -m atlas.dfs.cfb_participation

cfb-slate:
	$(PYTHON) -m atlas.dfs.cfb_slate

# The private college record's summary (needs ATLAS_OWNER_KEY to open it).
cfb-record:
	$(PYTHON) -m atlas.dfs.cfb_record

# The owner's paper tracker: the live signals graded as flat paper wagers.
# Shown only inside the owner page's ciphertext.
owner-paper:
	$(PYTHON) -m atlas.owner.paper

# The SEC's and the ACC's availability reports: their quarterbacks into tracking/availability.csv.
availability:
	$(PYTHON) -m atlas.sources.availability

# The owner's curated plays under the frozen rules, and their record (needs ATLAS_OWNER_KEY).
owner-plays:
	$(PYTHON) -m atlas.owner.plays

# College plan, row 9: the quarterback state from ESPN box scores, measured (it fails; see the report).
ncaaf-qb:
	$(PYTHON) -m atlas.models.ncaaf_qb

# NFL plan, step 1: point-in-time team-game tables in their own warehouse.
nfl-warehouse:
	$(PYTHON) -m atlas.staging.nfl.build

# NFL plan, step 2: the numbers the model has to beat, walk-forward.
nfl-benchmarks:
	$(PYTHON) -m atlas.models.nfl_benchmarks

# NFL plan, step 3: the state, carried across seasons, walk-forward.
nfl-state:
	$(PYTHON) -m atlas.models.nfl_state

# NFL plan, step 5: the total and the 60x60 grid on top of the state.
nfl-total:
	$(PYTHON) -m atlas.models.nfl_total

perf: site
	$(PYTHON) scripts/measure_performance.py

# Canonical tags, meta, OpenGraph, Twitter cards, sitemap and robots.
seo: site
	$(PYTHON) scripts/validate_seo.py

# The schedule, ready to install.
ops-crontab:
	$(PYTHON) -m atlas.ops crontab --root $(CURDIR)

# The launch gate. Scans every built page for a named side, the forbidden
# vocabulary, a card missing its disclaimer, and anything that moves. Exits
# non-zero on a blocking finding, so it can gate a deploy.
site-audit: site
	$(PYTHON) scripts/audit_site.py

# Screenshots of the built site at real viewports, into design/screens/site/.
site-shots: site
	$(PYTHON) scripts/shoot_site.py

# Everything that has to pass before Atlas is published.
launch-check: site-audit
	$(PYTHON) scripts/validate_seo.py
	$(PYTHON) -m pytest -q
	$(PYTHON) -m ruff check atlas/ scripts/ tests/

all: ingest warehouse research phase1b phase1c validate velocity beta gamma

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check atlas tests

clean-data:
	rm -rf data/raw data/staging data/warehouse
	mkdir -p data/raw data/staging data/warehouse
	touch data/raw/.gitkeep data/staging/.gitkeep data/warehouse/.gitkeep
