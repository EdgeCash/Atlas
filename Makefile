PYTHON ?= python3

.PHONY: help install ingest warehouse research all test lint clean-data

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

all: ingest warehouse research phase1b phase1c validate

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check atlas tests

clean-data:
	rm -rf data/raw data/staging data/warehouse
	mkdir -p data/raw data/staging data/warehouse
	touch data/raw/.gitkeep data/staging/.gitkeep data/warehouse/.gitkeep
