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
	@echo "  make all        ingest -> warehouse -> research -> phase1b"
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

# The quarterback probe re-downloads full play-by-play, so it is deliberately
# not part of `make all`. Research only - it writes nothing to the warehouse.
qb-research:
	$(PYTHON) scripts/research_qb_availability.py

all: ingest warehouse research phase1b

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check atlas tests

clean-data:
	rm -rf data/raw data/staging data/warehouse
	mkdir -p data/raw data/staging data/warehouse
	touch data/raw/.gitkeep data/staging/.gitkeep data/warehouse/.gitkeep
