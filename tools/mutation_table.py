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
     "        c.present,",
     "        c.file_names,",
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
     "    for name in sorted(set(members.present) - accounted_for - structural - collides):",
     "    for name in set(members.present) - accounted_for - structural - collides:",
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
     "    declared = _declared_trailer(data)",
     "    declared = None",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "the file declares where its cross-reference is; guessing instead is how "
     "this scan has been wrong five times"),

    ("reader/the-trailers-that-are-read-are-the-last-ones",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     '        at = data.rfind(b"trailer", 0, end)',
     '        at = data.find(b"trailer", len(data) - end)',
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "an incremental update appends, so reading the first trailers reports the "
     "file as it was before it was encrypted"),

    ("reader/a-comment-may-stand-before-the-dictionary",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "    hit = _NEWLINE.search(data, i, limit)",
     "    hit = None",
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
     "        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)",
     '        fd = os.open(path, os.O_RDONLY)',
     ["tests/test_defences.py"],
     "a blocking open on a FIFO with no writer waits forever, and the handler "
     "that keeps one bad path from stopping a sweep catches exceptions, not "
     "hangs"),

    ("rules/a-repeated-name-is-not-a-bad-checksum",
     "src/vdi2770_validate/rules/files.py",
     '                     or (because is not None and because.kind == "ambiguous-name"))',
     "                     or False)",
     ["tests/test_a_member_we_cannot_read_is_not_a_pass.py"],
     "the bytes read fine; F1 told the producer to re-create the archive and "
     "send it again, which reproduces the same archive"),

    ("rules/two-rules-name-one-folder-one-way",
     "src/vdi2770_validate/rules/container.py",
     '        named = [folder_path(f) + "/" for f, _ in as_folders[:5]]',
     "        named = [f for f, _ in as_folders[:5]]",
     ["tests/test_documents_delivered_as_folders.py"],
     "`Z9` said `AB393/` and `Z13` said `./AB393/` in one report, and a reader "
     "has to work out they are the same place"),

    ("gates/the-reader-ships-before-the-validator-that-pins-it",
     ".github/workflows/release.yml",
     "        run: python tools/check_release_order.py",
     "        run: true",
     ["tests/test_ci_parity.py::test_the_publishing_workflow_checks_the_reader_shipped_first"],
     "tagging the validator first publishes a distribution pip cannot resolve, "
     "under a number PyPI will not let anyone reuse"),

    ("gates/an-unreleased-reader-is-not-a-tagged-one",
     "tools/check_release_order.py",
     '    if f"sdk-v{floor}" not in tags:',
     "    if False:",
     ["tests/test_the_release_order_is_enforced.py"],
     "the check that makes the workflow step mean anything"),

    ("gates/a-checkout-without-tags-cannot-answer-the-order",
     "tools/check_release_order.py",
     "    if not tags:",
     "    if False:",
     ["tests/test_the_release_order_is_enforced.py"],
     "no tags is indistinguishable from nothing having been released, and "
     "answering yes there is how a release gate fails open"),

    ("gates/the-sweep-must-cover-what-is-on-disk",
     "tools/capture_oracle.py",
     '        if set(recorded["containers"]) != here:',
     "        if False:",
     ["tests/test_the_sweep_gate_can_fail.py"],
     "a sweep missing a container entirely answered complete, and a release "
     "publishes divergence counts that exclude it"),

    ("gates/a-sweep-over-nothing-is-not-a-sweep",
     "tools/capture_oracle.py",
     '        assert here, "no containers found; this gate would pass over nothing"',
     "        pass",
     ["tests/test_the_sweep_gate_can_fail.py"],
     "with no containers on disk and none recorded the sets agree, and the "
     "gate reports every one of 0 containers verified"),

    ("gates/a-published-version-is-not-recorded-over",
     "tools/api_fingerprint.py",
     '            if _published(now["version"]):',
     "            if False:",
     ["tests/test_the_api_record_holds.py"],
     "restoring the baseline from the previous tag is what this tool's own "
     "messages tell you to do, and it walked a surface change into a live "
     "version"),

    ("reader/a-hex-string-can-hold-the-dictionarys-close",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     '        if b == b"<":                    # hex string, which may hold `3c3c`',
     "        if False:",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "`<41>>` closes the dictionary a byte early without it, and the "
     "encryption reference after it is never seen"),

    ("gates/the-offline-promise-survives-being-caught",
     "tests/test_offline.py",
     "        raise ReachedForTheNetwork(\"the tool tried to open a socket\")",
     '        raise AssertionError("the tool tried to open a socket")',
     ["tests/test_offline.py"],
     "the tool turns any `Exception` into a finding, so a guard that raises one "
     "is swallowed and both sides of the comparison come back equal"),

    ("runner/a-container-we-did-not-parse-is-not-schema-checked",
     "src/vdi2770_validate/runner.py",
     "                         if tree is not None else [])",
     "                         if True else [])",
     ["tests/test_defences.py"],
     "the budget refused the parse, and this would hand xmlschema the very "
     "document the reader called too expensive, with no tree behind it"),

    ("rules/one-sibling-list-per-parent-not-per-error",
     "src/vdi2770_validate/xsdvalidate.py",
     "        if kids_of is None:\n            return node.find_all(tag)",
     "        if True:\n            return node.find_all(tag)",
     ["tests/test_the_schema_check_is_bounded.py"],
     "rebuilding the sibling list once per error to index one of them was 38% "
     "of the 29 seconds this area exists because of"),

    ("rules/a-name-that-matches-two-members-is-not-absent",
     "src/vdi2770_validate/rules/files.py",
     "            spellings = members.spelled_more_than_one_way(f.file_name)",
     "            spellings = ()",
     ["tests/test_two_spellings_are_two_files.py"],
     "`resolve` answers None for `no such file` and for `which one did you "
     "mean`, and F1 read the second as the first: a file the archive holds "
     "twice was reported absent, with a remedy that deletes a correct "
     "declaration"),

    ("rules/two-names-that-print-alike-are-told-apart",
     "src/vdi2770_validate/rules/container.py",
     "            if not alike:",
     "            if True:",
     ["tests/test_two_spellings_are_two_files.py"],
     "the reader got the same line twice with nothing on it to say which "
     "member each was about, or that the difference was in the encoding"),

    ("rules/a-locked-member-is-not-a-truncated-transfer",
     "src/vdi2770_validate/rules/files.py",
     '            elif "encrypted" in (because.detail or "").lower():',
     "            elif False:",
     ["tests/test_a_member_we_cannot_read_is_not_a_pass.py"],
     "re-creating the archive reproduces the same encrypted member and the "
     "same finding"),

    ("gates/a-tag-that-is-not-the-version-stops-the-release",
     ".github/workflows/release.yml",
     '          test "$tag" = "$pkg" || { echo "tag $tag != package $pkg"; exit 1; }',
     "          true",
     ["tests/test_two_packages_publish_separately.py"],
     "the test asserted the shell variable was created, not that it was "
     "compared: a tag saying 0.2.0 could publish a tree saying 0.1.9, and the "
     "number is on the index forever"),

    ("gates/a-release-checkout-can-see-its-tags",
     ".github/workflows/release.yml",
     "        with: { fetch-depth: 0 }",
     "        with: { fetch-depth: 1 }",
     ["tests/test_two_packages_publish_separately.py"],
     "without the tags the assertions comparing this tree against sdk-v* skip "
     "rather than fail, in the one workflow that authorises a publish"),

    ("gates/ci-installs-the-reader-from-this-tree",
     ".github/workflows/ci.yml",
     "          python -m pip install -e packages/vdi2770\n",
     "",
     ["tests/test_ci_parity.py"],
     "pip then resolves the pin from an index and every result in the run is "
     "about a different reader than the commit's"),

    ("runner/metadata-we-could-not-model-declares-nothing-known",
     "src/vdi2770_validate/runner.py",
     "        if c.kind in (Kind.DOCUMENT, Kind.DOCUMENTATION) and document is None:",
     "        if False:",
     ["tests/test_a_declared_zip_is_a_payload.py"],
     "a parse the reader refused left `declared` empty rather than unknown, so "
     "X6 said the metadata was not modelled while Z11 accused a member of not "
     "being in it"),

    ("rules/a-folder-count-under-the-cap-is-exact",
     "src/vdi2770_validate/rules/container.py",
     "        capped = len(named) >= MAX_FOLDERS",
     "        capped = True",
     ["tests/test_a_finding_says_something_true.py"],
     "the hedge was derived from the count rather than from whether collection "
     "stopped, so removing the cap printed an exact number under `at least`"),

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

    ("reader/the-trailer-reading-is-bounded-in-total",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "        budget -= max(spent, 1)          # never free, or a decoy is unbounded",
     "        budget -= 0",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "without a bound on how much of all the trailers is read, the "
     "per-dictionary budget multiplies: 16,000 bare `trailer` keywords cost 135 s"),

    ("reader/a-trailer-inside-a-comment-is-not-one",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     '        if not _is_a_keyword_here(data, at, len(b"trailer")):',
     "        if False:",
     ["packages/vdi2770/tests/test_the_public_api.py"],
     "`%trailer` is the word after a `%`, which no conformant reader sees as a "
     "keyword; reading them spent the budget the real trailer needed"),

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

    ("rules/a-name-that-prints-alike-is-spelled-out",
     "src/vdi2770_validate/names.py",
     "    hidden = any(_draws_nothing(c) for c in name)",
     "    return name",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "the helper was pinned by nothing: `return name` left the whole suite green "
     "while two members of one archive printed as the same line"),

    ("rules/an-escape-cannot-be-forged",
     "src/vdi2770_validate/names.py",
     '        _spelled(c) if c == "\\\\" or _draws_nothing(c)',
     "        _spelled(c) if _draws_nothing(c)",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "a member named with a literal backslash rendered exactly like a member "
     "named with the character that escape stands for"),

    ("rules/one-path-is-not-one-name",
     "src/vdi2770_validate/rules/container.py",
     "            relation[key] = (len({extracts_to(n) for n in group}) == 1,",
     "            relation[key] = (True,",
     ["tests/test_two_spellings_are_two_files.py"],
     "`Z10` grouped on `folder_path` and then said `extract to the same path` "
     "about members that land on two, in a report where `F2` treated them as two"),

    ("rules/one-name-is-not-one-path",
     "src/vdi2770_validate/rules/container.py",
     "                             len({nfc(n) for n in group}) == 1)",
     "                             False)",
     ["tests/test_two_spellings_are_two_files.py"],
     "the look-alike sentence is the one the rule exists for; forcing the branch "
     "off left a canonically equivalent pair described as something else"),

    ("rules/a-difference-nobody-can-see-is-spelled-out",
     "src/vdi2770_validate/names.py",
     "        if differing and easy_to_miss:",
     "        if False:",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "one Cyrillic letter among the Latin ones made `M3` name the name it was "
     "asking for, and `escaped` cannot see it -- both sides are their own NFC"),

    ("rules/collisions-are-joined-once",
     "src/vdi2770_validate/rules/container.py",
     "            alike = _partners(group, place[name])",
     "            alike = sorted(n for n in container.duplicate_names\n"
     "                           if folder_path(n) == folder_path(name) and n != name)",
     ["tests/test_two_spellings_are_two_files.py"],
     "filtering the collisions inside a loop over them cost 12.86 s for 1,600 "
     "pairs from a 316 KiB archive, past every budget the reader has"),

    ("rules/case-is-a-collision-somewhere",
     "src/vdi2770_validate/rules/container.py",
     "        folded.setdefault(ignoring_case(member), []).append(member)",
     "        folded.setdefault(member, []).append(member)",
     ["tests/test_two_spellings_are_two_files.py"],
     "two members a recipient's disk stores as one file came back clean, exit 0, "
     "and following the remedy that was offered made the report cleaner still"),

    ("rules/one-finding-does-not-name-the-whole-group",
     "src/vdi2770_validate/rules/container.py",
     "    stride = max(1, len(group) // MAX_ALIKE)",
     "    stride = 0 if False else 1",
     ["tests/test_two_spellings_are_two_files.py"],
     "a stride of one leaves the tail of a big group named by nobody: ten of a "
     "hundred and ten appeared neither as a subject nor in anybody's list"),

    ("runner/the-archive-is-parsed-once-per-container",
     "src/vdi2770_validate/runner.py",
     "    read_member = zipread.member_reader(raw, allowed=accepted)",
     "    read_member = lambda name: zipread.member_bytes(raw, name, allowed=accepted)  # noqa: E731",
     ["tests/test_defences.py"],
     "asking for every declared PDF re-parsed the central directory each time: "
     "20.6 s for 2,000 of them from a 210 KiB archive, 18.5 s of it in the parse"),

    ("rules/the-declared-paths-are-normalised-once",
     "src/vdi2770_validate/rules/files.py",
     "    collides = {n for n in container.duplicate_names if extracts_to(n) in landed_on}",
     "    collides = {n for n in container.duplicate_names\n"
     "                if any(extracts_to(n) == extracts_to(a) for a in accounted_for)}",
     ["tests/test_defences.py"],
     "matching each colliding member against every declared path recomputed the "
     "split-and-join on both sides at every pair"),

    ("rules/a-difference-a-reader-can-see-is-left-alone",
     "src/vdi2770_validate/names.py",
     "                                and published[plain_p[k]].isascii())",
     "                                and False)",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "spelling an all-ASCII difference buries the one character that matters: "
     "`identification` against `Identification` came back as two walls of hex"),

    ("rules/free-text-has-no-path-segments",
     "src/vdi2770_validate/names.py",
     "    stops = ([i for i, c in enumerate(name) if c == \"/\"] if segments else []) + [len(name)]",
     "    stops = [i for i, c in enumerate(name) if c == \"/\"] + [len(name)]",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "splitting a class name on `/` made the ordinary spaces around it the edges "
     "of segments, and spelled them out while the slash stayed plain"),

    ("reader/a-refused-name-is-not-a-near-miss",
     "packages/vdi2770/src/vdi2770/zipread.py",
     "            if refused and n in refused:",
     "            if False:",
     ["tests/test_a_reserved_name_at_the_root_is_at_the_root.py"],
     "one report said a `../` name was refused outright and, two lines on, that "
     "the file was found at a place and just needed moving"),

    ("rules/an-unopened-folders-member-is-not-judged-by-the-root",
     "src/vdi2770_validate/rules/container.py",
     "            if _inside(folder_path(m.name), unopened_here):",
     "            if False:",
     ["tests/test_a_declared_zip_is_a_payload.py"],
     "a folder whose unread metadata declares `cad.zip` drew `Z3`/`Z11` beside "
     "the `Z13` saying nobody looked"),

    ("rules/declared-a-file-and-classified-a-container-is-a-disagreement",
     "src/vdi2770_validate/rules/container.py",
     "            if child is not None and child.kind in (Kind.DOCUMENT, Kind.DOCUMENTATION):",
     "            if False:",
     ["tests/test_a_declared_zip_is_a_payload.py"],
     "a document container inside a document container shipped with exit 0, by "
     "the exact instruction the rule's own remedy gives"),

    ("rules/a-declared-payload-is-not-a-candidate-container",
     "src/vdi2770_validate/rules/container.py",
     "                and _candidate(d.where.member)",
     "                and True",
     ["tests/test_a_declared_zip_is_a_payload.py"],
     "at the depth limit an innermost documentation container holding only its "
     "declared payload delivered nothing, and nothing said so"),

    ("reader/a-near-miss-is-skipped-only-for-an-unsafe-name",
     "packages/vdi2770/src/vdi2770/zipread.py",
     '         if defect.kind == "unsafe-member-name"})',
     '         if True})',
     ["tests/test_a_finding_says_something_true.py"],
     "skipping every refusal erased the one line saying the archive nearly has "
     "a metadata file"),

    ("reader/an-indirect-object-is-what-makes-it-a-pdf",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "    is_pdf = _has_an_indirect_object(data)",
     "    is_pdf = True",
     ["tests/test_the_main_document_is_looked_at.py"],
     "eight bytes named VDI2770_Main.pdf were a PDF, and the container was clean"),

    ("reader/the-object-probe-looks-behind-before-it-agrees",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "                _OBJ_BEFORE.search(data[max(0, at - 48):at]):",
     "                True:",
     ["tests/test_amplification.py"],
     "any occurrence of the word `obj` would have made a text file a PDF"),

    ("reader/a-name-belongs-to-a-namespace",
     "packages/vdi2770/src/vdi2770/xmlread.py",
     "        return [c for c in self.children if c.tag == tag and c.ns == NS]",
     "        return [c for c in self.children if c.tag == tag]",
     ["tests/test_a_name_belongs_to_a_namespace.py"],
     "another vocabulary's DocumentClassification satisfied the rule that a "
     "document must carry one, and the schema complaint walker named the wrong "
     "line because it counted children a different way from the schema"),

    ("rules/the-vocabulary-is-decided-by-the-children-too",
     "src/vdi2770_validate/runner.py",
     "                                  or any(k.ns == NS for k in tree.children))",
     "                                  or True)",
     ["tests/test_a_name_belongs_to_a_namespace.py"],
     "a prefix declared on the root and left off every element read as a "
     "document with nothing in it"),

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
        # `env=` here too. The run below sets it for every check it starts and
        # this one, which builds the fixtures the whole sweep is measured
        # against, did not -- so the copy this sweep runs in was seeded with
        # bytecode written wherever `sys.pycache_prefix` points, and a mutation
        # is exactly the file most likely to be restored to its previous size
        # inside the same second.
        if subprocess.run([sys.executable, "tools/make_fixtures.py"],
                          cwd=tree, capture_output=True,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1")).returncode:
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
                              cwd=tree, capture_output=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1")).returncode:
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
