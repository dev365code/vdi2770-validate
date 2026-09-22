"""`Z13` says documents arrived as folders and this tool does not open them.
A sender's next question is *which* folders, and the answer has to be in the
field a consumer reads.

It was in the sentence instead. One finding carried every folder, with the names
listed in `detail` and cut at five, and `where.member` empty -- so a person
could read the location and a pipeline could not, which is backwards for the one
field that exists to be read by a machine.

One finding per folder now. The listing cap in `Report.add` is what makes that
safe: a delivery with a thousand unopened folders lists the first few and counts
the rest into `notListed`, the same way any rule that fires per element does.
"""
import json
import os
import subprocess
import sys

from conftest import CORPUS, ROOT

#: Two folders hold a metadata file, so this draws `Z13` twice.
FOLDERS = CORPUS / "missingdocuments" / "folders.zip"


def report_for(path):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run(
        [sys.executable, "-m", "vdi2770.validate", "check", str(path), "--json"],
        cwd=ROOT, capture_output=True, text=True, env=env)
    assert done.returncode in (0, 1), (done.returncode, done.stderr[-400:])
    return json.loads(done.stdout)


def z13_findings():
    assert FOLDERS.exists(), f"{FOLDERS} is not here; this gate would prove nothing"
    return [f for d in report_for(FOLDERS) for f in d.get("findings", [])
            if f["rule"] == "Z13"]


def test_no_two_findings_claim_the_same_folder():
    """One folder, one finding -- whatever it holds.

    `folders_holding_metadata` returns `(prefix, leaf)` pairs, and a folder may
    hold more than one reserved name. Iterating the pairs emitted two findings
    at one location, same `member` and same `subject`, differing only in a
    sentence -- which hands the consumer back exactly the deduplication this
    rule stopped making them do.

    Asked as a property rather than a count, deliberately. An earlier version of
    this file recomputed "which folders hold a metadata file" from the archive's
    listing, using a definition that is not the rule's: it disagreed on a folder
    holding both reserved names, on names that normalise together, on a member
    the reader refuses, and on a `./` prefix -- which is not a folder, a defect
    this project has fixed twice and which that arithmetic put back.
    """
    members = [f["where"]["member"] for f in z13_findings()]
    assert members, "Z13 did not fire; this gate would pass vacuously"
    twice = sorted({m for m in members if members.count(m) > 1})
    assert not twice, f"these folders draw more than one finding each: {twice}"


def test_every_unopened_folder_is_named_in_the_location():
    """`where.member`, not just the sentence. A consumer filtering its report by
    location gets nothing from prose."""
    placed = [(f["where"].get("member"), f.get("detail")) for f in z13_findings()]
    assert placed, "Z13 did not fire; this gate would pass vacuously"
    missing = [d for m, d in placed if not m]
    assert not missing, (
        f"{len(missing)} of {len(placed)} Z13 findings name no member, so the "
        f"folder is only in the sentence: {missing}")


def test_the_folder_named_is_one_the_archive_holds():
    """A location a sender cannot find in their own listing is worse than none:
    they go looking, fail, and stop trusting the field.

    Compared against the archive's directory levels as the reader normalises
    them, which is what the rule promises and what `Z9` prints beside it. A raw
    `startswith` against the listing is not that: it accepts a truncation --
    `AB` passes for `AB393/` -- and it fails on an archive that spells its own
    members with `./`, where the normalised folder is a real place under a name
    the listing does not literally contain.
    """
    import zipfile

    findings = z13_findings()
    assert findings, "Z13 did not fire; this gate would pass vacuously"
    with zipfile.ZipFile(FOLDERS) as z:
        names = z.namelist()
    levels = {n.rsplit("/", 1)[0].lstrip("./") + "/" for n in names if "/" in n}
    for f in findings:
        member = f["where"]["member"]
        assert member in levels, (
            f"Z13 names {member!r}; the archive's directory levels are "
            f"{sorted(levels)}")
