"""A bug report is written for a person to attach, and carries nothing from the
files it was about.

`check --bug-report` writes a diagnostic bundle beside the run: the shape of the
input -- sizes, methods, flags, hashes -- and what the run said, by rule code
and count. Nothing is sent; the bundle is a file here. What is held below is
the promise that makes it safe to attach: every place a sender can write
something -- a member's name, a folder, a value in the metadata, an XML
comment, the archive's comment, an extra field, a PDF's text, the directory the
file sat in -- carries a marker, and the marker is in the bundle in no form a
reader could decode it from. And the bundle changes nothing about the verdict.
"""
import base64
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest

import vdi2770.validate.cli as cli
from conftest import CORPUS, FIXTURES, ROOT

#: Written wherever a sender can write. Long and odd enough that a match is a leak.
CANARY = "Qz7Canary4Vx9Kp"


def _forms(text):
    """Every way the canary could sit in the bundle's bytes and still be read."""
    raw = text.encode("utf-8")
    forms = {raw, raw.lower(), raw.upper(), text.encode("utf-16-le"), text.encode("utf-16-be"),
             raw.hex().encode(), raw.hex().upper().encode()}
    for pad in (b"", b"x", b"xx"):
        coded = base64.b64encode(pad + raw)
        forms.add(coded[4:-4])              # the part that does not depend on what surrounds it
    return forms


def _container(tmp_path):
    """A document container with the canary in every place a sender writes."""
    metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- {CANARY} in a comment -->
<Document xmlns="http://www.vdi2770.com/DocumentMetadata">
  <DocumentId DomainId="{CANARY}-domain" IsPrimary="true">{CANARY}-id</DocumentId>
  <DocumentClassification ClassificationSystem="VDI2770:2018">
    <ClassId>{CANARY}</ClassId>
  </DocumentClassification>
  <Language>{CANARY}</Language>
  <DocumentVersion>
    <DocumentVersionId>{CANARY}-version</DocumentVersionId>
    <Language>{CANARY}</Language>
    <Title Language="en">{CANARY} title</Title>
  </DocumentVersion>
</Document>
""".encode()
    pdf = f"%PDF-1.7\n1 0 obj\n<< /Title ({CANARY}) >>\nendobj\n({CANARY} body)\n%%EOF\n".encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.comment = f"{CANARY} archive comment".encode()
        zf.writestr("VDI2770_Metadata.xml", metadata)
        info = zipfile.ZipInfo(f"{CANARY}/{CANARY}-file.pdf")
        info.extra = b"\xfe\xca" + len(CANARY.encode()).to_bytes(2, "little") + CANARY.encode()
        zf.writestr(info, pdf)
    where = tmp_path / f"drop-{CANARY}"
    where.mkdir()
    path = where / f"{CANARY}.zip"
    path.write_bytes(buf.getvalue())
    return path


def _bundle(tmp_path, capsys, *args):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    code = cli.main(["check", *args, "--bug-report", "--bundle-out", str(out)])
    captured = capsys.readouterr()
    written = sorted(out.iterdir())
    return code, captured, written


def test_nothing_a_sender_wrote_is_in_the_bundle(tmp_path, capsys):
    code, captured, written = _bundle(tmp_path, capsys, str(_container(tmp_path)),
                                      "--note", "the verdict looks wrong to me")
    assert len(written) == 1, written
    data = written[0].read_bytes()
    leaks = [form for form in _forms(CANARY) if form in data]
    assert not leaks, f"the bundle carries the canary as {leaks[:3]}"
    assert CANARY not in written[0].name
    # And what it does carry is there: the shape, the rule codes, the note.
    bundle = json.loads(data)
    assert bundle["input"]["members"]["count"] == 2
    assert bundle["run"]["findings"], "the bundle says nothing about the run"
    assert bundle["user"] == {"note": "the verdict looks wrong to me"}
    assert "<input-1>" in bundle["invocation"]["argv"]
    assert captured.err.rstrip().endswith("Nothing was sent.")


def test_the_same_run_gives_the_same_bytes(tmp_path, capsys):
    path = str(FIXTURES / "m2-unknown-class-id.zip")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = _bundle(tmp_path / "a", capsys, path)[2][0]
    second = _bundle(tmp_path / "b", capsys, path)[2][0]
    assert first.read_bytes() == second.read_bytes()
    assert first.name == second.name


def test_a_failure_of_this_tool_writes_a_bundle_and_keeps_its_exit_code(tmp_path, capsys, monkeypatch):
    path = str(FIXTURES / "m2-unknown-class-id.zip")

    def breaks(_path):
        raise KeyError(f"{CANARY} in the message")
    monkeypatch.setattr(cli, "check_file", breaks)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["check", path, "--no-bundle"]) == 2
    assert not list(tmp_path.glob("bug-report-*.json")), "--no-bundle wrote a bundle"
    assert cli.main(["check", path, "--show-bundle"]) == 2
    assert not list(tmp_path.glob("bug-report-*.json")), "--show-bundle wrote a bundle"
    capsys.readouterr()
    assert cli.main(["check", path]) == 2, "writing the bundle changed the exit code"
    written = list(tmp_path.glob("bug-report-*.json"))
    assert len(written) == 1
    data = written[0].read_bytes()
    assert not [form for form in _forms(CANARY) if form in data]
    bundle = json.loads(data)
    assert bundle["bundle"]["trigger"] == "crash"
    assert bundle["error"]["type"] == "KeyError"
    assert "defect in this tool" in capsys.readouterr().err


def test_a_large_archive_is_listed_up_to_the_limit(tmp_path, capsys):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for i in range(5001):
            zf.writestr(f"m{i}.txt", b"")
    path = tmp_path / "many.zip"
    path.write_bytes(buf.getvalue())
    _code, _captured, written = _bundle(tmp_path, capsys, str(path))
    bundle = json.loads(written[0].read_bytes())
    assert bundle["input"]["members"]["count"] == 5001
    assert bundle["input"]["members"]["listed"] <= 5000
    assert len(bundle["input"]["members"]["rows"]) == bundle["input"]["members"]["listed"]
    assert written[0].stat().st_size <= 256 * 1024


@pytest.mark.parametrize("path", sorted(CORPUS.rglob("*.zip")) + sorted(FIXTURES.glob("*.zip")),
                         ids=lambda p: p.name)
def test_asking_for_a_bundle_changes_no_verdict(path, tmp_path, capsys):
    plain = cli.main(["check", str(path)])
    before = capsys.readouterr().out
    code, captured, _written = _bundle(tmp_path, capsys, str(path))
    assert code == plain, "asking for a bundle moved the exit code"
    assert captured.out == before, "asking for a bundle changed the report"


def test_a_refused_file_is_told_how_to_report_it_once(tmp_path, capsys):
    path = tmp_path / "not-a-zip.zip"
    path.write_bytes(b"this is not an archive")
    cli.main(["check", str(path), str(path)])
    err = capsys.readouterr().err
    assert err.count(cli.REFUSED) == 1, err


@pytest.mark.parametrize("spelling", ["--bundle-out={}", "--bundle={}"])
def test_a_path_given_in_one_word_stays_out_too(spelling, tmp_path, capsys):
    """`--bundle-out=DIR` and the option cut short are the same option to the
    parser, and a bundle that copied the command line carried the directory --
    and the user name in it -- whole."""
    out = tmp_path / f"out-{CANARY}"
    out.mkdir()
    code = cli.main(["check", str(FIXTURES / "m2-unknown-class-id.zip"), "--bug-report",
                     spelling.format(out)])
    capsys.readouterr()
    written = list(out.iterdir())
    assert code == 1 and len(written) == 1
    data = written[0].read_bytes()
    assert not [form for form in _forms(CANARY) if form in data]
    assert "<out-1>" in json.loads(data)["invocation"]["argv"]


def test_a_long_note_and_many_inputs_stay_within_the_limit(tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    one = str(FIXTURES / "m2-unknown-class-id.zip")
    cli.main(["check", *([one] * 50), "--bug-report", "--bundle-out", str(out),
              "--note", "x" * 300_000])
    capsys.readouterr()
    for written in out.iterdir():
        assert written.stat().st_size <= 256 * 1024
        bundle = json.loads(written.read_bytes())
        assert bundle["user"]["note"].endswith("[cut at 2,000 characters]")
        assert bundle["invocation"]["argv"][-1] == "<40 more inputs>"


def test_a_bundle_that_cannot_be_written_stops_nothing(tmp_path, capsys, monkeypatch):
    """A working directory nobody can write to is not a reason for the sweep to
    stop, or for its exit code to move."""
    one = str(FIXTURES / "m2-unknown-class-id.zip")

    def refuses(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")
    plain = cli.main(["check", one, one])
    capsys.readouterr()
    monkeypatch.setattr(cli.bundling, "write", refuses)
    assert cli.main(["check", one, one, "--bug-report"]) == plain
    err = capsys.readouterr().err
    assert err.count("could not be written") == 2, err


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes here")
def test_a_pipe_nobody_writes_to_does_not_hold_the_bundle_up(tmp_path):
    """The run reads a pipe once; the bundle does not open it a second time and
    wait for a writer that is gone."""
    pipe = tmp_path / "pipe.zip"
    os.mkfifo(pipe)
    done = subprocess.run([sys.executable, "-m", "vdi2770_validate", "check", str(pipe),
                           "--bug-report", "--bundle-out", str(tmp_path)],
                          capture_output=True, text=True, timeout=120,
                          env={**os.environ, "PYTHONPATH": os.pathsep.join(
                              [str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")])})
    assert done.returncode in (1, 2), done.stderr
    written = list(tmp_path.glob("bug-report-*.json"))
    assert written and json.loads(written[0].read_bytes())["input"]["kind"] == "stream"
