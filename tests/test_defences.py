"""Each defence, exercised — and each budget, pinned.

A mutation sweep set every cap to 10**18 and deleted the path-traversal checks
one at a time; the suite noticed six of fifteen. The gap was structural: the
caps were only ever exercised through one fixture, and a budget you cannot
afford to reach in a test is a budget nothing checks.

So each one is tested twice. The *mechanism* is exercised with the budget
monkeypatched down to something a test can reach, and the *size* is pinned
separately, because a mechanism that works perfectly at 10**18 protects nobody.
"""
import io
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT
from vdi2770 import pdfread, xmlread, zipread

BASE = {n: zipfile.ZipFile(CLEAN_DOCUMENT).read(n)
        for n in zipfile.ZipFile(CLEAN_DOCUMENT).namelist()}


def pack(members, compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


# --- the sizes themselves ----------------------------------------------------

BUDGETS = {
    "MAX_MEMBERS": (100, 100_000),
    "MAX_MEMBER_BYTES": (1 << 20, 2 << 30),
    "MAX_TOTAL_BYTES": (1 << 20, 8 << 30),
    "MAX_RATIO": (10, 10_000),
    "MAX_METADATA_BYTES": (1 << 20, 256 << 20),
    "MAX_CONTAINER_LEVELS": (2, 8),
    # Added after the table was written, and left out of it until an audit asked
    # why the docstring above says every budget is pinned.
    "MIN_SUSPICIOUS_BYTES": (1 << 20, 64 << 20),
    "MAX_CONTAINERS": (100, 100_000),
    "MAX_TOTAL_METADATA_BYTES": (8 << 20, 1 << 30),
}
PDF_BUDGETS = {
    "MAX_STREAM_SCAN": (1 << 10, 8 << 20),
    "MAX_INFLATED_PER_STREAM": (1 << 20, 64 << 20),
    "MAX_INFLATED_TOTAL": (1 << 20, 256 << 20),
    "MAX_STREAMS": (16, 100_000),
    "MAX_XMP_PACKETS": (4, 4096),
    "MAX_PDFA_PREFIXES": (1, 64),
}


def test_every_budget_constant_is_in_one_of_those_tables():
    """The tables were written by hand and then the code grew three more caps.
    A budget nobody pinned is a budget that can be raised to 10**18 in a commit
    that looks like a tidy-up."""
    for module, table in ((zipread, BUDGETS), (pdfread, PDF_BUDGETS)):
        declared = {n for n in vars(module)
                    if n.startswith(("MAX_", "MIN_")) and isinstance(getattr(module, n), int)}
        missing = sorted(declared - set(table))
        assert not missing, f"{module.__name__} has unpinned budgets: {missing}"


@pytest.mark.parametrize("name,bounds", sorted(BUDGETS.items()))
def test_a_zip_budget_is_a_budget(name, bounds):
    low, high = bounds
    value = getattr(zipread, name)
    assert low <= value <= high, (
        f"{name} is {value}; outside {low}..{high} it is not protecting anyone")


@pytest.mark.parametrize("name,bounds", sorted(PDF_BUDGETS.items()))
def test_a_pdf_budget_is_a_budget(name, bounds):
    low, high = bounds
    value = getattr(pdfread, name)
    assert low <= value <= high, f"{name} is {value}; outside {low}..{high}"


# --- the mechanisms ----------------------------------------------------------

def test_too_many_members_is_refused(monkeypatch):
    monkeypatch.setattr(zipread, "MAX_MEMBERS", 3)
    c = zipread.read(pack({f"f{i}.txt": b"x" for i in range(10)}), "x.zip")
    assert c.kind is zipread.Kind.UNREADABLE
    assert "too-many-members" in {d.kind for d in c.defects}


def test_an_oversized_member_is_refused(monkeypatch):
    monkeypatch.setattr(zipread, "MAX_MEMBER_BYTES", 16)
    c = zipread.read(pack({"VDI2770_Metadata.xml": b"<x/>", "big.bin": b"y" * 4096}), "x.zip")
    assert "big.bin" in c.rejected
    assert "big.bin" not in c.file_names


def test_an_oversized_archive_stops_being_read(monkeypatch):
    monkeypatch.setattr(zipread, "MAX_TOTAL_BYTES", 64)
    c = zipread.read(pack({f"f{i}.bin": b"z" * 128 for i in range(8)}), "x.zip")
    assert "archive-too-large" in {d.kind for d in c.defects}


def test_metadata_over_the_parse_budget_is_refused(monkeypatch):
    monkeypatch.setattr(zipread, "MAX_METADATA_BYTES", 8)
    c = zipread.read(pack({"VDI2770_Metadata.xml": b"<Document/>" * 10}), "x.zip")
    assert "metadata-too-large" in {d.kind for d in c.defects}
    assert c.metadata_bytes is None


def test_pdf_inflation_stops_at_the_total_budget(monkeypatch):
    import zlib
    monkeypatch.setattr(pdfread, "MAX_INFLATED_TOTAL", 1000)
    body = b"%PDF-1.7\n" + b"".join(
        b"stream\n" + zlib.compress(b"Q" * 100_000) + b"\nendstream\n" for _ in range(20))
    assert sum(len(h) for h in pdfread._haystacks(body)) < len(body) + 200_000


def test_pdf_scanning_stops_after_the_stream_budget(monkeypatch):
    import zlib
    monkeypatch.setattr(pdfread, "MAX_STREAMS", 2)
    one = b"stream\n" + zlib.compress(b"Q" * 50_000) + b"\nendstream\n"
    body = b"%PDF-1.7\n" + one * 20
    inflated = list(pdfread._haystacks(body))[1:]        # drop the raw bytes
    assert len(inflated) <= 2
    # A ceiling on its own passes when `_haystacks` yields nothing at all, which
    # is the one way this budget could stop protecting anything. Exactly one gets
    # through here, not two: `MAX_STREAMS` bounds attempts, and the stream marker
    # also matches inside `endstream`, so every other attempt is a false start
    # that fails to inflate. That is the budget doing what its docstring says —
    # "the number of streams we will even try" — and worth knowing before
    # somebody reads the constant as a count of real streams.
    assert inflated, "the budget stopped everything, including the first stream"


# --- hostile names -----------------------------------------------------------

@pytest.mark.parametrize("name,why", [
    ("/etc/passwd", "absolute path"),
    ("C:\\Windows\\evil.txt", "drive letter"),
    ("dir\\..\\..\\evil.txt", "backslash separator with traversal"),
    ("subdir\\evil.txt", "backslash separator alone"),
    ("../escape.txt", "parent-directory segment"),
    ("a/../../b.txt", "parent-directory segment in the middle"),
])
def test_a_hostile_member_name_never_reaches_the_member_list(name, why):
    c = zipread.read(pack({"VDI2770_Metadata.xml": b"<x/>", name: b"x"}), "x.zip")
    assert name not in c.file_names, f"{why}: {name!r} was accepted"
    assert name in c.rejected, f"{why}: {name!r} was dropped without being reported"


# --- names are case-sensitive ------------------------------------------------

@pytest.mark.parametrize("name", ["vdi2770_metadata.xml", "VDI2770_METADATA.XML",
                                  "vdi2770_main.xml"])
def test_a_case_variant_is_not_a_container(name):
    """The reference matches these names exactly. Accepting a case variant would
    make this tool pass containers the recipient's tooling will reject."""
    c = zipread.read(pack({name: b"<x/>"}), "x.zip")
    assert c.kind is zipread.Kind.UNKNOWN, f"{name!r} was treated as a container"
    assert c.near_misses, "and nothing explained why"


# --- entities ----------------------------------------------------------------

def test_every_kind_of_entity_declaration_is_refused():
    """Internal, external and parameter declarations all go through the same
    handler, which is why the external-reference handler in xmlread is
    unreachable today. Measured, not assumed — see the comment there."""
    for doc in (
        b"<!DOCTYPE r [<!ENTITY a 'x'>]><r>&a;</r>",
        b"<!DOCTYPE r [<!ENTITY a SYSTEM 'file:///etc/passwd'>]><r>&a;</r>",
        b"<!DOCTYPE r [<!ENTITY % p SYSTEM 'http://a.example/p.dtd'> %p;]><r/>",
    ):
        with pytest.raises(xmlread.UnsafeXml):
            xmlread.parse(doc)


def test_an_external_dtd_subset_alone_is_not_fetched(monkeypatch):
    """This one fires neither handler: expat leaves an external subset alone
    because parameter-entity parsing is off. Pinned so that a future change to
    the parser setup cannot quietly turn fetching on."""
    import socket
    monkeypatch.setattr(socket, "socket",
                        lambda *a, **k: pytest.fail("the parser reached for the DTD"))
    xmlread.parse(b'<!DOCTYPE Document SYSTEM "http://attacker.example/x.dtd">'
                  b'<Document xmlns="http://www.vdi.de/schemas/vdi2770"/>')


@pytest.mark.parametrize("code,ok", [
    ("de", True), ("DE", True), ("deu", True), ("gsw", True),
    ("ДЕЮ", False), ("한국어", False), ("de-DE", False), ("zz", False), ("deutsch", False),
])
def test_iso_639_accepts_only_ascii_letter_codes(code, ok):
    from vdi2770_validate.rules.metadata import _iso_ok
    assert _iso_ok(code) is ok
