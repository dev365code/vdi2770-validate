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
