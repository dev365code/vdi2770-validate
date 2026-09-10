# One entry point. CI runs the `check` targets and, on every push, `zipapp` —
# which is outside `check` because it needs the network. Both directions are
# proved in tests/test_ci_parity.py, where the exception carries its reason.
PYTHON  ?= python3
RUFF_VERSION   := 0.16.3
PYTEST_VERSION := 8.3.4
XMLSCHEMA_VERSION := 4.2.0

.PHONY: paths-disjoint upgrade-paths wheels installed-runs upgrade-paths-from-wheels zipapp check lint test fixtures corpus coverage-check rules-doc oracle-half sdist-runs-its-own-tests wheel-installs-and-runs reader-api-matches-its-version mutations standalone clean oracle-fully-swept

check: lint fixtures test corpus coverage-check rules-doc oracle-half reader-api-matches-its-version sdist-runs-its-own-tests wheel-installs-and-runs

# `--no-cache`: ruff keys its cache on file contents and settings, and a tree
# where files had moved kept answering from it -- 84 import-order errors were
# invisible here and immediate in CI, which has no cache. A gate that is green
# because it did not look is the thing this repository spends its time removing.
# The comment lives above the recipe: a `#` line inside one is a command as far
# as anything reading recipes is concerned, and the parity gate read it as one.
lint:
	$(PYTHON) -m ruff check --no-cache src tests tools packages

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

# Deliberately not in `check`: the other half of the comparison is the wheels
# already on the index, and `check` is offline. A gate that only ever reads this
# working tree compares two files nobody is installing -- the destruction
# happens between a release and whatever an installation already has.
paths-disjoint:
	$(PYTHON) tools/check_paths_are_disjoint.py

# Deliberately not in `check`: needs the network and a clean interpreter per
# case, and it answers a question `check` cannot ask -- what happens to an
# install somebody already has. The verdict is running the command, not
# `pip check`, which reports a destroyed install as fine.
upgrade-paths:
	$(PYTHON) tools/check_upgrade_paths.py

# Deliberately not in `check`: it builds both wheels, which needs the network
# for the build backend and is not what a contributor's edit-run loop should
# do. It is the question no reading of a tree can answer -- whether the file
# pip *wrote* starts on the machine it wrote it on. This release moves where
# the tool is installed from and which distribution owns the executable, and
# the suite had never run on Windows, where that file is spelled `.exe` and
# this harness used to call it absent.
#
# `dist` is cleared first: `--find-links` over a directory holding a previous
# build resolves to whichever version sorts highest, which is a check on an
# artifact nobody made in this run.
#
# The two commands are the release's two commands, character for character, and
# a test says so. They used to differ -- `--wheel` here, sdist and wheel there --
# so what a push built and what a tag built were not the same artifacts, and the
# rehearsal was of something else. Nothing bound them; the parity gate waves
# `python -m build` through as setup.
wheels:
	rm -rf dist
	$(PYTHON) -m build packages/vdi2770 --outdir dist/
	$(PYTHON) -m build --outdir dist/

installed-runs: wheels
	$(PYTHON) tools/check_upgrade_paths.py --case 11 --case 13 --from dist

# The whole matrix against the wheels this tree builds, which is what the
# release runs and what no push ran. The release's copy of this was red from the
# merge until it was found by reading: it downloaded one of the two wheels it
# needs, and a gate first exercised by the event it guards is not a gate.
upgrade-paths-from-wheels: wheels
	$(PYTHON) tools/check_upgrade_paths.py --from dist

# Deliberately not in `check`: it copies the tree, rebuilds the fixtures and runs
# pytest once per row, which is minutes rather than seconds. It answers the
# question `check` cannot ask of itself — whether the gates catch anything.
mutations:
	$(PYTHON) tools/mutation_table.py --run

# Outside `check` because it needs the network once, to fetch the dependency it
# bundles -- and `check` is offline, which is the property this tool sells. In
# CI on every push, though: a build nobody runs until tag day is a build that
# breaks on tag day.
zipapp:
	$(PYTHON) tools/build_zipapp.py --check

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
	       packages/vdi2770/.pytest_cache \
	       packages/vdi2770/build packages/vdi2770/dist
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.egg-info' -type d -prune -exec rm -rf {} +
