"""The licensing claims are pinned, because they are the ones that matter if wrong.

This project bundles someone else's schema, a table extracted from someone
else's publication, and a corpus from an MIT project. Getting the notices wrong
is not a style problem.
"""
import hashlib
import json
import re

from conftest import ROOT

THIRD_PARTY = (ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8")
NOTICE = (ROOT / "NOTICE").read_text(encoding="utf-8")
DATA = ROOT / "src" / "vdi2770_validate" / "data"


def license_files():
    """Read the packaged licence list without a TOML parser — the tool supports
    Python 3.9, where tomllib does not exist, and plant systems run 3.9."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^license-files\s*=\s*\[(.*?)\]", text, re.M | re.S)
    assert m, "pyproject.toml declares no license-files"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_the_notices_travel_with_the_wheel():
    """Apache-2.0 requires the NOTICE to be distributed; the bundled schema and
    table make THIRD_PARTY.md carry the MIT and CC BY texts."""
    files = license_files()
    for wanted in ("LICENSE", "NOTICE", "THIRD_PARTY.md"):
        assert wanted in files, f"{wanted} would not be packaged"
        assert (ROOT / wanted).exists()


def test_mit_permission_notice_is_reproduced_in_full():
    """MIT: 'the above copyright notice AND THIS PERMISSION NOTICE shall be
    included'. A copyright line on its own does not satisfy it."""
    for where in (THIRD_PARTY, (ROOT / "corpus" / "NOTICE").read_text(encoding="utf-8")):
        assert "Permission is hereby granted, free of charge" in where
        assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in where
        assert "Copyright (C) 2021 Johannes Schmidt" in where


def test_cc_by_attribution_states_the_modification():
    """CC BY 4.0 requires the licence, the creator, a link, and an indication
    that the material was changed. We reformatted a table, so we say so."""
    assert "CC BY 4.0" in THIRD_PARTY
    assert "creativecommons.org/licenses/by/4.0" in THIRD_PARTY
    assert "Industrial Digital Twin Association" in THIRD_PARTY
    assert re.search(r"extracted and reformatted", THIRD_PARTY)


def test_every_bundled_data_file_is_accounted_for():
    for f in sorted(DATA.iterdir()):
        if f.name.endswith(".py"):
            continue
        assert f.name in THIRD_PARTY, f"{f.name} is shipped but not listed in THIRD_PARTY.md"


def test_the_vendored_schema_is_the_bytes_vdi_published():
    """We claim byte-for-byte verbatim and print a hash to prove it. If the file
    is ever touched, this fails before anyone can repeat the claim."""
    xsd = DATA / "VDI2770_Schema_2019-08-23.xsd"
    digest = hashlib.sha256(xsd.read_bytes()).hexdigest()
    assert digest in THIRD_PARTY, "the hash in THIRD_PARTY.md no longer matches the shipped file"
    assert digest == "f7a704fe4bba095eaa4e95be0b9853205412301ad09c4bcffb4c5f0f666cb805"


def test_the_paid_guideline_is_not_claimed_as_a_source():
    """Every rule must trace to something free. `ours` is allowed, but it has to
    explain itself; nothing may cite the guideline text."""
    rules = json.loads((DATA / "rules.json").read_text(encoding="utf-8"))["rules"]
    for r in rules:
        basis = (r.get("basis") or "").lower()
        assert "blatt" not in basis, f"{r['id']} cites the paywalled guideline as its basis"
    assert "was not consulted" in THIRD_PARTY or "not read" in THIRD_PARTY


def test_unofficial_is_stated_where_a_reader_will_see_it():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Unofficial" in readme or "unofficial" in readme
    assert "not affiliated" in readme.lower()
    assert "not affiliated" in THIRD_PARTY.lower()


def test_the_oracle_evidence_records_identifiers_and_not_their_prose():
    """`docs/oracle-sweep.json` is produced by running someone else's MIT-licensed
    software over our containers. Codes are identifiers; their message strings are
    their prose, and this project vendors exactly one bounded list of those with
    the licence attached. A change to the capture that started recording `text`
    would quietly widen what we redistribute, so the shape is asserted rather
    than trusted."""
    import json
    import re

    path = ROOT / "docs" / "oracle-sweep.json"
    assert path.name in THIRD_PARTY, "the evidence file is not listed in THIRD_PARTY.md"

    strings = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            strings.append(node)

    walk(json.loads(path.read_text(encoding="utf-8"))["containers"])
    assert strings, "the evidence file recorded nothing"
    allowed = re.compile(r"^(?:[A-Z]{1,4}_\d{3}|[A-Z]\d{1,2}|«uncoded»)$")
    strays = sorted({s for s in strings if not allowed.match(s)})
    assert not strays, f"not identifiers: {strays[:5]}"


def test_the_oracle_harness_is_accounted_for():
    assert "Sweep.java" in THIRD_PARTY
    harness = (ROOT / "tools" / "oracle" / "Sweep.java").read_text(encoding="utf-8")
    assert "de.vdi.vdi2770" in harness, "the harness no longer imports theirs; update the note"
    assert "Copyright (C) 2021" not in harness, "their source must not be pasted into ours"


def test_no_foreign_log_or_build_output_is_tracked():
    """Running the differential oracle drops the reference implementation's log4j
    output into the working directory, and `git add -A` committed one: 59 KB of
    somebody else's log, with absolute paths from the machine that ran it, in a
    repository that accounts for every other byte it carries from them.

    It never reached a published artifact — MANIFEST.in lists what ships — but it
    was in the repository, and this is cheaper than remembering."""
    import subprocess

    # Inside an sdist there is no repository, and the question is the same one:
    # does this distribution carry a stray. Asking git when git is there keeps
    # ignored files out of the answer; walking the tree covers the sdist, where
    # only shipped files exist anyway. (A `git ls-files` with no fallback is what
    # broke the sdist gate the first time this test was written.)
    found = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if found.returncode == 0:
        names = found.stdout.split()
    else:
        skip = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist"}
        names = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
                 if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]
    assert names, "nothing to inspect"

    strays = [f for f in names
              if f.endswith((".log", ".jar", ".class", ".orig", ".rej"))
              or f.split("/")[0] == "target"]
    assert not strays, f"build or log output is carried: {strays}"
