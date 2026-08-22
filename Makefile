# One entry point. CI runs exactly these targets — tests/test_ci_parity.py proves it.
PYTHON  ?= python3
RUFF_VERSION   := 0.16.3
PYTEST_VERSION := 8.3.4
XMLSCHEMA_VERSION := 4.3.2

.PHONY: check lint test fixtures corpus coverage-check clean

check: lint fixtures test corpus coverage-check

lint:
	$(PYTHON) -m ruff check src tests tools

test:
	$(PYTHON) -m pytest

# Fixtures are generated, never committed: the generator is the source of truth.
fixtures:
	$(PYTHON) tools/make_fixtures.py

corpus:
	$(PYTHON) tools/vendor_corpus.py --check

coverage-check:
	$(PYTHON) tools/rule_coverage.py --check

clean:
	rm -rf .pytest_cache .ruff_cache build dist tests/fixtures **/__pycache__
