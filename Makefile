# One entry point. CI runs exactly these targets — tests/test_ci_parity.py proves it.
PYTHON  ?= python3
RUFF_VERSION   := 0.16.3
PYTEST_VERSION := 8.3.4
XMLSCHEMA_VERSION := 4.2.0

.PHONY: check lint test fixtures corpus coverage-check rules-doc oracle-half sdist-runs-its-own-tests wheel-installs-and-runs reader-api-matches-its-version mutations standalone clean oracle-fully-swept

check: lint fixtures test corpus coverage-check rules-doc oracle-half reader-api-matches-its-version sdist-runs-its-own-tests wheel-installs-and-runs

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

# The rule reference is generated. Editing the page instead of the data is the
# double-maintenance this project keeps a --check for.
rules-doc:
	$(PYTHON) tools/rules_doc.py --check

# The reference half of the sweep needs a JDK and somebody else's checkout. Our
# half needs neither, and it is the half that goes stale: a rule's severity can
# move and leave a recorded verdict describing a tool that no longer exists,
# while docs/divergences.md goes on counting from it.
oracle-half:
	$(PYTHON) tools/capture_oracle.py --check-ours

# Deliberately not in `check`: it copies the tree, rebuilds the fixtures and runs
# pytest once per row, which is minutes rather than seconds. It answers the
# question `check` cannot ask of itself — whether the gates catch anything.
mutations:
	$(PYTHON) tools/mutation_table.py --run

# Outside `check` because it is a release question, not a change question: a
# container may sit unswept for as long as it takes to run the `oracle` workflow,
# and that is fine while the divergence counts exclude it. It stops being fine
# the moment those counts are published. Reads the recorded file and the
# containers on disk — a release must not depend on Maven Central being
# reachable, but it does have to know which containers exist, and the fixtures
# are generated rather than committed. Without `fixtures` first this target
# fails on a fresh clone and blames the sweep for the twenty-seven containers
# nobody had built yet; it passed in the release workflow only because
# `make check` happens to run `fixtures` before it.
oracle-fully-swept: fixtures
	$(PYTHON) tools/capture_oracle.py --check-swept

# Also outside `check`: one interpreter start per test file. It answers a
# question a shared process cannot — whether any file passes only because of
# what ran before it.
standalone:
	$(PYTHON) tools/standalone_tests.py

# A downstream packager builds from the sdist. If the sdist cannot run the gate,
# they get a green build that checked nothing — the same shape as a gate that
# reads a path outside the repository.
sdist-runs-its-own-tests:
	$(PYTHON) tools/check_sdist.py

# Nobody installs a source distribution. Until this existed, "the licences travel
# with the package" was a claim about a string in a pyproject.toml.
wheel-installs-and-runs:
	$(PYTHON) tools/check_wheel.py

# The pin gate catches "the pin is too loose". This catches the other half: the
# reader's public surface moved and its version did not, so whoever installs
# that version from PyPI does not get what these tests ran against.
reader-api-matches-its-version:
	$(PYTHON) tools/api_fingerprint.py --check

clean:
	# `**` is not recursive under /bin/sh, and *.egg-info is what makes the
	# packaging gates read the last build instead of this commit.
	rm -rf .pytest_cache .ruff_cache build dist tests/fixtures \
	       packages/vdi2770/build packages/vdi2770/dist
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.egg-info' -type d -prune -exec rm -rf {} +
