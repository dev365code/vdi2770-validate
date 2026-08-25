#!/usr/bin/env python3
"""Every claim this project makes about a gate, as a mutation somebody can run.

    python tools/mutation_table.py            # list the table
    python tools/mutation_table.py --run      # apply each one and check it dies

A gate is only worth what it catches. This repository's history is a list of
gates that turned out to catch nothing — a ceiling with no floor, a glob over a
directory that had been renamed, a check derived from the same declaration it was
checking. Each was found by hand, once, and the evidence lived in a commit
message.

Here it is a table, and the harness checks itself as hard as it checks the code:

  * **the mutation has to take effect.** Every row asserts its original text
    appears exactly once. A row whose anchor has drifted is an error, not a pass.
  * **the bytecode has to be the new bytecode.** Restoring a file to its previous
    *size* leaves a `.pyc` that CPython still considers valid — source mtime is
    stored at one-second resolution — so a mutation can look like it survived
    when it never loaded. Twice in one day. Every apply and every restore clears
    `__pycache__` and touches the file.
  * **the tests have to exist.** A selection that collects nothing exits 5, not
    1, and that is a broken row rather than a killed mutant.
  * **one row must survive.** If every row dies, the likeliest explanation is a
    harness that reports red for everything. The canary is a change that really
    does not matter, and it failing means the results above it mean nothing.

It runs on a copy of the tree, so an interrupted run cannot leave a mutation in
your working directory.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (id, file, original, mutated, checks that must go red, why it matters)
# A check is a pytest path, or `tools/<script> <args>` for a gate that is a tool.
TABLE = [
    ("reader/decompression-budget",
     "packages/vdi2770/src/vdi2770/zipread.py",
     "        if not exhausted and not budget.take_bytes(m.size):",
     "        if False:",
     ["packages/vdi2770/tests/test_the_budget_covers_every_read.py"],
     "one read could inflate two terabytes"),

    ("reader/refused-member-is-still-present",
     "packages/vdi2770/src/vdi2770/zipread.py",
     "    c.kind, c.near_misses = _classify(c.present)",
     "    c.kind, c.near_misses = _classify(c.file_names)",
     ["tests/test_a_refused_member_is_still_in_the_archive.py"],
     "one bad CRC made a container 'not a VDI 2770 container at all'"),

    ("reader/never-read-what-we-refused",
     "packages/vdi2770/src/vdi2770/zipread.py",
     "    if wanted and wanted in c.rejected:\n        wanted = None",
     "    if False:\n        wanted = None",
     ["packages/vdi2770/tests/test_a_refused_member_is_never_read.py"],
     "a refused zip bomb was inflated anyway"),

    ("reader/duplicates-over-the-whole-directory",
     "packages/vdi2770/src/vdi2770/zipread.py",
     "    for m in [i for i in infos if not i.is_dir()]:",
     "    for m in [i for i in infos if not i.is_dir()][:1]:",
     ["packages/vdi2770/tests/test_every_name_is_accounted_for.py"],
     "a duplicate name could be hidden by making one copy oversized"),

    ("report/listing-cap-does-not-soften-the-count",
     "src/vdi2770_validate/model.py",
     "        return (sum(1 for f in self.findings if f.severity is sev)\n"
     "                + self._suppressed_severity.get(sev, 0))",
     "        return sum(1 for f in self.findings if f.severity is sev)",
     ["tests/test_one_rule_cannot_flood_the_report.py", "tests/test_cli.py"],
     "a bounded listing would have become a quieter verdict"),

    ("runner/a-crashing-rule-is-a-finding",
     "src/vdi2770_validate/runner.py",
     "        for f in findings:\n            report.add(f)",
     "        for f in list(findings)[:0]:\n            report.add(f)",
     ["tests/test_a_rule_that_crashes_does_not_kill_the_run.py"],
     "one rule's exception killed a whole sweep"),

    ("cli/one-bad-path-does-not-stop-the-rest",
     "src/vdi2770_validate/cli.py",
     "getattr(e, 'strerror', None) or e",
     "e.strerror or e",
     ["tests/test_cli.py"],
     "the handler that existed to keep going was itself stopping"),

    ("rules/z8-counts-document-containers",
     "src/vdi2770_validate/rules/container.py",
     "        if not delivered and not stopped and not as_folders:",
     "        if not container.children and not stopped and not as_folders:",
     ["tests/test_z8_counts_document_containers.py"],
     "a documentation container delivering nothing came back clean"),

    ("rules/f2-emits-in-a-fixed-order",
     "src/vdi2770_validate/rules/files.py",
     "    for name in sorted(set(members.present) - accounted_for - structural):",
     "    for name in set(members.present) - accounted_for - structural:",
     ["tests/test_determinism.py"],
     "the report depended on the interpreter's hash seed"),

    ("gates/a-dead-rule-fails-the-build",
     "tools/rule_coverage.py",
     "    unexercised = sorted(all_ids - fired - set(cannot_fire))\n    if unexercised:",
     "    unexercised = sorted(all_ids - fired - set(cannot_fire))\n    if False:",
     ["tests/test_the_coverage_gate_judges_dead_rules.py"],
     "README says a rule that fires nowhere fails the build"),

    ("gates/the-excuse-is-the-reason",
     "tools/rule_coverage.py",
     "    if dict(baseline.get(\"cannotFire\", {})) != dict(cannot_fire):",
     "    if set(baseline.get(\"cannotFire\", {})) != set(cannot_fire):",
     ["tests/test_the_coverage_gate_judges_dead_rules.py"],
     "an excuse could be rewritten from impossible to unwritten"),

    ("layering/a-rule-cannot-reach-a-parser",
     "src/vdi2770_validate/rules/files.py",
     "from typing import Iterator",
     "import zipfile\nfrom typing import Iterator",
     ["tests/test_layering.py"],
     "a rule could check the spelling instead of the model"),

    ("gates/our-half-of-the-sweep-is-current",
     "src/vdi2770_validate/data/rules.json",
     '"id": "F3",\n      "layer": "files",\n      "severity": "warning"',
     '"id": "F3",\n      "layer": "files",\n      "severity": "error"',
     ["tools/capture_oracle.py --check-ours"],
     "a rule's severity could move and leave the recorded sweep describing a "
     "tool that no longer exists"),

    ("gates/the-vendored-messages-have-not-moved",
     "tests/data/oracle-messages.json",
     '"count": 233',
     '"count": 232',
     ["tests/test_licensing.py"],
     "weakening the message set weakens the proof that no remedy was copied"),

    ("gates/a-publishing-workflow-runs-the-whole-gate",
     ".github/workflows/release-sdk.yml",
     "        working-directory: .\n        run: |\n          python -m pip install -e packages/vdi2770",
     "        run: |\n          python -m pip install -e packages/vdi2770",
     ["tests/test_ci_parity.py"],
     "the SDK release ran make check from a directory with no Makefile"),

    ("gates/the-coverage-gate-uses-its-own-judgement",
     "tools/rule_coverage.py",
     "        if problems:\n            for p in problems:",
     "        problems = []\n        if problems:\n            for p in problems:",
     ["tools/rule_coverage.py --check", "tests/test_the_coverage_gate_judges_dead_rules.py"],
     "`judge()` was tested by calling it; nothing ran the gate as a command, so "
     "main() could throw the judgement away and every check stayed green"),

    ("gates/a-rule-that-lost-its-fixture-is-noticed",
     "tools/make_fixtures.py",
     '    add("m9-repeated-document-id.zip"',
     '    _dropped = lambda *a, **k: None; _dropped("m9-repeated-document-id.zip"',
     ["tools/make_fixtures.py", "tools/rule_coverage.py --check"],
     "a fixture removed from the generator used to stay on disk and go on "
     "satisfying firing coverage — the generator now owns the directory, so the "
     "rule genuinely stops firing and the gate says so"),

    ("gates/an-excuse-is-not-available-to-every-rule",
     "tools/rule_coverage.py",
     "    if about_a_container:",
     "    if False:",
     ["tests/test_the_coverage_gate_judges_dead_rules.py"],
     "one long sentence in the gate's own file removed a rule from the gate"),

    ("gates/the-api-record-cannot-be-quieted-by-editing-it",
     "tools/api_fingerprint.py",
     "        if recorded and recorded.get(\"version\") not in (None, now[\"version\"]):",
     "        if False:",
     ["tests/test_the_api_record_holds.py"],
     "editing one field in the JSON steered the refusal past the row it should "
     "have compared"),

    ("gates/the-wheel-carries-only-the-package",
     "pyproject.toml",
     'vdi2770_validate = ["data/*.json", "data/*.xsd"]',
     'vdi2770_validate = ["data/*.json", "data/*.xsd"]\n\n'
     '[tool.setuptools.data-files]\n"share/vdi2770" = ["docs/oracle-sweep.json"]',
     ["tools/check_wheel.py"],
     "NOTICE tells readers the MIT-derived oracle evidence is in the sdist and in "
     "neither wheel; nothing checked the wheel from that direction"),

    ("gates/a-breaking-change-cannot-ship-as-a-patch",
     "tools/api_fingerprint.py",
     "    if not lost and not moved:",
     "    if True:",
     ["tests/test_the_api_record_holds.py"],
     "the validator pins the reader with `~=`, so a removal published as 0.6.1 "
     "installs itself on machines that asked for 0.6.0 -- which this project "
     "shipped once already"),

    ("gates/a-cited-file-has-to-exist-in-every-document",
     "CONTRIBUTING.md",
     "## Three rules of the road",
     "The gate lives in `tools/it_was_renamed.py::check`.\n\n## Three rules of the road",
     ["tests/test_the_docs_count_what_they_claim.py"],
     "the citation check read SECURITY.md and nothing else, so CONTRIBUTING and "
     "docs/licensing.md could point at files that are not here"),

    ("reader/the-xml-tree-has-a-ceiling",
     "packages/vdi2770/src/vdi2770/xmlread.py",
     "        if built > MAX_ELEMENTS:",
     "        if False:",
     ["packages/vdi2770/tests/test_the_tree_bounds_what_it_builds.py"],
     "the bytes were bounded and the tree built out of them was not: a 115 KB "
     "archive cost 952 MB"),

    ("reader/a-repeated-name-identifies-nothing",
     "packages/vdi2770/src/vdi2770/zipread.py",
     "    repeated = {n for n, k in counted.items() if k > 1}",
     "    repeated = set()",
     ["packages/vdi2770/tests/test_a_refused_member_is_never_read.py"],
     "zipfile resolves a duplicated name to the last entry while the budget "
     "charged the first, so a 505 KiB archive cost 1.25 GiB with the report "
     "saying the member had been refused"),

    ("rules/a-refusal-to-model-is-not-a-malformed-file",
     "src/vdi2770_validate/rules/schema.py",
     '               else "X6" if isinstance(parse_error, XmlTooLarge) else "X1")',
     '               else "X1")',
     ["tests/test_a_document_we_would_not_build_is_not_malformed.py"],
     "bounding the tree handed well-formed metadata the verdict `not well-formed "
     "XML`, which blames the sender for our limit"),

    ("gates/the-version-is-not-part-of-the-surface-it-names",
     "tools/api_fingerprint.py",
     '    a = {k: v for k, v in recorded["surface"].items() if k != "__version__"}',
     '    a = dict(recorded["surface"])',
     ["tests/test_the_api_record_holds.py"],
     "`__version__` is in `__all__`, so it moved in every comparison and the "
     "compatible branch was unreachable: every patch release of the reader was "
     "refused, including one that changed nothing else"),

    ("reader/the-tree-of-documents-has-a-ceiling-too",
     "src/vdi2770_validate/runner.py",
     "        if c.metadata_bytes is not None and elements >= MAX_TOTAL_ELEMENTS:",
     "        if False:",
     ["tests/test_a_document_we_would_not_build_is_not_malformed.py"],
     "bounding one document did not bound the sum: 12 KiB of archive cost 74 "
     "seconds of CPU with every reader budget green"),

    ("reader/a-bad-encoding-declaration-is-the-documents-problem",
     "packages/vdi2770/src/vdi2770/xmlread.py",
     "    except (LookupError, ValueError) as e:",
     "    except (LookupError,) as e:  # noqa: B014",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "expat raises outside ExpatError for an encoding it will not decode, so a "
     "malformed document was reported as this tool crashing"),

    ("rules/a-dot-slash-prefix-is-not-a-folder",
     "src/vdi2770_validate/rules/container.py",
     '        if not folder_path(prefix + "/"):',
     "        if False:",
     ["tests/test_documents_delivered_as_folders.py"],
     "`./VDI2770_Metadata.xml` is at the root, and Z13 said this tool had not "
     "looked inside something it had read"),

    ("reader/each-trailer-gets-its-own-budget",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "        found, _ = _scan_dictionary(data, start, MAX_TRAILER_SCAN)",
     "        found, _ = _scan_dictionary(data, start, max(0, MAX_TRAILER_SCAN - start))",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "one trailer with a long /ID spent the budget and the encrypted trailer "
     "after it was never read"),

    ("reader/the-trailers-that-are-read-are-the-last-ones",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "    for start in starts[-MAX_TRAILERS:]:",
     "    for start in starts[:MAX_TRAILERS]:",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "an incremental update appends, so reading the first trailers reports the "
     "file as it was before it was encrypted"),

    ("reader/a-comment-may-stand-before-the-dictionary",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "    return nl + 1",
     "    return limit",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "comments were skipped inside the dictionary but not at its door, so a "
     "file that wrote one there had its trailer declared absent"),

    ("reader/the-token-is-a-key-only-where-a-key-can-be",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "        if (b == b\"/\" and depth == 1 and not in_array",
     "        if (b == b\"/\" and True",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "an array element and a nested dictionary's value both read as the "
     "trailer's encryption reference, telling a producer to unprotect a file "
     "that was never protected"),

    ("reader/one-element-may-not-carry-unbounded-attributes",
     "packages/vdi2770/src/vdi2770/xmlread.py",
     "        if len(attrs) > MAX_ATTRIBUTES_PER_ELEMENT:",
     "        if False:",
     ["packages/vdi2770/tests/test_the_tree_bounds_what_it_builds.py"],
     "the schema check is quadratic in the attributes on one element: 12,000 "
     "of them in a 27 KiB archive cost 13.6 s"),

    ("reader/a-document-may-not-carry-unbounded-attributes",
     "packages/vdi2770/src/vdi2770/xmlread.py",
     "        if attributes > MAX_ATTRIBUTES:",
     "        if False:",
     ["packages/vdi2770/tests/test_the_tree_bounds_what_it_builds.py"],
     "a per-element cap alone lets a sender pay the per-element cost once for "
     "every element they care to write"),

    ("runner/a-path-that-blocks-is-a-path-we-cannot-read",
     "src/vdi2770_validate/runner.py",
     "    if not stat.S_ISREG(os.stat(path).st_mode):",
     "    if False:",
     ["tests/test_defences.py"],
     "opening a FIFO with no writer waits forever, and the handler that keeps "
     "one bad path from stopping a sweep catches exceptions, not hangs"),

    ("rules/a-repeated-name-is-not-a-bad-checksum",
     "src/vdi2770_validate/rules/files.py",
     '                     or (because is not None and because.kind == "ambiguous-name"))',
     "                     or False)",
     ["tests/test_a_member_we_cannot_read_is_not_a_pass.py"],
     "the bytes read fine; F1 told the producer to re-create the archive and "
     "send it again, which reproduces the same archive"),

    ("rules/two-rules-name-one-folder-one-way",
     "src/vdi2770_validate/rules/container.py",
     '            named = [folder_path(f) + "/" for f in as_folders[:5]]',
     "            named = list(as_folders[:5])",
     ["tests/test_documents_delivered_as_folders.py"],
     "`Z9` said `AB393/` and `Z13` said `./AB393/` in one report, and a reader "
     "has to work out they are the same place"),

    ("gates/an-exception-nobody-can-catch-by-name",
     "packages/vdi2770/src/vdi2770/__init__.py",
     '"XmlTooLarge",',
     "",
     ["packages/vdi2770/tests/test_it_stands_alone.py"],
     "XmlTooLarge was raised at the boundary and not exported, so the release "
     "fingerprint could not see it and a caller could not catch it"),

    ("gates/canonical-form-is-read-not-grepped",
     "src/vdi2770_validate/names.py",
     "from vdi2770 import nfc",
     "import unicodedata\n\n\ndef _nfc_again(name):\n"
     "    return unicodedata.normalize(\"NFC\", name)\n\n\nfrom vdi2770 import nfc  # noqa: E402",
     ["tests/test_layering.py"],
     "the check for a second definition was a grep, so a comment naming the "
     "function counted as one -- and a real second import did not"),

    ("runner/the-budget-is-charged-before-the-work",
     "src/vdi2770_validate/runner.py",
     '            elements += (c.metadata_bytes.count(b"<") - c.metadata_bytes.count(b"</"))',
     "            pass",
     ["tests/test_a_document_we_would_not_build_is_not_malformed.py"],
     "counting the tree that came back charged nothing for a document the parser "
     "refused, and refusing is the expensive path"),

    ("runner/a-container-we-did-not-model-is-not-judged",
     "src/vdi2770_validate/runner.py",
     "            c, declared=declared if modelled else None,",
     "            c, declared=declared or frozenset(),",
     ["tests/test_a_document_we_would_not_build_is_not_malformed.py"],
     "`None` is what tells the two rules that read the model that nobody knows; "
     "an empty set tells them the container declares nothing, and a conforming "
     "archive got Z11 and Z3 beside the X6 saying we had not looked"),

    ("gates/a-checkout-without-tags-is-not-a-package-without-releases",
     "tools/api_fingerprint.py",
     "    tags = {t for t in got.stdout.split() if t}",
     '    tags = {t for t in got.stdout.split() if t} or {"sdk-v0"}',
     ["tests/test_the_api_record_holds.py"],
     "a --depth 1 --no-tags clone made every guard answer `not published`, and a "
     "moved surface recorded cleanly under a version live on PyPI"),

    ("gates/a-publishing-workflow-checks-the-sweep-is-complete",
     ".github/workflows/release.yml",
     "        run: make oracle-fully-swept",
     "        run: true",
     ["tests/test_ci_parity.py"],
     "OUTSIDE_CHECK stated the requirement in prose and enforced nothing"),

    ("reader/the-number-of-trailers-scanned-is-bounded",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "    for start in starts[-MAX_TRAILERS:]:",
     "    for start in starts:",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "without a bound on how many dictionaries are walked, the per-dictionary "
     "budget multiplies: 16,000 bare `trailer` keywords cost 135 s"),

    ("reader/an-encrypt-in-a-comment-is-not-a-key",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     '        if b == b"%":                    # comment, to the end of the line',
     "        if False:",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "the token used to be found by a regex over raw bytes, so `/Encrypt` in a "
     "comment told the sender their unencrypted file was encrypted"),

    ("gates/the-baseline-is-checked-against-its-tag-unconditionally",
     "tools/api_fingerprint.py",
     '            if not _published(recorded["version"]):',
     "            if False:",
     ["tests/test_the_api_record_holds.py"],
     "guarding the authenticity check on the recorded version made it depend on a "
     "value the editor chooses: name a tag that does not exist and it never runs"),

    ("gates/the-bundled-schema-is-compiled-once",
     "src/vdi2770_validate/xsdvalidate.py",
     "@lru_cache(maxsize=1)\ndef _schema():",
     "def _schema():",
     ["tests/test_the_schema_check_is_bounded.py"],
     "999 document containers -- a legitimate delivery -- spent 21 of 26 seconds "
     "recompiling the same XSD once per container"),

    # --- the canary -------------------------------------------------------
    ("canary/a-comment-nobody-reads",
     "src/vdi2770_validate/report.py",
     '"""Rendering.',
     '"""Rendering, which is what this module does.',
     ["tests/test_readme_sample.py"],
     "MUST SURVIVE: if this dies, the harness reports red for everything"),
]
CANARY = "canary/a-comment-nobody-reads"


def clear(tree: Path) -> None:
    for cache in tree.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def run(tree: Path, checks: list) -> int:
    """Whatever the row names: a pytest selection, or a gate that is a tool.

    Several gates in this project are not tests — the coverage baseline, the
    oracle sweep, the API fingerprint, the wheel. A table that could only run
    pytest reported "nothing caught" for those and was wrong about it.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    tools = [c for c in checks if c.startswith("tools/")]
    tests = [c for c in checks if not c.startswith("tools/")]
    worst = 0
    for spec in tools:
        code = subprocess.run([sys.executable, *spec.split()],
                              cwd=tree, capture_output=True, text=True, env=env).returncode
        worst = worst or code
    if tests:
        code = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               *tests], cwd=tree, capture_output=True, text=True,
                              env=env).returncode
        worst = worst or code
    return worst


def apply(tree: Path, row) -> None:
    _id, rel, old, new, _tests, _why = row
    f = tree / rel
    text = f.read_text(encoding="utf-8")
    found = text.count(old)
    if found != 1:
        raise SystemExit(f"{_id}: the anchor appears {found} times in {rel}; the table has "
                         f"drifted from the code and the row proves nothing")
    f.write_text(text.replace(old, new), encoding="utf-8")
    f.touch()
    clear(tree)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()

    if not a.run:
        for _id, rel, _old, _new, tests, why in TABLE:
            print(f"{_id}\n    {rel}\n    dies in: {', '.join(tests)}\n    why: {why}")
        print(f"\n{len(TABLE)} rows, one of them the canary.")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "tree"
        shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "build", "dist", "*.egg-info", ".pytest_cache", ".ruff_cache"))
        if subprocess.run([sys.executable, "tools/make_fixtures.py"],
                          cwd=tree, capture_output=True).returncode:
            print("could not build the fixtures in the copy", file=sys.stderr)
            return 1

        survivors, broken = [], []
        for row in TABLE:
            _id, rel, old, new, tests, _why = row
            pristine = (tree / rel).read_text(encoding="utf-8")

            clear(tree)
            if run(tree, tests) != 0:
                broken.append(f"{_id}: the tests it names already fail before the mutation")
                continue

            apply(tree, row)
            code = run(tree, tests)
            (tree / rel).write_text(pristine, encoding="utf-8")
            (tree / rel).touch()
            clear(tree)
            # Restoring the source is not restoring the tree. A row whose checks
            # include `make_fixtures.py` leaves the fixtures the *mutated*
            # generator produced — one row deleted a fixture and the next three
            # rows then failed their own baseline, which the harness reported as
            # "the tests it names already fail before the mutation". A harness
            # that poisons the tree it is measuring measures itself.
            if subprocess.run([sys.executable, "tools/make_fixtures.py"],
                              cwd=tree, capture_output=True).returncode:
                print(f"{_id}: could not rebuild the fixtures after restoring the tree",
                      file=sys.stderr)
                return 1

            if code == 5:
                broken.append(f"{_id}: the selection {tests} collects nothing")
            elif code == 0:
                survivors.append(_id)
                print(f"  survived  {_id}")
            else:
                print(f"  killed    {_id}")

        problems = list(broken)
        if CANARY not in survivors:
            problems.append(f"the canary {CANARY} died. Everything above it is unreliable: "
                            f"a harness that reports red for a change that does not matter "
                            f"is reporting red for everything.")
        real = [s for s in survivors if s != CANARY]
        if real:
            problems.append(f"mutations nothing caught: {real}")

        for p in problems:
            print(p, file=sys.stderr)
        if problems:
            return 1
        print(f"\n{len(TABLE) - 1} mutations, all caught; the canary survived.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
