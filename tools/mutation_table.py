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
import re
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
     "packages/vdi2770/src/vdi2770/validate/model.py",
     "        return (sum(1 for f in self.findings if f.severity is sev)\n"
     "                + self._suppressed_severity.get(sev, 0))",
     "        return sum(1 for f in self.findings if f.severity is sev)",
     ["tests/test_one_rule_cannot_flood_the_report.py", "tests/test_cli.py"],
     "a bounded listing would have become a quieter verdict"),

    ("runner/a-crashing-rule-is-a-finding",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "        for f in findings:\n            report.add(f)",
     "        for f in list(findings)[:0]:\n            report.add(f)",
     ["tests/test_a_rule_that_crashes_does_not_kill_the_run.py"],
     "one rule's exception killed a whole sweep"),

    ("cli/one-bad-path-does-not-stop-the-rest",
     "packages/vdi2770/src/vdi2770/validate/cli.py",
     'why = getattr(e, "strerror", None) or str(e)',
     'why = e.strerror or str(e)',
     ["tests/test_cli.py"],
     "the handler that existed to keep going was itself stopping"),

    ("rules/z8-counts-document-containers",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "        if not delivered and not stopped and not as_folders:",
     "        if not container.children and not stopped and not as_folders:",
     ["tests/test_z8_counts_document_containers.py"],
     "a documentation container delivering nothing came back clean"),

    ("rules/f2-emits-in-a-fixed-order",
     "packages/vdi2770/src/vdi2770/validate/rules/files.py",
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
     "packages/vdi2770/src/vdi2770/validate/rules/files.py",
     "from typing import Iterator",
     "import zipfile\nfrom typing import Iterator",
     ["tests/test_layering.py"],
     "a rule could check the spelling instead of the model"),

    ("gates/our-half-of-the-sweep-is-current",
     "packages/vdi2770/src/vdi2770/validate/data/rules.json",
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
     ".github/workflows/release.yml",
     "      - name: The gate must pass on the tagged tree\n        run: make check",
     "      - name: The gate must pass on the tagged tree\n        run: true",
     ["tests/test_ci_parity.py"],
     "a release workflow listed the gate's targets by hand and ran six of nine; "
     "the three it missed were the three newest"),

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
     "packages/vdi2770/pyproject.toml",
     '"vdi2770.validate" = ["data/*.json", "data/*.xsd"]',
     '"vdi2770.validate" = ["data/*.json", "data/*.xsd"]\n\n'
     '[tool.setuptools.data-files]\n"share/vdi2770" = ["README.md"]',
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

    ("gates/the-front-page-names-the-classes-that-are-disputed",
     "README.md",
     "disagree on five English ones**",
     "disagree on six English ones**",
     ["tests/test_the_docs_count_what_they_claim.py::"
      "test_the_readme_names_the_classes_the_two_sources_actually_disagree_on"],
     "the front page tells a reader which rows to distrust, by id, and nothing "
     "derived it -- a corrected name or an added class would leave the list "
     "reading true"),

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
     "packages/vdi2770/src/vdi2770/validate/rules/schema.py",
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
     "packages/vdi2770/src/vdi2770/validate/runner.py",
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
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
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
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)",
     '        fd = os.open(path, os.O_RDONLY)',
     ["tests/test_defences.py"],
     "a blocking open on a FIFO with no writer waits forever, and the handler "
     "that keeps one bad path from stopping a sweep catches exceptions, not "
     "hangs"),

    ("rules/a-repeated-name-is-not-a-bad-checksum",
     "packages/vdi2770/src/vdi2770/validate/rules/files.py",
     '                     or (because is not None and because.kind == "ambiguous-name"))',
     "                     or False)",
     ["tests/test_a_member_we_cannot_read_is_not_a_pass.py"],
     "the bytes read fine; F1 told the producer to re-create the archive and "
     "send it again, which reproduces the same archive"),

    ("rules/two-rules-name-one-folder-one-way",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     '        named = [folder_path(f) + "/" for f, _ in as_folders[:5]]',
     "        named = [f for f, _ in as_folders[:5]]",
     ["tests/test_documents_delivered_as_folders.py"],
     "`Z9` said `AB393/` and `Z13` said `./AB393/` in one report, and a reader "
     "has to work out they are the same place"),

    ("gates/the-rules-ship-after-the-reader-they-pin",
     ".github/workflows/release.yml",
     "            if python tools/check_release_order.py; then exit 0; fi",
     "            if true; then exit 0; fi",
     ["tests/test_two_packages_publish_separately.py::"
      "test_the_order_gate_runs_and_not_with_the_flag_that_skips_the_index"],
     "publishing the rules first puts a distribution pip cannot resolve on the "
     "index, under a number PyPI will not let anyone reuse"),

    ("gates/an-unreleased-package-is-not-a-tagged-one",
     "tools/check_release_order.py",
     '    if f"v{version}" not in tags:',
     "    if False:",
     ["tests/test_the_release_order_is_enforced.py"],
     "the check that makes the workflow step mean anything"),

    ("gates/the-two-tag-namespaces-are-told-apart",
     "tools/api_fingerprint.py",
     "ONE_TAG_FROM = (0, 7, 0)",
     "ONE_TAG_FROM = (0, 0, 0)",
     ["tests/test_the_api_record_holds.py::"
      "test_a_version_from_before_the_merge_is_looked_up_in_the_old_namespace"],
     "`v0.5.0` is a validator release whose reader said 0.3.1, so reading an "
     "older reader version out of the `v*` namespace answers about a "
     "different distribution"),

    ("gates/a-floor-that-is-not-this-release-is-refused",
     "tools/check_release_order.py",
     "    if Version(pinned) != Version(version):",
     "    if False:",
     ["tests/test_the_release_order_is_enforced.py"],
     "a floor below this release lets the alias resolve to an engine older "
     "than the release it stands for, and a floor above it resolves to "
     "nothing at all -- neither state can be reported by any index"),

    ("gates/the-engine-is-floored-at-this-release-or-not-at-all",
     "tools/check_release_order.py",
     "    if len(only) != 1 or only[0].operator not in (\"==\", \">=\"):",
     "    if False:",
     ["tests/test_the_release_order_is_enforced.py::"
      "test_a_requirement_that_lets_pip_choose_an_older_engine_is_refused"],
     "a bare name, a ceiling, a compatible release or an exclusion each let a "
     "resolver install an engine this release was never run against"),

    ("gates/the-dependency-array-ends-where-the-array-ends",
     "tools/check_release_order.py",
     '    start = re.search(r"^dependencies = \\[", text, re.M)',
     '    start = re.search(r"^dependencies = X", text, re.M)',
     ["tests/test_the_release_order_is_enforced.py::"
      "test_the_gate_can_read_this_repositorys_own_manifest"],
     "the pattern that read this list stopped at the `]` inside "
     "`vdi2770[validate]`, so the gate refused every release with `this release no longer depends on vdi2770` -- standing between the two publishes, "
     "where a refusal lands with half a release on the index"),

    ("gates/the-two-distributions-cannot-claim-one-import-name",
     "pyproject.toml",
     '\nwhere = ["src"]',
     '\nwhere = ["src", "packages/vdi2770/src"]',
     ["tests/test_the_two_halves_carry_one_version.py::"
      "test_no_two_distributions_here_claim_one_import_name"],
     "two distributions shipping one import package install over each other "
     "without complaint, and uninstalling either deletes files the other is "
     "still using -- reproduced against the published 0.6.0"),

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
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "                         if tree is not None else [])",
     "                         if True else [])",
     ["tests/test_defences.py"],
     "the budget refused the parse, and this would hand xmlschema the very "
     "document the reader called too expensive, with no tree behind it"),

    ("rules/one-sibling-list-per-parent-not-per-error",
     "packages/vdi2770/src/vdi2770/validate/xsdvalidate.py",
     "        if kids_of is None:\n            return node.find_all(tag)",
     "        if True:\n            return node.find_all(tag)",
     ["tests/test_the_schema_check_is_bounded.py"],
     "rebuilding the sibling list once per error to index one of them was 38% "
     "of the 29 seconds this area exists because of"),

    ("rules/a-name-that-matches-two-members-is-not-absent",
     "packages/vdi2770/src/vdi2770/validate/rules/files.py",
     "            spellings = members.spelled_more_than_one_way(f.file_name)",
     "            spellings = ()",
     ["tests/test_two_spellings_are_two_files.py"],
     "`resolve` answers None for `no such file` and for `which one did you "
     "mean`, and F1 read the second as the first: a file the archive holds "
     "twice was reported absent, with a remedy that deletes a correct "
     "declaration"),

    ("rules/two-names-that-print-alike-are-told-apart",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "            if not alike:",
     "            if True:",
     ["tests/test_two_spellings_are_two_files.py"],
     "the reader got the same line twice with nothing on it to say which "
     "member each was about, or that the difference was in the encoding"),

    ("rules/a-locked-member-is-not-a-truncated-transfer",
     "packages/vdi2770/src/vdi2770/validate/rules/files.py",
     '            elif "encrypted" in (because.detail or "").lower():',
     "            elif False:",
     ["tests/test_a_member_we_cannot_read_is_not_a_pass.py"],
     "re-creating the archive reproduces the same encrypted member and the "
     "same finding"),

    ("gates/a-tag-that-is-not-the-version-stops-the-release",
     ".github/workflows/release.yml",
     '          pkg=$(python -c "import sys; sys.path.insert(0,\'src\'); import '
     'vdi2770_validate as v; print(v.__version__)")\n'
     '          test "$tag" = "$pkg" || { echo "tag $tag != package $pkg"; exit 1; }',
     '          pkg=$(python -c "import sys; sys.path.insert(0,\'src\'); import '
     'vdi2770_validate as v; print(v.__version__)")\n          true',
     ["tests/test_two_packages_publish_separately.py"],
     "the test asserted the shell variable was created, not that it was "
     "compared: a tag saying 0.2.0 could publish a tree saying 0.1.9, and the "
     "number is on the index forever"),

    ("gates/a-tag-that-is-not-the-readers-version-stops-it-too",
     ".github/workflows/release.yml",
     '          pkg=$(python -c "import sys; sys.path.insert(0,\'packages/vdi2770/src\'); '
     'import vdi2770 as v; print(v.__version__)")\n'
     '          test "$tag" = "$pkg" || { echo "tag $tag != package $pkg"; exit 1; }',
     '          pkg=$(python -c "import sys; sys.path.insert(0,\'packages/vdi2770/src\'); '
     'import vdi2770 as v; print(v.__version__)")\n          true',
     ["tests/test_two_packages_publish_separately.py"],
     "one tag drives both distributions, and either half left on an older "
     "number is a pair that was never built"),

    ("gates/the-pin-names-the-reader-that-was-built",
     "packages/vdi2770/pyproject.toml",
     'version = "0.8.0.dev0"',
     'version = "0.7.1"',
     ["tools/check_wheel.py"],
     "the two manifests agree with each other and the artifacts do not: the "
     "smoke test installs the pair with --no-deps and cannot notice, and on an "
     "index there is no --no-deps"),

    ("gates/each-build-asks-about-what-it-builds",
     ".github/workflows/release.yml",
     "        run: python -m build packages/vdi2770 --outdir dist/",
     "        run: python -m build --outdir dist/",
     ["tests/test_two_packages_publish_separately.py::"
      "test_each_build_asks_the_index_about_the_distribution_it_actually_builds"],
     "the index is asked about one distribution and the other is uploaded; "
     "every other assertion stays green and PyPI does not take it back"),

    ("gates/a-release-checkout-can-see-its-tags",
     ".github/workflows/release.yml",
     "      # skip \u2014 in the one workflow that authorises a publish.\n"
     "      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n        with: { fetch-depth: 0 }",
     "      # skip \u2014 in the one workflow that authorises a publish.\n"
     "      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n        with: { fetch-depth: 1 }",
     ["tests/test_two_packages_publish_separately.py"],
     "without the tags the assertions comparing this tree against a release tag "
     "skip rather than fail, in the one workflow that authorises a publish"),

    ("gates/the-rules-checkout-can-see-them-too",
     ".github/workflows/release.yml",
     "      # and a default checkout is `--depth 1 --no-tags`.\n"
     "      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n        with: { fetch-depth: 0 }",
     "      # and a default checkout is `--depth 1 --no-tags`.\n"
     "      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n        with: { fetch-depth: 1 }",
     ["tests/test_two_packages_publish_separately.py"],
     "the order gate reads the tag history, and a gate that cannot see fails "
     "closed here -- which stops the release rather than breaking it, but stops "
     "it for a reason nobody wrote down"),

    ("gates/every-workflow-installs-the-reader-from-the-tree",
     ".github/workflows/oracle.yml",
     "          python -m pip install -e packages/vdi2770\n",
     "",
     ["tests/test_ci_parity.py::"
      "test_every_workflow_that_installs_this_project_installs_the_reader_first"],
     "the sweep is where the reference implementation's verdicts come from, and "
     "one workflow had this line while the other did not -- the gate that "
     "compared CI against the Makefile read one file and could not see it"),

    ("gates/ci-installs-this-repository-from-this-tree",
     ".github/workflows/ci.yml",
     '          python -m pip install -e ".[dev]"',
     "          python -m pip install vdi2770",
     ["tests/test_ci_parity.py"],
     "the run is then about whatever the index happens to hold rather than "
     "about the commit"),

    ("runner/metadata-we-could-not-model-declares-nothing-known",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "        if c.kind in (Kind.DOCUMENT, Kind.DOCUMENTATION) and (document is None",
     "        if False and (document is None",
     ["tests/test_a_declared_zip_is_a_payload.py"],
     "a parse the reader refused left `declared` empty rather than unknown, so "
     "X6 said the metadata was not modelled while Z11 accused a member of not "
     "being in it"),

    ("rules/a-folder-count-under-the-cap-is-exact",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
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
     "packages/vdi2770/src/vdi2770/validate/names.py",
     "from vdi2770 import nfc",
     "import unicodedata\n\n\ndef _nfc_again(name):\n"
     "    return unicodedata.normalize(\"NFC\", name)\n\n\nfrom vdi2770 import nfc  # noqa: E402",
     ["tests/test_layering.py"],
     "the check for a second definition was a grep, so a comment naming the "
     "function counted as one -- and a real second import did not"),

    ("runner/the-budget-is-charged-before-the-work",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     '            elements += (c.metadata_bytes.count(b"<") - c.metadata_bytes.count(b"</"))',
     "            pass",
     ["tests/test_a_document_we_would_not_build_is_not_malformed.py"],
     "counting the tree that came back charged nothing for a document the parser "
     "refused, and refusing is the expensive path"),

    ("runner/a-container-we-did-not-model-is-not-judged",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
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
     "packages/vdi2770/src/vdi2770/validate/xsdvalidate.py",
     "@lru_cache(maxsize=1)\ndef _schema():",
     "def _schema():",
     ["tests/test_the_schema_check_is_bounded.py"],
     "999 document containers -- a legitimate delivery -- spent 21 of 26 seconds "
     "recompiling the same XSD once per container"),

    ("rules/a-name-that-prints-alike-is-spelled-out",
     "packages/vdi2770/src/vdi2770/validate/names.py",
     "    hidden = any(_draws_nothing(c) for c in name)",
     "    return name",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "the helper was pinned by nothing: `return name` left the whole suite green "
     "while two members of one archive printed as the same line"),

    ("rules/an-escape-cannot-be-forged",
     "packages/vdi2770/src/vdi2770/validate/names.py",
     '        _spelled(c) if c == "\\\\" or _draws_nothing(c)',
     "        _spelled(c) if _draws_nothing(c)",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "a member named with a literal backslash rendered exactly like a member "
     "named with the character that escape stands for"),

    ("rules/one-path-is-not-one-name",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "            relation[key] = (len({extracts_to(n) for n in group}) == 1,",
     "            relation[key] = (True,",
     ["tests/test_two_spellings_are_two_files.py"],
     "`Z10` grouped on `folder_path` and then said `extract to the same path` "
     "about members that land on two, in a report where `F2` treated them as two"),

    ("rules/one-name-is-not-one-path",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "                             len({nfc(n) for n in group}) == 1)",
     "                             False)",
     ["tests/test_two_spellings_are_two_files.py"],
     "the look-alike sentence is the one the rule exists for; forcing the branch "
     "off left a canonically equivalent pair described as something else"),

    ("rules/a-difference-nobody-can-see-is-spelled-out",
     "packages/vdi2770/src/vdi2770/validate/names.py",
     "        if differing and easy_to_miss:",
     "        if False:",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "one Cyrillic letter among the Latin ones made `M3` name the name it was "
     "asking for, and `escaped` cannot see it -- both sides are their own NFC"),

    ("rules/collisions-are-joined-once",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "            alike = _partners(group, place[name])",
     "            alike = sorted(n for n in container.duplicate_names\n"
     "                           if folder_path(n) == folder_path(name) and n != name)",
     ["tests/test_two_spellings_are_two_files.py"],
     "filtering the collisions inside a loop over them cost 12.86 s for 1,600 "
     "pairs from a 316 KiB archive, past every budget the reader has"),

    ("rules/case-is-a-collision-somewhere",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "        folded.setdefault(ignoring_case(member), []).append(member)",
     "        folded.setdefault(member, []).append(member)",
     ["tests/test_two_spellings_are_two_files.py"],
     "two members a recipient's disk stores as one file came back clean, exit 0, "
     "and following the remedy that was offered made the report cleaner still"),

    ("rules/one-finding-does-not-name-the-whole-group",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "    stride = max(1, len(group) // MAX_ALIKE)",
     "    stride = 0 if False else 1",
     ["tests/test_two_spellings_are_two_files.py"],
     "a stride of one leaves the tail of a big group named by nobody: ten of a "
     "hundred and ten appeared neither as a subject nor in anybody's list"),

    ("runner/the-archive-is-parsed-once-per-container",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "    read_member = zipread.member_reader(raw, allowed=accepted)",
     "    read_member = lambda name: zipread.member_bytes(raw, name, allowed=accepted)  # noqa: E731",
     ["tests/test_defences.py"],
     "asking for every declared PDF re-parsed the central directory each time: "
     "20.6 s for 2,000 of them from a 210 KiB archive, 18.5 s of it in the parse"),

    ("rules/the-declared-paths-are-normalised-once",
     "packages/vdi2770/src/vdi2770/validate/rules/files.py",
     "    collides = {n for n in container.duplicate_names if extracts_to(n) in landed_on}",
     "    collides = {n for n in container.duplicate_names\n"
     "                if any(extracts_to(n) == extracts_to(a) for a in accounted_for)}",
     ["tests/test_defences.py"],
     "matching each colliding member against every declared path recomputed the "
     "split-and-join on both sides at every pair"),

    ("rules/a-difference-a-reader-can-see-is-left-alone",
     "packages/vdi2770/src/vdi2770/validate/names.py",
     "                                and published[plain_p[k]].isascii())",
     "                                and False)",
     ["tests/test_two_names_that_print_alike_are_told_apart.py"],
     "spelling an all-ASCII difference buries the one character that matters: "
     "`identification` against `Identification` came back as two walls of hex"),

    ("rules/free-text-has-no-path-segments",
     "packages/vdi2770/src/vdi2770/validate/names.py",
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
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "            if _inside(folder_path(m.name), unopened_here):",
     "            if False:",
     ["tests/test_a_declared_zip_is_a_payload.py"],
     "a folder whose unread metadata declares `cad.zip` drew `Z3`/`Z11` beside "
     "the `Z13` saying nobody looked"),

    ("rules/declared-a-file-and-classified-a-container-is-a-disagreement",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
     "            if child is not None and child.kind in (Kind.DOCUMENT, Kind.DOCUMENTATION):",
     "            if False:",
     ["tests/test_a_declared_zip_is_a_payload.py"],
     "a document container inside a document container shipped with exit 0, by "
     "the exact instruction the rule's own remedy gives"),

    ("rules/a-declared-payload-is-not-a-candidate-container",
     "packages/vdi2770/src/vdi2770/validate/rules/container.py",
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

    ("rules/the-vocabulary-is-decided-by-what-the-model-came-out-as",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "            if elsewhere and not (document.identifiers or document.classifications",
     "            if elsewhere or not (document.identifiers or document.classifications",
     ["tests/test_a_name_belongs_to_a_namespace.py"],
     "a root outside the namespace whose children are inside it builds the whole "
     "model, and was told that nothing in it is a VDI 2770 element"),

    ("rules/a-vocabulary-we-cannot-read-is-unknown-not-empty",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "                                                              or foreign is not None):",
     "                                                              or False):",
     ["tests/test_a_name_belongs_to_a_namespace.py"],
     "an empty model read as 'this container declares nothing', so a declared "
     "payload was told to declare itself"),

    ("reader/part-four-names-no-conformance-level-on-purpose",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     '        return part.group(1).decode() + ("" if part.group(1) == b"4" else "?")',
     '        return part.group(1).decode() + "?"',
     ["tests/test_pdf_precision.py"],
     "every PDF/A-4 file was recorded as claiming a level it does not claim"),

    ("reader/the-first-claim-is-the-first-one-in-the-file",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "    for begins, stop in sorted(spans):",
     "    for begins, stop in spans:",
     ["tests/test_pdf_precision.py"],
     "which of two disagreeing PDF/A claims was reported came down to packet "
     "syntax, which says nothing about which packet is the document's own"),

    ("report/the-figure-counts-what-the-archive-lists",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "        listed = c.present or c.file_names",
     "        listed = c.file_names",
     ["tests/test_the_report_says_how_much_it_read.py"],
     "refusing a member took it out of the denominator, so the figure improved "
     "when this tool declined to look"),

    ("report/an-archive-nobody-opened-is-still-one-archive",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "    report.read.archives_found = 1\n    if root is _CRASHED:",
     "    if root is _CRASHED:",
     ["tests/test_the_report_says_how_much_it_read.py"],
     "the one path that says nothing in the archive was checked read "
     "`0 of 0 archives` and called itself complete"),

    ("report/an-unreadable-archive-is-not-an-opened-one",
     "packages/vdi2770/src/vdi2770/validate/runner.py",
     "        if c.kind is not Kind.UNREADABLE:",
     "        if True:",
     ["tests/test_the_report_says_how_much_it_read.py"],
     "a file that did not open as a ZIP was counted as an archive this read "
     "opened"),

    ("report/complete-knows-what-the-numbers-cannot",
     "packages/vdi2770/src/vdi2770/validate/report.py",
     "                         and not any(report.count_about(s, About.TOOL)",
     "                         and not any(False and report.count_about(s, About.TOOL)",
     ["tests/test_the_report_says_how_much_it_read.py"],
     "a container this tool declined to model had every number full and called "
     "the read complete"),

    ("report/the-coverage-line-is-not-a-note",
     "packages/vdi2770/src/vdi2770/validate/report.py",
     '    lines.append("  read " + ", ".join(parts))',
     '    lines.append("  read " + ", ".join(parts)) if show_info else None',
     ["tests/test_the_report_says_how_much_it_read.py"],
     "the flag that hides notes hid the line that says how much of this tool ran"),

    ("cli/the-run-says-what-it-never-verifies",
     "packages/vdi2770/src/vdi2770/validate/cli.py",
     '        print("\\nThis tool does not verify PDF/A conformance. It reports the "',
     '        _unused = ("\\nThis tool does not verify PDF/A conformance. It reports the "',
     ["tests/test_cli.py"],
     "the refusal this project leads with was carried only by notes, and the "
     "flag a CI log reaches for removes every one of them"),

    ("cli/a-gate-can-choose-to-fail-on-warnings",
     "packages/vdi2770/src/vdi2770/validate/cli.py",
     '                args.fail_on == "warning" and rep.count(Severity.WARNING)):',
     "                False):",
     ["tests/test_cli.py"],
     "eight containers here come back exit 0 carrying a warning and a gate had "
     "no way to say it wanted none of them"),

    # --- the canary -------------------------------------------------------
    ("canary/a-comment-nobody-reads",
     "packages/vdi2770/src/vdi2770/validate/report.py",
     '"""Rendering.',
     '"""Rendering, which is what this module does.',
     ["tests/test_readme_sample.py"],
     "MUST SURVIVE: if this dies, the harness reports red for everything"),
]
#: The front door. Seven ways to put something false on the page a stranger
#: reads first, each one leaving every other gate green.
FRONT_DOOR = [
    ("gates/the-page-points-at-the-picture-it-committed",
     "docs/assets/tenseconds.svg",
     "vdi2770-validate — real output, colour added",
     "vdi2770-validate — output, colour added",
     ["tests/test_the_front_page_points_at_what_it_shows.py::"
      "test_every_picture_on_the_page_is_the_one_committed"],
     "the committed picture changes and the page's ?v= does not, so GitHub's "
     "image proxy keeps serving the old one to everybody who has been here"),

    ("gates/the-shot-draws-only-what-the-tool-prints",
     "tools/gen_door.py",
     '"A file named in the metadata is not in the container"',
     '"A file named in the metadata is missing from the container"',
     ["tests/test_the_front_door_pictures_are_true.py::"
      "test_every_line_drawn_in_the_shot_is_one_the_tool_really_prints"],
     "the terminal shot shows a sentence no version ever printed, which reads "
     "exactly like one that did"),

    ("gates/the-elision-in-the-shot-says-what-it-elided",
     "tools/gen_door.py",
     '"… 1 more error (Z13) and 1 warning (Z9)"',
     '"… 1 more error (Z9) and 1 warning (Z13)"',
     ["tests/test_the_front_door_pictures_are_true.py::"
      "test_the_elision_in_the_shot_says_what_it_elided"],
     "a marked gap is a claim about the output, and this project has already "
     "shipped one that stood for findings of a different kind"),

    ("gates/the-page-quotes-the-requirement-the-project-declares",
     "README.md",
     "`vdi2770[validate]>=0.8.0.dev0`",
     "`vdi2770[validate]>=0.7.0`",
     ["tests/test_the_front_page_points_at_what_it_shows.py::"
      "test_the_requirement_the_page_quotes_is_the_one_the_project_declares"],
     "the paragraph whose whole subject is that the pin is exact quotes a pin "
     "the project does not declare"),

    ("gates/the-badge-counts-the-catalogue",
     "README.md",
     "rules-41_each_with_a_remedy",
     "rules-42_each_with_a_remedy",
     ["tests/test_the_front_page_points_at_what_it_shows.py::"
      "test_the_badge_that_counts_rules_counts_the_catalogue"],
     "a number inside a shields.io URL is not the shape the prose gate reads, "
     "so the badge could say anything at all"),

    ("gates/the-gallery-shows-the-severity-the-tool-prints",
     "README.md",
     "| `error Z13` — and it says plainly",
     "| `warn Z13` — and it says plainly",
     ["tests/test_the_front_page_points_at_what_it_shows.py::"
      "test_every_rule_the_gallery_names_is_a_rule_with_that_severity"],
     "the shortest promise on the page -- ship this, it says that -- advertises "
     "a verdict the tool does not give"),

    ("gates/a-claim-is-held-where-it-was-last-made",
     "tests/conftest.py",
     "    for heading, text in changelog_sections():",
     "    for heading, text in changelog_sections()[:1]:",
     # Not the standalone-file count, which was the first choice and survived
     # this exact mutation: that claim is restated in the section being written,
     # so cutting the reader down to one section still finds it. The row was
     # testing nothing. This claim is made by the release below and by nothing
     # above it, which is the whole condition the reader exists for.
     ["tests/test_the_docs_count_what_they_claim.py::"
      "test_the_changelog_counts_the_trailer_shapes_it_claims_are_pinned"],
     "a claim stated in the release below stops being read the moment a new "
     "section opens, and every number it pins goes unchecked"),
]

RELATIONSHIPS = [
    ("rules/a-half-read-delivery-cannot-say-what-is-missing",
     "packages/vdi2770/src/vdi2770/validate/rules/delivery.py",
     "    if not read_everything:\n        return",
     "    if not read_everything:\n        pass",
     ["tests/test_a_delivery_carries_the_documents_it_refers_to.py::"
      "test_a_reference_is_not_dangling_when_this_tool_declined_to_read_the_delivery"],
     "documents delivered as folders are in the container and this tool does "
     "not open them, so without the guard our refusal is billed to the sender "
     "as an error about their delivery"),

    ("rules/the-main-document-is-the-one-that-makes-it-an-error",
     "packages/vdi2770/src/vdi2770/validate/rules/delivery.py",
     'r = rule("M11" if from_main else "M12")',
     'r = rule("M11")',
     ["tests/test_a_delivery_carries_the_documents_it_refers_to.py::"
      "test_the_same_defect_from_a_document_that_is_not_the_main_one_is_also_an_error"],
     "the reference implementation raises this as information unless the main "
     "document is the one pointing, and `obligation: reference` promises the "
     "judgement is theirs -- one severity turns their note into our error"),

    ("rules/an-identifier-is-the-number-and-the-domain",
     "packages/vdi2770/src/vdi2770/validate/rules/delivery.py",
     "    return (document_id.id.strip().casefold(),\n"
     "            document_id.domain_id.strip().casefold())",
     "    return (document_id.id.strip().casefold(),)",
     ["tests/test_a_delivery_carries_the_documents_it_refers_to.py::"
      "test_the_domain_is_part_of_the_identity"],
     "the same drawing number issued by two domains is two documents, and "
     "comparing the bare number accepts a delivery carrying something else"),
]

BASIS_ROWS = [
    ("report/every-finding-says-what-it-rests-on",
     "packages/vdi2770/src/vdi2770/validate/report.py",
     '        lines.append(f"         {basis(f.rule)}")',
     '        pass',
     ["tests/test_the_report_says_what_its_judgement_rests_on.py::"
      "test_the_text_report_prints_a_basis_for_every_finding_it_lists"],
     "the person at a terminal reads an imperative with nothing behind it, "
     "while the JSON beside it says the requirement is somebody else's program"),

    ("report/the-basis-is-derived-and-not-written",
     "packages/vdi2770/src/vdi2770/validate/report.py",
     '        lines.append(f"         {basis(f.rule)}")',
     '        lines.append("         per the reference implementation")',
     ["tests/test_the_report_says_what_its_judgement_rests_on.py::"
      "test_the_two_surfaces_say_the_same_thing_about_every_finding"],
     "one risk written on two surfaces drifts: the text would call our own "
     "judgement somebody else's, with the JSON still telling the truth"),

    ("rules/a-document-cannot-answer-its-own-reference",
     "packages/vdi2770/src/vdi2770/validate/rules/delivery.py",
     "for _container, doc in documents if doc is not excluding",
     "for _container, doc in documents",
     ["tests/test_a_delivery_carries_the_documents_it_refers_to.py::"
      "test_a_document_does_not_satisfy_its_own_reference"],
     "`ContainerValidator` drops the current document before comparing, so a "
     "relationship naming its own id is dangling to them and was not to us"),
]

STREAM_ROWS = [
    ("reader/the-marker-does-not-count-the-word-that-ends-a-stream",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     '        if data[max(0, m.start() - 3):m.start()] == b"end":\n            continue',
     '        if False:\n            continue',
     ["packages/vdi2770/tests/test_the_stream_budget_counts_streams.py::"
      "test_the_scan_stops_where_the_budget_says_and_not_at_half_of_it"],
     "`endstream` ends in `stream`, so every stream takes two places out of "
     "`MAX_STREAMS` and a published budget of 512 stops at 257"),

    ("reader/the-stream-marker-stays-a-bare-literal",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     '_STREAM = re.compile(rb"stream\\r?\\n")',
     '_STREAM = re.compile(rb"(?<![A-Za-z])stream\\r?\\n")',
     ["packages/vdi2770/tests/test_the_stream_budget_counts_streams.py::"
      "test_the_marker_stays_a_bare_literal"],
     "a filter at the front of the pattern reads like the tidy version and "
     "costs the literal prefilter, so a large file is walked rather than "
     "skimmed -- on the reader's untrusted-input path. It also drops a marker "
     "after any letter, which is a second defect the same edit brings back"),

    ("rules/a-scan-stopped-by-the-stream-budget-names-it",
     "packages/vdi2770/src/vdi2770/validate/rules/pdf.py",
     'f"one file" if stopped.reason == "streams" else "")',
     'f"one file" if False else "")',
     ["tests/test_the_report_says_what_its_judgement_rests_on.py::"
      "test_a_scan_stopped_by_the_stream_budget_names_it"],
     "the number was withheld because the marker double-counted; the defect is "
     "gone and withholding it on a new reason would be rationalising"),
]

STREAM_ROWS.append(
    ("reader/a-rejected-marker-still-costs-a-place",
     "packages/vdi2770/src/vdi2770/pdfread.py",
     "        if examined >= MAX_STREAM_MARKERS:",
     "        if False:",
     ["packages/vdi2770/tests/test_the_stream_budget_counts_streams.py::"
      "test_markers_the_filter_rejects_still_cost_something"],
     "only yielded markers reach the caller's count, so a member made entirely "
     "of closings advances nothing and is walked end to end -- and it arrives "
     "small, because `endstream` compresses to almost nothing"))

UPGRADE_ROWS = [
    ("gates/an-upgrade-is-judged-by-running-the-command",
     "tools/check_upgrade_paths.py",
     '    code, said = env.command("--version")\n'
     '    expect(code == 0, f"{why}: `{COMMAND} --version` gave {code}: {said}")',
     '    code, said = env.command("--version")',
     ["tests/test_ci_parity.py::"
      "test_the_upgrade_harness_judges_by_running_the_command"],
     "the harness would agree with `pip check` instead of contradicting it, "
     "which is the one thing it exists to do -- a destroyed install has "
     "consistent metadata and no entry point"),

    ("gates/the-release-gate-runs-before-the-publish-it-guards",
     ".github/workflows/release.yml",
     "    needs: [reader-is-on-the-index, upgrade-gate]",
     "    needs: reader-is-on-the-index",
     ["tests/test_ci_parity.py::"
      "test_nothing_publishes_before_the_check_that_guards_it"],
     "the upgrade check would run beside the publish instead of before it, so "
     "a release that breaks an existing install goes out while the job that "
     "would have said so is still starting"),
]

DECLARED_ROWS = [
    ("gates/an-import-nobody-declared-is-caught-here-not-in-ci",
     "pyproject.toml",
     'dev = ["build==1.4.4", "packaging==26.3", "pytest==8.3.4", "PyYAML==6.0.3",',
     'dev = ["build==1.4.4", "packaging==26.3", "pytest==8.3.4",',
     ["tests/test_the_suite_declares_what_it_imports.py"],
     "a package the suite imports would be declared nowhere, which is green on "
     "the machine that happens to have it and red on every machine that does "
     "not -- and this project has already spent a red main on exactly that"),
]

WORKFLOW_ROWS = [
    ("gates/the-gate-installs-the-release-being-made",
     ".github/workflows/release.yml",
     "        run: python tools/check_upgrade_paths.py --from dist",
     "        run: python tools/check_upgrade_paths.py",
     ["tests/test_ci_parity.py::"
      "test_nothing_publishes_before_the_check_that_guards_it"],
     "the job before the publish would read the index and never install the "
     "wheel it is standing in front of -- the one state nobody else tests"),

    ("gates/a-step-cannot-swallow-the-check-it-runs",
     ".github/workflows/release.yml",
     "        run: python tools/check_upgrade_paths.py --from dist",
     "        run: python tools/check_upgrade_paths.py --from dist || true",
     ["tests/test_ci_parity.py::"
      "test_nothing_publishes_before_the_check_that_guards_it"],
     "a failed upgrade check would report a passed job, which is the gate "
     "removed by four characters that read as caution in a diff"),

    ("gates/a-publish-has-no-condition-of-its-own",
     ".github/workflows/release.yml",
     "  publish-rules:\n",
     "  publish-rules:\n    if: ${{ !cancelled() }}\n",
     ["tests/test_ci_parity.py::"
      "test_nothing_publishes_before_the_check_that_guards_it"],
     "the publish would fire when the gate it waits for has failed -- one of "
     "several spellings for that, which is why no condition is allowed rather "
     "than a list of the ones somebody thought of"),

]

GUARDED_ROWS = [
    ("gates/a-try-is-not-an-excuse-unless-it-catches-the-absence",
     "tests/test_the_suite_declares_what_it_imports.py",
     "    named = caught.elts if isinstance(caught, ast.Tuple) else [caught]",
     "    return True\n    named = caught.elts if isinstance(caught, ast.Tuple) else [caught]",
     ["tests/test_the_suite_declares_what_it_imports.py::"
      "test_a_try_that_catches_something_else_does_not_excuse_the_import"],
     "the word `try` would excuse an undeclared import whatever the handler "
     "catches, and a `try` that catches ValueError does nothing at all about a "
     "package that is not installed"),

]

LOCATION_ROWS = [
    ("gates/underneath-the-stdlib-directory-is-not-the-stdlib",
     "tests/test_the_suite_declares_what_it_imports.py",
     '    for installed in _SITE:\n        if _within(origin, installed):\n            return "third-party"\n    if any(part in _INSTALLED_DIRS for part in origin.parts):\n        return "third-party"\n    if _within(origin, _STDLIB) or _within(origin, _BASE):\n        return "stdlib"',
     '    if _within(origin, _STDLIB) or _within(origin, _BASE):\n        return "stdlib"\n    for installed in _SITE:\n        if _within(origin, installed):\n            return "third-party"',
     ["tests/test_the_suite_declares_what_it_imports.py::"
      "test_a_package_installed_under_the_stdlib_directory_is_not_the_stdlib"],
     "an interpreter that keeps its site-packages inside the stdlib directory "
     "-- Apple's command-line tools, Debian's dist-packages -- would have "
     "setuptools and pkg_resources excused as the standard library, and the "
     "machine that shows it is the developer's, never CI"),

]

UPGRADE_BODY_ROWS = [
    ('gates/an-install-whose-library-is-gone-is-not-a-tool-that-runs',
     'tools/check_upgrade_paths.py',
     '    for name in ("vdi2770", "vdi2770_validate"):\n        code, said = env.imports(name)\n        expect(code == 0, f"{why}: import {name} failed\\n{said}")',
     '    pass',
     ['tests/test_ci_parity.py::test_the_upgrade_harness_judges_by_running_the_command'],
     'an install with metadata and a console script and no library behind them would be called a tool that runs -- and this assertion was already unbreakable before it went through the environment, because the harness replaced the function it used for every case at once'),

    ('gates/a-version-is-compared-as-a-whole-word',
     'tools/check_upgrade_paths.py',
     '    expect(installed in said.split(), (',
     '    expect(installed in said, (',
     ['tests/test_ci_parity.py::test_the_upgrade_harness_judges_by_running_the_command'],
     '0.8.0 is a substring of 0.8.0.post1, so a build reporting a version it is not would pass the check written to catch exactly that'),

    ('gates/the-release-being-made-is-one-of-the-cases',
     'tools/check_upgrade_paths.py',
     '         case_4_the_release_being_made,\n',
     '',
     ['tests/test_ci_parity.py::test_every_case_the_harness_runs_asks_that_question'],
     'the case that installs the wheels about to be published would be outside every structural check again, which is how deleting its verdict left the suite green in the case standing closest to the publish'),

]

WINDOWS_ROWS = [
    ("gates/the-standard-library-is-a-tree-not-a-directory",
     'tests/test_the_suite_declares_what_it_imports.py',
     '    if _within(origin, _STDLIB) or _within(origin, _BASE):',
     '    if _within(origin, _STDLIB):',
     ['tests/test_the_suite_declares_what_it_imports.py::test_an_extension_module_outside_the_stdlib_directory_still_is_the_stdlib'],
     "Windows keeps the extension modules in `DLLs`, a sibling of `Lib` "
     "rather than a child, so `unicodedata` would be reported as an "
     "undeclared package on every Windows run -- the same assumption that "
     "excused setuptools here, broken in the other direction and invisible "
     "from either machine"),

]

MANIFEST_ROWS = [
    ('gates/a-renamed-directory-still-claims-the-name-it-ships',
     'tests/test_the_two_halves_carry_one_version.py',
     '    for claimed in (tools.get("package-dir") or {}):\n        if claimed:                                  # `"" = "src"` names nothing\n            names.add(claimed.split(".")[0])',
     '    pass',
     ['tests/test_the_two_halves_carry_one_version.py::test_a_manifest_that_renames_a_directory_claims_the_name_it_ships'],
     "a manifest mapping `vdi2770` onto the rules' directory would ship the reader's top-level name and the gate written to make that collision unreachable would answer with the directory's name and pass"),

    ('gates/an-excluded-directory-is-not-shipped',
     'tests/test_the_two_halves_carry_one_version.py',
     '                    if any(_excluded(name, pattern) for pattern in excluded):\n                        continue',
     '                    pass',
     ['tests/test_the_two_halves_carry_one_version.py::test_a_directory_the_manifest_excludes_is_not_shipped'],
     'a directory the manifest excludes would be counted as shipped, manufacturing a collision that turns the release red on a correct tree'),

    ('gates/a-flat-layout-does-not-ship-the-working-directory',
     'tests/test_the_two_halves_carry_one_version.py',
     'def _is_package_dir(child):\n    if child.name.startswith(".") or child.name in NOT_PACKAGES:\n        return False',
     'def _is_package_dir(child):\n    if False:\n        return False',
     ['tests/test_the_two_halves_carry_one_version.py::test_a_flat_layout_does_not_ship_the_working_directory'],
     'a flat layout is legal and would report `.venv` as a shipped package -- present on the machine that has one and absent in CI, so the same commit would have two answers'),

    ('gates/two-distributions-cannot-install-one-command',
     'tests/test_the_two_halves_carry_one_version.py',
     '    return set(_parsed(path).get("project", {}).get("scripts") or {})',
     '    return {"vdi2770-validate"}',
     ['tests/test_the_two_halves_carry_one_version.py::test_no_two_distributions_here_claim_one_command'],
     'a console script is a file in bin/ like any other, written by whichever distribution installed last and deleted by whichever is uninstalled first -- the failure this file is about, one directory over, and the import-name gate cannot see it'),

]

AGREEMENT_ROWS = [
    ('agreement/a-record-somewhere-else-is-not-this-installation',
     'packages/vdi2770/src/vdi2770/validate/agreement.py',
     '            if base != here or dist.read_text("METADATA") is None:\n                continue',
     '            if False:\n                continue',
     ['tests/test_the_two_halves_have_to_agree.py::test_a_record_somewhere_else_on_the_path_is_not_this_installations'],
     'the single-file build would be refused on any machine that had also installed the reader, and a layered install over a base image with it -- the artifact sold to people with no route to an index, handed a `pip install` as the remedy'),

    ('agreement/a-build-artifact-is-not-an-install-record',
     'packages/vdi2770/src/vdi2770/validate/agreement.py',
     '            if base != here or dist.read_text("METADATA") is None:',
     '            if base != here:',
     ['tests/test_the_two_halves_have_to_agree.py::test_a_build_artifact_beside_the_code_is_not_an_install_record'],
     'a stale `.egg-info` in a source checkout -- which this repository has, and the Makefile already says lingers -- would refuse every verdict inside `make test`'),

    ('agreement/the-answer-is-computed-once',
     'packages/vdi2770/src/vdi2770/validate/agreement.py',
     '    if not _ANSWER:\n        _ANSWER.append(_disagreement())\n    return _ANSWER[0]',
     '    return _disagreement()',
     ['tests/test_the_two_halves_have_to_agree.py::test_it_is_computed_once'],
     'a coherent, correct, still-running process would start refusing every verdict because somebody upgraded the environment in another window -- the loaded version cannot change, so re-reading buys only that'),

    ('agreement/two-spellings-of-one-version-are-one-version',
     'packages/vdi2770/src/vdi2770/validate/agreement.py',
     '    if folded(reader) != folded(ruleset):',
     '    if reader != ruleset:',
     ['tests/test_the_two_halves_have_to_agree.py::test_the_same_release_spelled_two_ways_is_one_release'],
     '`0.8.0-rc1` is what a hand-edited literal writes and `0.8.0rc1` is what the build backend records, so a working install would be refused over punctuation'),

    ('agreement/the-refusal-is-not-a-verdict-on-a-container',
     'packages/vdi2770/src/vdi2770/validate/cli.py',
     '        except InstallationDisagrees:',
     '        except InstallationDisagrees if False else RuntimeError:',
     ['tests/test_the_two_halves_have_to_agree.py::test_the_refusal_reaches_the_command_as_three_and_writes_no_report'],
     'the refusal would be caught as `cannot read it`, counted against the container, and written into the JSON as a document stamped `toolVersion` by the install that had just said it could not account for itself'),

    ('agreement/the-version-is-not-answered-by-half-an-installation',
     'packages/vdi2770/src/vdi2770/validate/cli.py',
     '    p.add_argument("--version", action=_Version, nargs=0, help="show the version")',
     '    p.add_argument("--version", action="version", version=VERSION)',
     ['tests/test_the_two_halves_have_to_agree.py::test_the_version_is_not_answered_by_half_an_installation'],
     '`--version` would print the rules half during parsing, before anything could ask -- true about the package it came from and false about the tool that would run'),

    ('agreement/a-library-caller-goes-through-it-too',
     'packages/vdi2770/src/vdi2770/validate/runner.py',
     '    refuse_if_disagreeing()\n    report = Report(target=name)',
     '    report = Report(target=name)',
     ['tests/test_the_two_halves_have_to_agree.py::test_a_caller_who_never_touches_the_command_still_goes_through_it'],
     'the front page sells `import vdi2770_validate` as a way to use this, and that caller would get verdicts from an installation nothing had asked about'),

]

BOOT_ROWS = [
    ('agreement/the-check-runs-before-what-it-guards',
     'packages/vdi2770/src/vdi2770/validate/entry.py',
     '    from .agreement import refuse_early\n    early = refuse_early()\n    if early is not None:\n        return early\n    # Only now. Everything below this line can need the reader.\n    from .cli import _run\n    return _run(argv)',
     '    from .cli import _run\n    from .agreement import refuse_early\n    early = refuse_early()\n    if early is not None:\n        return early\n    return _run(argv)',
     ['tests/test_the_two_halves_have_to_agree.py::test_the_check_runs_before_anything_that_needs_the_reader'],
     "the command would die at import in the state the check exists to catch -- `cli` reaches the reader's public surface through `report` and `model`, and that surface is what is missing -- so the answer would be a traceback and `rc=1`, this tool's code for a container that has findings"),

    ('agreement/the-single-file-build-goes-through-the-same-door',
     'tools/build_zipapp.py',
     'from vdi2770.validate.entry import run  # noqa: E402 - after the path is arranged\n\nsys.exit(run())',
     'from vdi2770.validate.cli import _run  # noqa: E402 - after the path is arranged\n\nsys.exit(_run())',
     ['tests/test_the_two_halves_have_to_agree.py::test_every_door_this_project_ships_is_the_same_door'],
     'the single-file build would skip the check the other two doors take, which is how one door got the console handling and the other kept the crash'),

]

PLATFORM_ROWS = [
    ('gates/a-test-is-not-named-after-its-own-input',
     'conftest.py',
     '    if isinstance(val, (bytes, bytearray)):\n        return f"{argname}<{len(val)}B>"',
     '    if False:\n        return None',
     ['tests/test_a_test_name_is_a_name.py'],
     'a case handed a whole document is named after it, which is unreadable in a log everywhere and fatal on Windows -- pytest puts the id in PYTEST_CURRENT_TEST and the platform refuses an environment variable over 32767 characters, so the case passes and then fails in teardown'),

    ('gates/a-directory-that-holds-the-stdlib-is-not-an-install-directory',
     'tests/test_the_suite_declares_what_it_imports.py',
     '    return {d for d in candidates if not _within(stdlib, d)}',
     '    return set(candidates)',
     ['tests/test_the_suite_declares_what_it_imports.py::test_a_directory_that_contains_the_stdlib_is_not_an_install_directory'],
     'Windows offers `sys.prefix` itself as a site directory and the standard library is under it, so with installs checked first every module the interpreter ships would be reported as a package nobody declared'),

    ('gates/a-command-is-a-claim-on-a-file-in-bin',
     'tools/check_paths_are_disjoint.py',
     '                        owned.add(f"command {command}")',
     '                        pass',
     ['tests/test_no_two_distributions_claim_one_path.py::test_two_distributions_that_install_one_command_are_caught'],
     'a wheel RECORD has no bin/ entries at all -- pip synthesises the console scripts at install time -- so comparing recorded paths alone is blind to the files that vanished first the last time an install here was destroyed'),

    ('gates/an-import-name-is-a-claim-on-a-directory',
     'tools/check_paths_are_disjoint.py',
     '    return {f"import {head}"} if rest == "__init__.py" else set()',
     '    return set()',
     ['tests/test_no_two_distributions_claim_one_path.py::test_two_distributions_that_ship_one_import_name_are_caught'],
     'two distributions shipping different files under one top-level directory would pass, and uninstalling either takes the directory the other is importing from'),

    ('gates/two-versions-of-one-distribution-may-share-their-paths',
     'tools/check_paths_are_disjoint.py',
     '            if name_a == name_b:',
     '            if False:',
     ['tests/test_no_two_distributions_claim_one_path.py::test_two_versions_of_one_distribution_may_share_everything'],
     'pip replacing its own files is the normal case, and a gate that forbids it fails every release this project makes'),

]

PUBLISHING_PATH_ROWS = [
    ('release/the-workflow-states-its-own-permission-floor',
     '.github/workflows/release.yml',
     'permissions:\n  contents: read\n',
     '',
     ['tests/test_the_publishing_path_has_three_properties.py::'
      'test_the_release_states_its_own_floor'],
     'three jobs would go back to taking whatever the repository default is -- '
     'a setting nobody reading this file can see, in jobs that install from an '
     'index and run a build backend'),

    ('release/the-publish-action-is-pinned-to-a-commit',
     '.github/workflows/release.yml',
     '          name: sums-rules\n          path: sums/\n      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02  # v4.6.2\n        with:\n          name: dist-rules\n          path: dist/\n\n  # The last thing before the name people type gets a new version behind it.\n  # It installs what is on the index today and then upgrades to the wheel that\n  # is about to replace it, and the verdict is that the command still runs --\n  # `pip check` calls a destroyed install healthy, so it is recorded and not\n  # believed. This cannot protect the reader\'s publish, which has already\n  # happened by the time both wheels exist; it protects the one people install\n  # by name, which is where every upgrade failure here has been.\n  upgrade-gate:\n    needs: [build-reader, build-rules]\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5.6.0\n        with:\n          python-version: "3.12"\n      # Both wheels, into one directory. It downloaded only the rules, and every\n      # case from the fourth onward installs with `--no-index --find-links` and\n      # asks for the engine -- directly, or as the alias\'s own dependency. The\n      # engine\'s wheel was not there, so pip could not resolve and the gate\n      # standing between the two publishes was red on any tag. Nothing noticed:\n      # locally `make` builds both into one directory, so it only failed where\n      # no one had run it.\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-reader\n          path: dist/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-rules\n          path: dist/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: sums-reader\n          path: sums-reader/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: sums-rules\n          path: sums-rules/\n      - name: These are the bytes the build jobs made\n        run: |\n          cat sums-reader/SHA256SUMS sums-rules/SHA256SUMS > /tmp/SHA256SUMS\n          # Counted before it is checked. `sha256sum -c` over a list with no\n          # entries is a check that agrees with everything -- measured, exit 0 --\n          # and whether it happens to refuse depends on which coreutils is\n          # installed. A gate must not rest on that.\n          n="$(wc -l < /tmp/SHA256SUMS)"\n          test "$n" -ge 4 || { echo "only $n files recorded for two builds"; exit 1; }\n          (cd dist && sha256sum -c /tmp/SHA256SUMS)\n          test "$(ls dist | wc -l)" -eq "$n" || {\n            echo "dist/ holds $(ls dist | wc -l) files and $n were recorded; "\n            echo "something is here that no build job made"\n            exit 1; }\n      - name: Both wheels are here, or the gate is checking half a release\n        run: |\n          ls -l dist/\n          test -n "$(ls dist/vdi2770-*.whl 2>/dev/null)" || {\n            echo "no engine wheel in dist/; every case that installs would fail"\n            exit 1; }\n          test -n "$(ls dist/vdi2770_validate-*.whl 2>/dev/null)" || {\n            echo "no alias wheel in dist/"; exit 1; }\n      # Before either publish, so it protects both. The first three cases\n      # install from the live index with no `--find-links`, which before this\n      # ran against an index already holding the new engine. It no longer does,\n      # and that is the right way round: if a new engine broke an old alias, the\n      # remedy is to publish the matched pair, not to withhold it and leave\n      # everyone in the mixed state. The window itself is measured by the case\n      # that simulates it.\n      - name: An install somebody already has must survive this release\n        run: python tools/check_upgrade_paths.py --from dist\n\n  # The only thing between the two uploads. It holds the workflow\'s floor --\n  # `contents: read`, nothing else -- and no environment. (It said "no token",\n  # which is not a thing a job can have: absent a `permissions:` block it takes\n  # whatever the repository\'s default is, and that is a setting, not a fact\n  # about this file.) Two reasons it is its own job rather than a step inside the\n  # publisher. A job that publishes should be download-and-upload and nothing\n  # else, so that re-running it after a failure is one click and repeats no\n  # decision -- which is the whole of the recovery path when the engine is on\n  # the index and the alias is not. And a `pip install` from PyPI, a `git`\n  # subprocess and a script from the tagged tree do not belong in the job that\n  # holds `id-token: write` for a distribution.\n  reader-is-on-the-index:\n    needs: publish-reader\n    runs-on: ubuntu-latest\n    steps:\n      # `fetch-depth: 0`: the gate asks the tag history whether this release is\n      # tagged, and a default checkout is `--depth 1 --no-tags`.\n      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n        with: { fetch-depth: 0 }\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5.6.0\n        with:\n          python-version: "3.12"\n      - name: Install\n        run: python -m pip install --upgrade pip packaging\n      # `needs: publish-reader` proves the upload step ran. It does not prove\n      # the index serves the file, and the alias is unresolvable until it does.\n      # PyPI\'s JSON view can trail the upload, so this is given a few tries --\n      # and refuses at the end rather than guessing, because an alias published\n      # against an engine that is not there cannot be fixed under this version\n      # number.\n      - name: The engine this floors on must be on the index\n        run: |\n          for attempt in 1 2 3 4 5; do\n            if python tools/check_release_order.py; then exit 0; fi\n            echo "the index does not serve it yet (attempt $attempt of 5); waiting"\n            sleep 20\n          done\n          echo "the engine this floors on never appeared on the index"\n          exit 1\n      # And "the JSON view lists it" is not "a machine can install it". This is\n      # the state the alias actually requires, so it is the one that is asked\n      # for before the alias goes out.\n      - name: And a machine can actually install it\n        run: |\n          version="${GITHUB_REF_NAME#v}"\n          for attempt in 1 2 3 4 5; do\n            if python -m pip download --no-deps --only-binary :all: \\\n                 --dest /tmp/probe "vdi2770==$version"; then exit 0; fi\n            echo "not installable yet (attempt $attempt of 5); waiting"\n            sleep 20\n          done\n          echo "vdi2770 $version is listed and cannot be installed"\n          exit 1\n\n  publish-rules:\n    needs: [reader-is-on-the-index, upgrade-gate]\n    runs-on: ubuntu-latest\n    # Not the reader\'s environment. The environment is half of what PyPI keys\n    # the publisher on, so sharing it would let either job publish as the other\n    # package.\n    environment: pypi-vdi2770-validate\n    permissions:\n      id-token: write\n    steps:\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-rules\n          path: dist/\n      # The bytes, not the name. An artifact is immutable and fetched by\n      # name, so this cannot fail without something having gone very wrong --\n      # which is the point: it is the line that turns "the gate tested these\n      # wheels" from an argument about the job graph into a checked fact, and\n      # it is what an independent verifier compares against afterwards.\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: sums-rules\n          path: sums/\n      - name: These are the bytes that were built and tested\n        run: |\n          cat sums/SHA256SUMS\n          # Counted first: `sha256sum -c` over an empty list exits 0 on at\n          # least one coreutils, and this is the last thing that runs before an\n          # upload that cannot be taken back.\n          n="$(wc -l < sums/SHA256SUMS)"\n          test "$n" -ge 2 || { echo "only $n files recorded"; exit 1; }\n          (cd dist && sha256sum -c ../sums/SHA256SUMS)\n          test "$(ls dist | wc -l)" -eq "$n" || {\n            echo "dist/ holds $(ls dist | wc -l) files and $n were recorded; "\n            echo "PyPI would receive something no build job made"\n            exit 1; }\n      # Pinned to a commit, not to `release/v1`. This is the one thing in this\n      # job that is not ours, and it runs while the job holds `id-token: write`\n      # for a real distribution: a moving ref means whatever that ref points at\n      # on the day can mint a publishing token. v1.14.2.\n      - uses: pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33  # v1.14.2',
     '          name: sums-rules\n          path: sums/\n      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02  # v4.6.2\n        with:\n          name: dist-rules\n          path: dist/\n\n  # The last thing before the name people type gets a new version behind it.\n  # It installs what is on the index today and then upgrades to the wheel that\n  # is about to replace it, and the verdict is that the command still runs --\n  # `pip check` calls a destroyed install healthy, so it is recorded and not\n  # believed. This cannot protect the reader\'s publish, which has already\n  # happened by the time both wheels exist; it protects the one people install\n  # by name, which is where every upgrade failure here has been.\n  upgrade-gate:\n    needs: [build-reader, build-rules]\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5.6.0\n        with:\n          python-version: "3.12"\n      # Both wheels, into one directory. It downloaded only the rules, and every\n      # case from the fourth onward installs with `--no-index --find-links` and\n      # asks for the engine -- directly, or as the alias\'s own dependency. The\n      # engine\'s wheel was not there, so pip could not resolve and the gate\n      # standing between the two publishes was red on any tag. Nothing noticed:\n      # locally `make` builds both into one directory, so it only failed where\n      # no one had run it.\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-reader\n          path: dist/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-rules\n          path: dist/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: sums-reader\n          path: sums-reader/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: sums-rules\n          path: sums-rules/\n      - name: These are the bytes the build jobs made\n        run: |\n          cat sums-reader/SHA256SUMS sums-rules/SHA256SUMS > /tmp/SHA256SUMS\n          # Counted before it is checked. `sha256sum -c` over a list with no\n          # entries is a check that agrees with everything -- measured, exit 0 --\n          # and whether it happens to refuse depends on which coreutils is\n          # installed. A gate must not rest on that.\n          n="$(wc -l < /tmp/SHA256SUMS)"\n          test "$n" -ge 4 || { echo "only $n files recorded for two builds"; exit 1; }\n          (cd dist && sha256sum -c /tmp/SHA256SUMS)\n          test "$(ls dist | wc -l)" -eq "$n" || {\n            echo "dist/ holds $(ls dist | wc -l) files and $n were recorded; "\n            echo "something is here that no build job made"\n            exit 1; }\n      - name: Both wheels are here, or the gate is checking half a release\n        run: |\n          ls -l dist/\n          test -n "$(ls dist/vdi2770-*.whl 2>/dev/null)" || {\n            echo "no engine wheel in dist/; every case that installs would fail"\n            exit 1; }\n          test -n "$(ls dist/vdi2770_validate-*.whl 2>/dev/null)" || {\n            echo "no alias wheel in dist/"; exit 1; }\n      # Before either publish, so it protects both. The first three cases\n      # install from the live index with no `--find-links`, which before this\n      # ran against an index already holding the new engine. It no longer does,\n      # and that is the right way round: if a new engine broke an old alias, the\n      # remedy is to publish the matched pair, not to withhold it and leave\n      # everyone in the mixed state. The window itself is measured by the case\n      # that simulates it.\n      - name: An install somebody already has must survive this release\n        run: python tools/check_upgrade_paths.py --from dist\n\n  # The only thing between the two uploads. It holds the workflow\'s floor --\n  # `contents: read`, nothing else -- and no environment. (It said "no token",\n  # which is not a thing a job can have: absent a `permissions:` block it takes\n  # whatever the repository\'s default is, and that is a setting, not a fact\n  # about this file.) Two reasons it is its own job rather than a step inside the\n  # publisher. A job that publishes should be download-and-upload and nothing\n  # else, so that re-running it after a failure is one click and repeats no\n  # decision -- which is the whole of the recovery path when the engine is on\n  # the index and the alias is not. And a `pip install` from PyPI, a `git`\n  # subprocess and a script from the tagged tree do not belong in the job that\n  # holds `id-token: write` for a distribution.\n  reader-is-on-the-index:\n    needs: publish-reader\n    runs-on: ubuntu-latest\n    steps:\n      # `fetch-depth: 0`: the gate asks the tag history whether this release is\n      # tagged, and a default checkout is `--depth 1 --no-tags`.\n      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n        with: { fetch-depth: 0 }\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5.6.0\n        with:\n          python-version: "3.12"\n      - name: Install\n        run: python -m pip install --upgrade pip packaging\n      # `needs: publish-reader` proves the upload step ran. It does not prove\n      # the index serves the file, and the alias is unresolvable until it does.\n      # PyPI\'s JSON view can trail the upload, so this is given a few tries --\n      # and refuses at the end rather than guessing, because an alias published\n      # against an engine that is not there cannot be fixed under this version\n      # number.\n      - name: The engine this floors on must be on the index\n        run: |\n          for attempt in 1 2 3 4 5; do\n            if python tools/check_release_order.py; then exit 0; fi\n            echo "the index does not serve it yet (attempt $attempt of 5); waiting"\n            sleep 20\n          done\n          echo "the engine this floors on never appeared on the index"\n          exit 1\n      # And "the JSON view lists it" is not "a machine can install it". This is\n      # the state the alias actually requires, so it is the one that is asked\n      # for before the alias goes out.\n      - name: And a machine can actually install it\n        run: |\n          version="${GITHUB_REF_NAME#v}"\n          for attempt in 1 2 3 4 5; do\n            if python -m pip download --no-deps --only-binary :all: \\\n                 --dest /tmp/probe "vdi2770==$version"; then exit 0; fi\n            echo "not installable yet (attempt $attempt of 5); waiting"\n            sleep 20\n          done\n          echo "vdi2770 $version is listed and cannot be installed"\n          exit 1\n\n  publish-rules:\n    needs: [reader-is-on-the-index, upgrade-gate]\n    runs-on: ubuntu-latest\n    # Not the reader\'s environment. The environment is half of what PyPI keys\n    # the publisher on, so sharing it would let either job publish as the other\n    # package.\n    environment: pypi-vdi2770-validate\n    permissions:\n      id-token: write\n    steps:\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-rules\n          path: dist/\n      # The bytes, not the name. An artifact is immutable and fetched by\n      # name, so this cannot fail without something having gone very wrong --\n      # which is the point: it is the line that turns "the gate tested these\n      # wheels" from an argument about the job graph into a checked fact, and\n      # it is what an independent verifier compares against afterwards.\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: sums-rules\n          path: sums/\n      - name: These are the bytes that were built and tested\n        run: |\n          cat sums/SHA256SUMS\n          # Counted first: `sha256sum -c` over an empty list exits 0 on at\n          # least one coreutils, and this is the last thing that runs before an\n          # upload that cannot be taken back.\n          n="$(wc -l < sums/SHA256SUMS)"\n          test "$n" -ge 2 || { echo "only $n files recorded"; exit 1; }\n          (cd dist && sha256sum -c ../sums/SHA256SUMS)\n          test "$(ls dist | wc -l)" -eq "$n" || {\n            echo "dist/ holds $(ls dist | wc -l) files and $n were recorded; "\n            echo "PyPI would receive something no build job made"\n            exit 1; }\n      # Pinned to a commit, not to `release/v1`. This is the one thing in this\n      # job that is not ours, and it runs while the job holds `id-token: write`\n      # for a real distribution: a moving ref means whatever that ref points at\n      # on the day can mint a publishing token. v1.14.2.\n      - uses: pypa/gh-action-pypi-publish@release/v1',
     ['tests/test_the_publishing_path_has_three_properties.py::'
      'test_every_action_is_pinned_to_a_commit'],
     'the one piece of code in that job which is not ours would run from a '
     'moving reference while the job holds a token that can publish as a real '
     'distribution'),

    ('release/the-gate-receives-both-distributions',
     '.github/workflows/release.yml',
     '      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-reader\n          path: dist/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-rules\n          path: dist/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: sums-reader',
     '      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: dist-rules\n          path: dist/\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0\n        with:\n          name: sums-reader',
     ['tests/test_the_publishing_path_has_three_properties.py::'
      'test_the_gate_receives_both_distributions_and_both_records'],
     'the exact defect: the job that installs and upgrades gets one of the two '
     'wheels it needs, every case that installs fails to resolve, and the gate '
     'between the two uploads is red on any tag while green on every machine'),

    ('release/a-publisher-does-not-check-out-the-tree',
     '.github/workflows/release.yml',
     '    environment: pypi-vdi2770-validate\n    permissions:\n      id-token: write\n    steps:\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0',
     '    environment: pypi-vdi2770-validate\n    permissions:\n      id-token: write\n    steps:\n      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0\n      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0',
     ['tests/test_the_publishing_path_has_three_properties.py::'
      'test_a_publisher_downloads_and_uploads_and_does_nothing_else'],
     'code from the tagged tree would run in the job that holds a publishing '
     'token, and re-running the publisher after a half-finished release would '
     'stop being the one thing that repeats no decision'),


    ('release/a-push-builds-what-a-tag-builds',
     '.github/workflows/ci.yml',
     '          python -m build packages/vdi2770 --outdir dist/\n          python -m build --outdir dist/\n          python tools/check_upgrade_paths.py --from dist',
     '          python -m build --wheel --outdir dist .\n          python -m build --wheel --outdir dist packages/vdi2770\n          python tools/check_upgrade_paths.py --from dist',
     ['tests/test_the_publishing_path_has_three_properties.py::'
      'test_the_wheels_a_push_builds_are_the_wheels_a_tag_builds'],
     'the rehearsal would build wheels only while the release builds an sdist '
     'too, so what every push checks and what a tag publishes stop being the '
     'same artifacts -- and the parity gate waves `python -m build` through as '
     'setup, so nothing else compares those lines'),

]

PAGES_ROWS = [
    ('pages/the-install-with-no-command-says-how-to-run-it',
     'README.md',
     'python -m vdi2770.validate check YOUR-CONTAINER.zip',
     'vdi2770-validate check YOUR-CONTAINER.zip',
     ['tests/test_the_two_pages_say_one_thing.py::'
      'test_a_page_that_names_the_extra_says_how_to_run_it'],
     'the page tells the reader to install the extra and then gives them a '
     'command that install does not carry -- measured on a clean environment, '
     'the scripts directory holds the parser\'s three and nothing of ours'),

    ('pages/the-old-name-page-says-how-to-run-the-extra',
     'README-vdi2770-validate.md',
     'run that one as `python -m vdi2770.validate check YOUR-CONTAINER.zip`',
     'run that one from the command line',
     ['tests/test_the_two_pages_say_one_thing.py::'
      'test_a_page_that_names_the_extra_says_how_to_run_it'],
     'one page tells the reader how to start the tool and the other does not, '
     'about one install'),

    ('pages/the-half-taken-upgrade-caveat-is-on-the-old-name-page',
     'README-vdi2770-validate.md',
     'An installation that takes half the upgrade still has old rules in it.',
     'An installation that takes half the upgrade is fine.',
     ['tests/test_the_two_pages_say_one_thing.py::'
      'test_neither_page_says_the_trap_is_gone'],
     'the sentence this gate exists to protect could be deleted with the suite '
     'green, because the gate was looking for a word that appears elsewhere on '
     'the page'),


    ('gates/the-harness-sees-the-command-windows-installed',
     'tools/check_upgrade_paths.py',
     '    for suffix in ("", ".exe", ".bat", ".cmd"):',
     '    for suffix in ("",):',
     ['tests/test_the_harness_finds_what_pip_installed.py::'
      'test_the_windows_executable_is_the_command'],
     'the harness answers "not installed at all" about a Windows installation '
     'that has the command, and it has an assertion that an install carries no '
     'command -- absence that is right for the wrong reason'),

    ('gates/a-near-name-is-not-the-command',
     'tools/check_upgrade_paths.py',
     '    for suffix in ("", ".exe", ".bat", ".cmd"):',
     '    for suffix in ("", ".exe", ".bat", ".cmd", "-script.py"):',
     ['tests/test_the_harness_finds_what_pip_installed.py::'
      'test_a_name_that_merely_starts_the_same_is_not_the_command'],
     'setuptools writes `<name>-script.py` beside the executable, and counting '
     'it as the command makes an install look like it has one'),


    ('gates/every-door-on-a-working-install-is-one-of-the-cases',
     'tools/check_upgrade_paths.py',
     '         case_13_every_door_on_a_working_install]',
     '         case_12_the_window]',
     ['tests/test_ci_parity.py::test_every_case_the_harness_runs_asks_that_question'],
     'the only case that asks whether the file pip wrote starts -- and the only '
     'one CI runs on Windows -- would be outside the harness while the workflow '
     'still named its number'),

    ('gates/a-selection-that-runs-nothing-is-not-a-pass',
     'tools/check_upgrade_paths.py',
     '    if not chosen:',
     '    if False:',
     ['tests/test_ci_parity.py::test_a_selection_that_runs_nothing_is_not_a_pass'],
     'a platform step whose build produced nothing would print "0 upgrade '
     'path(s) end in a tool that runs" and exit 0 -- the same shape as the '
     'test-id gate this project shipped that collected nothing and passed'),

    ('gates/a-case-is-numbered-by-what-was-asked-for',
     'tools/check_upgrade_paths.py',
     '    for n, case in zip(numbers, chosen):',
     '    for n, case in enumerate(chosen, start=1):',
     ['tests/test_ci_parity.py::test_the_harness_numbers_a_selected_case_by_its_own_number'],
     'a run of cases 11 and 13 would report them as 1 and 2, so a failing '
     'platform step names a case nobody can select'),


    ('release/ci-must-have-judged-this-commit',
     '.github/workflows/release.yml',
     '        run: python tools/check_ci_judged_this_commit.py --commit "$GITHUB_SHA"',
     '        run: true',
     ['tests/test_a_release_asks_whether_ci_judged_this_commit.py::'
      'test_the_gate_is_wired_into_the_release_before_anything_is_published'],
     'the gate would exist as a file and never run, which is the shape this '
     'repository keeps finding -- and by the time the reader is published there '
     'is nothing left to refuse'),

    ('release/a-cancelled-run-is-not-a-pass',
     'tools/check_ci_judged_this_commit.py',
     '    if any(r.get("status") == "completed" and r.get("conclusion") == "success"',
     '    if any(r.get("status") == "completed"',
     ['tests/test_a_release_asks_whether_ci_judged_this_commit.py::'
      'test_a_cancelled_run_is_not_a_judgement'],
     'a cancelled run is a commit nobody judged and it renders grey rather than '
     'red, so it is the one that gets past a person and has to be stopped by a '
     'machine'),

    ('release/an-answer-about-another-commit-is-not-an-answer',
     'tools/check_ci_judged_this_commit.py',
     '    mine = [r for r in runs if (r.get("headSha") or "") == commit]',
     '    mine = list(runs)',
     ['tests/test_a_release_asks_whether_ci_judged_this_commit.py::'
      'test_a_run_on_another_commit_does_not_count'],
     'the `--commit` filter is applied by a server, and a filter quietly '
     "ignored lets yesterday's green authorise today's publish"),

    ('release/no-answer-is-not-a-pass',
     'tools/check_ci_judged_this_commit.py',
     '    if runs is None:',
     '    if False:',
     ['tests/test_a_release_asks_whether_ci_judged_this_commit.py::'
      'test_gh_failing_is_a_refusal_not_a_pass'],
     'a missing `gh`, a token without `actions: read` or a rate limit would '
     'each turn into a pass, which makes every outage an authorisation'),


    ('release/an-abbreviated-commit-is-named-as-the-reason',
     'tools/check_ci_judged_this_commit.py',
     '        if not others and len(commit) != 40:',
     '        if False:',
     ['tests/test_a_release_asks_whether_ci_judged_this_commit.py::'
      'test_an_abbreviated_commit_is_named_as_the_reason'],
     'the short SHA a person copies out of `git log` returns nothing from '
     'GitHub, and this gate then reports that a judged commit was not judged -- '
     'to the person trying to find out why a release stopped'),

]

ABSENT_STDLIB_ROWS = [
    ('gates/a-module-this-platform-lacks-is-still-the-standard-library',
     'tests/test_the_suite_declares_what_it_imports.py',
     '    return name in (_SAYS_STDLIB if known is None else known) or name in _PLATFORM_STDLIB',
     '    return name in (_SAYS_STDLIB if known is None else known)',
     ['tests/test_the_suite_declares_what_it_imports.py::test_a_module_this_platform_lacks_can_still_be_the_standard_library'],
     'fcntl is the standard library and is not on Windows; reporting it '
     'as undeclared asks for a manifest entry that cannot exist, and the '
     'interpreter that could be asked for the full list is 3.10 and later'),

]

TABLE += ABSENT_STDLIB_ROWS

TABLE += PLATFORM_ROWS

TABLE += BOOT_ROWS

TABLE += AGREEMENT_ROWS

TABLE += MANIFEST_ROWS

TABLE += WINDOWS_ROWS

TABLE += UPGRADE_BODY_ROWS

TABLE += LOCATION_ROWS

TABLE += GUARDED_ROWS

TABLE += WORKFLOW_ROWS

TABLE += DECLARED_ROWS

TABLE += UPGRADE_ROWS

TABLE += STREAM_ROWS

TABLE += PAGES_ROWS

TABLE += PUBLISHING_PATH_ROWS

TABLE += BASIS_ROWS

TABLE += RELATIONSHIPS

TABLE += FRONT_DOOR

CANARY = "canary/a-comment-nobody-reads"


def clear(tree: Path) -> None:
    for cache in tree.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def run(tree: Path, checks: list) -> tuple:
    """Whatever the row names: a pytest selection, or a gate that is a tool.

    Several gates in this project are not tests — the coverage baseline, the
    oracle sweep, the API fingerprint, the wheel. A table that could only run
    pytest reported "nothing caught" for those and was wrong about it.

    Returns the worst exit code and what pytest printed — `None` when the row
    names no pytest selection at all, which is different from one that printed
    nothing. The exit code alone cannot tell a test that ran from a test that
    declined to; see `_ran`.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    tools = [c for c in checks if c.startswith("tools/")]
    tests = [c for c in checks if not c.startswith("tools/")]
    worst, said = 0, None
    for spec in tools:
        code = subprocess.run([sys.executable, *spec.split()],
                              cwd=tree, capture_output=True, text=True, env=env).returncode
        worst = worst or code
    if tests:
        # No `-q` here. The project's `addopts` already carries one, and pytest
        # counts verbosity: two of them silence the `N passed` line entirely,
        # which is the line `_ran` reads. The output is captured either way, so
        # the second `-q` bought nothing and cost the harness its eyesight.
        done = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
                               *tests], cwd=tree, capture_output=True, text=True,
                              env=env)
        worst = worst or done.returncode
        said = done.stdout + done.stderr
    return worst, said


def _ran(said: str) -> bool:
    """Whether pytest actually asserted anything.

    This sweep runs in a copy of the tree with `.git` left out, and a test that
    reads the tag history skips there. `pytest` exits 0 on a run that skipped
    everything, so the mutation was applied, nothing objected, and the row was
    reported as *survived* -- a real finding, but pointing at the workflow
    rather than at the row, and the fix would have been to weaken the gate.
    Exit code 5 already covers "collected nothing"; this covers "collected it
    and declined to run it", which looks exactly like a pass from outside.
    """
    return re.search(r"\b\d+ passed", said) is not None


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
            code, said = run(tree, tests)
            if code != 0:
                broken.append(f"{_id}: the tests it names already fail before the mutation")
                continue
            # `said is None` means the row names only tools, which report by exit
            # code and have no summary line to read. `tests` here is the whole
            # check list, tools included, so testing *it* flagged every
            # tools-only row -- the guard read "this row named something" as
            # "pytest ran".
            if said is not None and not _ran(said):
                broken.append(f"{_id}: the tests it names pass nothing here -- they "
                              f"skipped, so the row cannot kill anything")
                continue

            apply(tree, row)
            code, _ = run(tree, tests)
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
