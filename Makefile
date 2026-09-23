PYTHON ?= python3

.PHONY: help install ingest warehouse research all test lint clean-data \
	live-refresh live-run live-report live-check live-reproduce \
	site site-full site-serve site-audit site-shots launch-check

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
