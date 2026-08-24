# One entry point. CI runs exactly these targets — tests/test_ci_parity.py proves it.
PYTHON  ?= python3
RUFF_VERSION   := 0.16.3
PYTEST_VERSION := 8.3.4
XMLSCHEMA_VERSION := 4.2.0

.PHONY: check lint test fixtures corpus coverage-check sdist-runs-its-own-tests clean

check: lint fixtures test corpus coverage-check

lint:
	$(PYTHON) -m ruff check src tests tools packages

test:
	$(PYTHON) -m pytest

# Fixtures are generated, never committed: the generator is the source of truth.
fixtures:
	$(PYTHON) tools/make_fixtures.py

corpus:
	$(PYTHON) tools/vendor_corpus.py --check

coverage-check:
	$(PYTHON) tools/rule_coverage.py --check

# A downstream packager builds from the sdist. If the sdist cannot run the gate,
# they get a green build that checked nothing — the same shape as a gate that
# reads a path outside the repository.
sdist-runs-its-own-tests:
	$(PYTHON) tools/check_sdist.py

clean:
	rm -rf .pytest_cache .ruff_cache build dist tests/fixtures **/__pycache__
