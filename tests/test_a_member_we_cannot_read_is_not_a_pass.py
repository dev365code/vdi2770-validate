"""Silence is the worst answer a validator can give.

Three containers, passed by this tool with exit 0 and
"no findings" while `unzip -t` refused them, and three legitimate deliveries it
failed. Both directions are recorded here.
"""
import io
import os
import pathlib
import struct
import subprocess
import unicodedata
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_bytes, check_file

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = SRC.read("VDI2770_Metadata.xml").decode()
PDF = SRC.read("B.pdf")
DOCX = SRC.read("B.docx")
DOCX_DECL = ('<DigitalFile FileFormat="application/vnd.openxmlformats-officedocument'
             '.wordprocessingml.document">B.docx</DigitalFile>')


def build(tmp_path, name, entries, level=None):
    p = tmp_path / name
    kw = {"compresslevel": level} if level else {}
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED, **kw) as z:
        for n, d in entries:
            z.writestr(n, d)
    return str(p)


def ids(path):
    return {f.rule.id for f in check_file(path).findings}


# -- silent passes -----------------------------------------------------------

def test_a_member_with_a_broken_crc_is_reported(tmp_path):
    """`unzip -t` says "bad CRC"; this tool used to say "no findings", exit 0.
    A truncated transfer is the commonest defect a handover archive has."""
    p = build(tmp_path, "crc.zip",
              [("VDI2770_Metadata.xml", META), ("B.docx", DOCX), ("B.pdf", PDF)])
    raw = bytearray(pathlib.Path(p).read_bytes())
    i = zipfile.ZipFile(p).getinfo("B.pdf")
    o = i.header_offset + 30 + len(i.filename) + 1000
    for k in range(o, o + 40):
        raw[k] ^= 0xFF
    pathlib.Path(p).write_bytes(bytes(raw))
    assert ids(p) & {"Z12"}, f"nothing reported the corrupt member: {ids(p)}"


def test_a_password_protected_member_is_reported(tmp_path):
    """A member the recipient cannot open without a password has not been
    handed over -- which is P2's own reasoning, one layer out."""
    if subprocess.run(["which", "zip"], capture_output=True).returncode:
        pytest.skip("needs the zip(1) command to build an encrypted member")
    src = tmp_path / "src"
    src.mkdir()
    (src / "VDI2770_Metadata.xml").write_text(META)
    (src / "B.pdf").write_bytes(PDF)
    (src / "B.docx").write_bytes(DOCX)
    p = str(tmp_path / "enc.zip")
    subprocess.run(["zip", "-jq", p, str(src / "VDI2770_Metadata.xml"),
                    str(src / "B.docx")], check=True)
    subprocess.run(["zip", "-jq", "-P", "secret", p, str(src / "B.pdf")], check=True)
    assert ids(p) & {"Z12"}, f"nothing reported the encrypted member: {ids(p)}"


# -- false alarms on legitimate deliveries -----------------------------------

def test_a_hundred_kilobyte_archive_does_not_exceed_our_limits(tmp_path):
    """An uncompressed TIFF scan of a line drawing expands ~220x and is 1MB.
    The ratio heuristic exists so a bomb cannot exhaust the machine; 1MB
    exhausts nothing, and "split the delivery" is not a remedy anyone can act on."""
    rows = []
    for y in range(3508):
        if y in (200, 201, 3300, 3301):
            rows.append(b"\x00" * 310)
            continue
        r = bytearray(b"\xff" * 310)
        r[25] = 0x0F
        r[280] = 0x00
        if 400 < y < 3000 and (y // 60) % 3 == 0:
            for x in range(40, 260):
                r[x] = 0x55
        rows.append(bytes(r))
    tif = b"II*\x00" + struct.pack("<I", 8) + b"\x00\x00" + b"".join(rows)
    m = META.replace(DOCX_DECL, '<DigitalFile FileFormat="image/tiff">Zeichnung.tif</DigitalFile>')
    p = build(tmp_path, "tiff.zip",
              [("VDI2770_Metadata.xml", m), ("B.pdf", PDF), ("Zeichnung.tif", tif)], level=9)
    assert os.path.getsize(p) < 200_000, "the premise is that the archive is small"
    assert not ids(p) & {"Z5", "F1"}, f"refused a 100KB archive: {ids(p)}"


def test_a_colon_in_a_file_name_is_not_a_drive_letter(tmp_path):
    """`5:1.pdf` is a gear ratio. The check looked only at the second character."""
    m = META.replace(DOCX_DECL, '<DigitalFile FileFormat="application/pdf">5:1.pdf</DigitalFile>')
    p = build(tmp_path, "colon.zip",
              [("VDI2770_Metadata.xml", m), ("B.pdf", PDF), ("5:1.pdf", PDF)])
    assert not ids(p) & {"Z4", "F1"}, f"called a benign name a path escape: {ids(p)}"


def test_a_real_drive_letter_is_still_refused(tmp_path):
    p = build(tmp_path, "drive.zip",
              [("VDI2770_Metadata.xml", META), ("C:/windows/evil.txt", b"x")])
    assert "Z4" in ids(p)


def test_the_same_name_in_two_unicode_normalisations_is_the_same_name(tmp_path):
    """macOS stores NFD and its Finder writes NFD into the ZIP; metadata authored
    anywhere else is NFC. Both denote one file, and the report printed the same
    visible string twice, once as missing and once as undeclared."""
    nfc = "Gr\u00f6\u00dfe.pdf"
    m = META.replace(DOCX_DECL, f'<DigitalFile FileFormat="application/pdf">{nfc}</DigitalFile>')
    p = build(tmp_path, "nfd.zip",
              [("VDI2770_Metadata.xml", m), ("B.pdf", PDF),
               (unicodedata.normalize("NFD", nfc), PDF)])
    assert not ids(p) & {"F1", "F2"}, f"NFD and NFC treated as different files: {ids(p)}"


def test_a_genuinely_missing_file_is_still_missing(tmp_path):
    m = META.replace(DOCX_DECL, '<DigitalFile FileFormat="application/pdf">nope.pdf</DigitalFile>')
    p = build(tmp_path, "missing.zip", [("VDI2770_Metadata.xml", m), ("B.pdf", PDF)])
    assert "F1" in ids(p)


def test_a_declared_name_the_archive_stores_twice_is_told_to_remove_the_repeat():
    """`F1` said the bytes could not be read. They read fine.

    The archive stores `B.pdf` twice; the reader refuses both entries because the
    name identifies neither. `F1` then took the "bad CRC" branch and told the
    producer to *re-create the archive and send it again* -- which, done exactly
    as instructed, produces the same archive and the same finding.

    `files.py` already had the right words. They were behind
    `f.file_name in members.ambiguous`, and that set is always empty from real
    reader output for precisely the reason this test exists: the reader dropped
    both entries, so the name the metadata declares is not in `file_names` at
    all. The live signal is the refusal, so the branch reads that.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in src.namelist():
            z.writestr(name, src.read(name))
        z.writestr("B.pdf", b"%PDF-1.4 other bytes")

    f1 = [f for f in check_bytes(buf.getvalue(), "dup.zip").findings
          if f.rule.id == "F1"]
    assert len(f1) == 1, [f.rule.id for f in check_bytes(buf.getvalue(), "d.zip").findings]
    assert "more than once" in f1[0].message, f1[0].message
    assert "Remove the repeat" in (f1[0].fix or ""), f1[0].fix
    assert "not readable" not in (f1[0].fix or ""), f1[0].fix
