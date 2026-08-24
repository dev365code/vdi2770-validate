"""`zipfile.ZipFile()` raises more than `BadZipFile`, and the two it also raises
come from one mislabelled field each.

`_RealGetContents` raises `UnicodeDecodeError` when a member name is flagged
UTF-8 and is not — routine mislabelling by older Windows and Info-ZIP writers —
and `NotImplementedError` for a "version needed to extract" it does not know.
Neither was caught. A hand-written 119-byte file produced a stack trace naming
CPython internals, exited 1 as though findings had been reported, and took the
rest of the run with it: `cli.py`'s own comment says one bad path must not stop
a CI job sweeping a supplier drop folder, and it did.
"""
import io
import subprocess
import sys
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT, ROOT
from vdi2770_validate.runner import check_file


def one_member_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", b"x")
    return bytearray(buf.getvalue())


def mislabelled_utf8():
    raw = one_member_zip()
    central = raw.rindex(b"PK\x01\x02")
    raw[central + 9] |= 0x08                       # general-purpose bit 11
    raw[raw.index(b"a.txt", central)] = 0xE9       # not valid UTF-8
    local = raw.index(b"PK\x03\x04")
    raw[raw.index(b"a.txt", local)] = 0xE9
    return bytes(raw)


def unknown_version():
    raw = one_member_zip()
    raw[raw.rindex(b"PK\x01\x02") + 6] = 64
    return bytes(raw)


@pytest.mark.parametrize("name,make", [("mislabelled utf-8", mislabelled_utf8),
                                       ("unknown version", unknown_version)])
def test_it_is_reported_as_an_unreadable_archive(tmp_path, name, make):
    p = tmp_path / "bad.zip"
    p.write_bytes(make())
    with pytest.raises(zipfile.BadZipFile if False else Exception):
        zipfile.ZipFile(io.BytesIO(p.read_bytes()))   # the premise: CPython refuses it
    assert {f.rule.id for f in check_file(str(p)).findings} == {"Z1"}, name


def test_one_unreadable_archive_does_not_end_the_sweep(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(mislabelled_utf8())
    good = tmp_path / "good.zip"
    good.write_bytes(CLEAN_DOCUMENT.read_bytes())

    done = subprocess.run(
        [sys.executable, "-m", "vdi2770_validate", "check", str(bad), str(good)],
        capture_output=True, text=True,
        env={"PYTHONPATH": ":".join([str(ROOT / "src"),
                                     str(ROOT / "packages" / "vdi2770" / "src")]),
             "PATH": "/usr/bin:/bin"})
    assert "Traceback" not in done.stderr, done.stderr[-400:]
    assert "Z1" in done.stdout and "P4" in done.stdout, done.stdout
    assert done.returncode == 1


def test_an_inner_member_that_cannot_be_opened_is_reported_too(tmp_path):
    """Same failure one level down: a valid documentation container with one bad
    supplier archive inside used to lose the whole run."""
    from conftest import CLEAN_DOCUMENTATION

    docn = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Main.xml", docn.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", docn.read("VDI2770_Main.pdf"))
        z.writestr("documentcontainer.zip", CLEAN_DOCUMENT.read_bytes())
        z.writestr("supplier.zip", mislabelled_utf8())
    p = tmp_path / "nested.zip"
    p.write_bytes(buf.getvalue())

    ids = {f.rule.id for f in check_file(str(p)).findings}
    assert "Z1" in ids, ids
    assert "P4" in ids, f"the good half of the container stopped being checked: {ids}"
