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


def test_each_unopened_folder_draws_its_own_finding():
    """Counted from the archive rather than written here: whatever holds a
    metadata file is what should be reported, so the number cannot drift."""
    import zipfile
    with zipfile.ZipFile(FOLDERS) as z:
        names = z.namelist()
    holders = {n.rsplit("/", 1)[0] for n in names
               if n.count("/") >= 1 and n.rsplit("/", 1)[1] in
               ("VDI2770_Metadata.xml", "VDI2770_Main.xml")}
    assert holders, "no folder in this fixture holds a metadata file"
    assert len(z13_findings()) == len(holders), (
        f"{len(holders)} folders hold a metadata file and Z13 reported "
        f"{len(z13_findings())} findings")


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
    they go looking, fail, and stop trusting the field."""
    import zipfile
    with zipfile.ZipFile(FOLDERS) as z:
        names = set(z.namelist())
    for f in z13_findings():
        member = f["where"]["member"]
        assert any(n.startswith(member) for n in names), (
            f"Z13 names {member!r}, which is not a prefix of anything in the "
            f"archive's own listing")
