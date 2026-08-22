# One entry point. CI runs exactly these targets — tests/test_ci_parity.py proves it.
PYTHON  ?= python3
RUFF_VERSION   := 0.16.3
PYTEST_VERSION := 8.3.4
XMLSCHEMA_VERSION := 4.3.2

.PHONY: check lint test corpus clean

check: lint test corpus

lint:
	$(PYTHON) -m ruff check src tests tools

test:
	$(PYTHON) -m pytest

corpus:
	$(PYTHON) tools/vendor_corpus.py --check

clean:
	rm -rf .pytest_cache .ruff_cache build dist **/__pycache__
