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
import zlib
from pathlib import Path

import pytest

import vdi2770.validate.bundle as bundling
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


def _as_bytes(value):
    """Every list of whole numbers in the bundle, read back as bytes the ways a
    list of numbers can hold text: one byte each, or two either way round. The
    bundle is mostly numbers, and a name carried as `[81, 122, 55, ...]` is a
    name carried."""
    if isinstance(value, dict):
        for inner in value.values():
            yield from _as_bytes(inner)
    elif isinstance(value, list):
        numbers = [v for v in value if type(v) is int]
        if numbers and len(numbers) == len(value):
            if all(0 <= v < 256 for v in numbers):
                yield bytes(numbers)
            if all(0 <= v < 65536 for v in numbers):
                yield b"".join(v.to_bytes(2, "little") for v in numbers)
                yield b"".join(v.to_bytes(2, "big") for v in numbers)
        for inner in value:
            yield from _as_bytes(inner)


def _leaks(data):
    """The canary in the bundle's bytes, or in any list of numbers in it."""
    places = [data, *_as_bytes(json.loads(data))]
    return [form for form in _forms(CANARY) for place in places if form in place]


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
        name = f"{CANARY}/{CANARY}-file.pdf"
        info = zipfile.ZipInfo(name)
        # Two extra fields, each holding the canary: one of no standard, and
        # the one Info-ZIP and WinZip write for every name that is not ASCII --
        # version, the CRC of the name in the header, and the name in UTF-8.
        # A walk over them that is one byte off reads names out of the second.
        unicode_path = b"\x01" + zlib.crc32(name.encode()).to_bytes(4, "little") + name.encode()
        info.extra = (b"\xfe\xca" + len(CANARY.encode()).to_bytes(2, "little") + CANARY.encode()
                      + b"\x75\x70" + len(unicode_path).to_bytes(2, "little") + unicode_path)
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
    leaks = _leaks(data)
    assert not leaks, f"the bundle carries the canary as {leaks[:3]}"
    assert CANARY not in written[0].name
    # And what it does carry is there: the shape, the rule codes, the note.
    bundle = json.loads(data)
    assert bundle["input"]["members"]["count"] == 2
    # Each row is numbers of the kind its field names, so nothing can ride in
    # a field as a list or a string; and of an extra field, the ids of its
    # records and not a byte of what they hold.
    members = bundle["input"]["members"]
    for row in members["rows"]:
        field = dict(zip(members["rowFields"], row))
        assert len(row) == len(members["rowFields"]), row
        assert all(type(field[k]) is int for k in ("i", "size", "csize", "method", "flagBits", "nameLen")), row
        assert all(field[k] is None or type(field[k]) is int for k in ("sameNameAs", "sameFoldedNameAs")), row
        assert type(field["utf8Flag"]) is bool and all(type(x) is int for x in field["extraIds"]), row
    assert dict(zip(members["rowFields"], members["rows"][1]))["extraIds"] == [0xCAFE, 0x7075]
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
    assert not _leaks(data)
    bundle = json.loads(data)
    assert bundle["bundle"]["trigger"] == "crash"
    assert bundle["error"]["type"] == "KeyError"
    assert "defect in this tool" in capsys.readouterr().err


def test_a_path_that_is_not_there_is_not_called_a_defect(tmp_path, capsys, monkeypatch):
    """A mistyped path is the caller's, not this tool's: no bundle is written
    for it, and nothing calls it a defect here."""
    monkeypatch.chdir(tmp_path)
    plain = cli.main(["check", str(tmp_path / "not-there.zip")])
    assert plain != 0
    assert not list(tmp_path.glob("bug-report-*.json")), "a mistyped path wrote a bundle"
    assert "defect in this tool" not in capsys.readouterr().err


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
    code, captured, written = _bundle(tmp_path, capsys, str(path))
    assert code == plain, "asking for a bundle moved the exit code"
    assert captured.out == before, "asking for a bundle changed the report"
    # And it was written. A bundle that fails to draw is said in one line and
    # the run goes on, which is right for the run and would be silence here:
    # a defect that hits only some inputs would pass every assertion above.
    assert len(written) == 1 and "could not be written" not in captured.err, captured.err


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
    assert "could not be written" not in capsys.readouterr().err
    assert list(out.iterdir()), "no bundle was written, so nothing below was checked"
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


def test_a_note_the_console_could_not_decode_stops_nothing(tmp_path, capsys):
    """A note typed in another code page -- a name with an umlaut from a Latin-1
    terminal, Korean from a script saved in CP949 -- arrives holding bytes the
    locale could not decode. The run is the same run, and the bundle keeps what
    it can of the note."""
    one, two = str(FIXTURES / "m2-unknown-class-id.zip"), str(FIXTURES / "m5-bad-language-code.zip")
    plain = cli.main(["check", "--json", one, two])
    before = capsys.readouterr().out
    code, captured, written = _bundle(tmp_path, capsys, "--json", one, two, "--note", "M\udcfcller")
    assert code == plain, "a note moved the exit code"
    assert captured.out == before, "a note changed the report"
    assert len(written) == 2, written
    for each in written:
        assert json.loads(each.read_bytes())["user"]["note"] == "M\ufffdller"


def test_a_bundle_that_cannot_be_drawn_stops_nothing(tmp_path, capsys, monkeypatch):
    """Whatever goes wrong in drawing the bundle, not only in writing it, is said
    once and the sweep goes on with the same report and the same exit code."""
    one, two = str(FIXTURES / "m2-unknown-class-id.zip"), str(FIXTURES / "m5-bad-language-code.zip")
    plain = cli.main(["check", one, two])
    before = capsys.readouterr().out

    def breaks(**_kwargs):
        raise ValueError("drawing the bundle fell over")
    monkeypatch.setattr(cli.bundling, "build", breaks)
    assert cli.main(["check", one, two, "--bug-report"]) == plain
    captured = capsys.readouterr()
    assert captured.out == before
    assert captured.err.count("could not be written") == 2, captured.err


def test_an_input_that_reads_back_short_is_not_described_by_what_came_back(monkeypatch):
    """What is read again for the bundle has to be what the file says it holds,
    or it is not the input the run read."""
    path = FIXTURES / "m2-unknown-class-id.zip"
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"")
    shape = bundling.fingerprint(str(path))
    monkeypatch.undo()
    assert shape["kind"] == "stream" and shape["size"] is None, shape


@pytest.mark.skipif(not os.path.exists("/dev/stdin"), reason="no /dev/stdin here")
def test_a_file_given_as_standard_input_is_not_called_empty(tmp_path):
    """`check /dev/stdin < file`: on macOS and the BSDs, opening the descriptor's
    name again shares the offset the run left at the end, so a second read
    comes back empty. The bundle says the file's size, or that it does not know
    it -- never 0 bytes for a file that was not empty."""
    path = FIXTURES / "m8-unlabelled-class-name.zip"
    with open(path, "rb") as given:
        subprocess.run([sys.executable, "-m", "vdi2770_validate", "check", "/dev/stdin",
                        "--bug-report", "--bundle-out", str(tmp_path)],
                       stdin=given, capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PYTHONPATH": os.pathsep.join(
                           [str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")])})
    written = list(tmp_path.glob("bug-report-*.json"))
    assert len(written) == 1, written
    shape = json.loads(written[0].read_bytes())["input"]
    assert shape["size"] in (None, path.stat().st_size), shape


def test_with_stderr_closed_the_report_stays_a_report(tmp_path, capsys, monkeypatch):
    """With stderr closed -- `2>&-`, or pythonw with no console -- there is no
    `sys.stderr`, and a line printed to it goes to stdout, into the JSON a
    machine is about to read. The line saying a path could not be read did
    so before any bundle existed. That, the sentence after a refusal, the
    bundle's summary and where it went are said nowhere then, and the report
    is the report."""
    refused, missing = str(FIXTURES / "z1-not-a-zip.zip"), str(tmp_path / "not-there.zip")
    monkeypatch.chdir(tmp_path)
    plain = cli.main(["check", "--json", refused, missing])
    before = capsys.readouterr().out
    monkeypatch.setattr(sys, "stderr", None)
    assert cli.main(["check", "--json", refused, missing, "--bug-report"]) == plain
    after = capsys.readouterr().out
    assert after == before, "a line meant for a person is in the report"
    json.loads(after)


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
