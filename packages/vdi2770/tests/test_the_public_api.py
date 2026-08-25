"""What `import vdi2770` promises, held by a test.

These run without `vdi2770-validate` installed and without touching the corpus,
because the point of splitting the package was that the library stands alone.
"""
import dataclasses
import io
import zipfile
from pathlib import Path

import pytest

import vdi2770

META = b"""<?xml version="1.0" encoding="utf-8"?>
<Document xmlns="http://www.vdi.de/schemas/vdi2770">
  <DocumentId DomainId="acme">D-1</DocumentId>
  <DocumentClassification ClassificationSystem="VDI2770:2018">
    <ClassId>02-01</ClassId>
    <ClassName Language="de">Allgemeine technische Daten</ClassName>
    <ClassName Language="en">General technical data</ClassName>
  </DocumentClassification>
  <DocumentVersion>
    <DocumentVersionId>1.0</DocumentVersionId>
    <Language>de</Language>
    <DocumentDescription Language="de"><Title>Datenblatt</Title></DocumentDescription>
    <LifeCycleStatus StatusValue="Released"/>
    <DigitalFile FileFormat="application/pdf">datenblatt.pdf</DigitalFile>
  </DocumentVersion>
</Document>
"""


def container(members, name="doc.zip"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in members.items():
            z.writestr(n, b)
    return vdi2770.read_container(buf.getvalue(), name)


# -- the round trip, which is the whole product ------------------------------

def test_a_document_container_reads_end_to_end():
    box = container({"VDI2770_Metadata.xml": META, "datenblatt.pdf": b"%PDF-1.7\n"})
    assert box.kind is vdi2770.Kind.DOCUMENT
    doc = vdi2770.build_document(vdi2770.parse_xml(box.metadata_bytes), box.where)
    assert doc.ids == ("D-1",)
    k = doc.classifications[0]
    assert k.class_id == "02-01" and k.system == "VDI2770:2018"
    assert {n.language: n.text for n in k.names}["de"] == "Allgemeine technische Daten"
    v = doc.versions[0]
    assert v.version_id == "1.0" and v.life_cycle_status == "Released"
    assert tuple(t.code for t in v.languages) == ("de",)
    assert v.languages[0].src.line, "a language element with no line is not a location"
    assert v.descriptions[0].title == "Datenblatt"
    assert v.files[0].file_name == "datenblatt.pdf"
    assert v.files[0].file_format == "application/pdf"


def test_every_node_remembers_where_it_was_written():
    """The reason to carry our own parser: a caller can point at the line."""
    base = vdi2770.Location("doc.zip", "VDI2770_Metadata.xml")
    doc = vdi2770.build_document(vdi2770.parse_xml(META), base)
    where = doc.classifications[0].src
    assert where.line == 4, f"expected the classification on line 4, got {where.line}"
    assert where.subject == "02-01"
    assert str(where).startswith("doc.zip!/VDI2770_Metadata.xml:4:")

    # The parts inside it, each on its own line. `ClassName.src`, `Tagged.src`
    # and `DocumentVersion.life_cycle_src` were added so a caller could point at
    # the element rather than the block around it -- and every test of them
    # lived in the validator, while `check_sdist.py` makes it literal that a
    # packager building this package alone runs *this* suite and nothing else.
    # Pointing all three back at their parent left this suite green.
    names = doc.classifications[0].names
    assert [n.src.line for n in names] == [6, 7], [n.src.line for n in names]
    assert names[0].src.line != where.line

    v = doc.versions[0]
    assert [t.src.line for t in v.languages] == [11], [t.src.line for t in v.languages]
    assert v.life_cycle_src.line == 13, v.life_cycle_src.line
    assert v.life_cycle_src.line != v.src.line


def test_a_documentation_container_is_recognised_and_walked():
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("VDI2770_Metadata.xml", META)
    box = container({"VDI2770_Main.xml": META, "VDI2770_Main.pdf": b"%PDF-1.7\n",
                     "d1.zip": inner.getvalue()}, "handover.zip")
    assert box.kind is vdi2770.Kind.DOCUMENTATION
    seen = sorted(c.path for c in box.walk())
    assert seen == ["handover.zip", "handover.zip!/d1.zip"], seen
    assert box.children[0].kind is vdi2770.Kind.DOCUMENT


def test_a_name_that_nearly_matched_is_reported_rather_than_ignored():
    box = container({"vdi2770_metadata.xml": META})
    assert box.kind is vdi2770.Kind.UNKNOWN
    kind, found = box.near_misses[vdi2770.METADATA_XML]
    assert (kind, found) == ("case-differs", "vdi2770_metadata.xml"), (kind, found)

    buried = io.BytesIO()
    with zipfile.ZipFile(buried, "w") as z:
        z.writestr("docs/VDI2770_Metadata.xml", META)
    box = vdi2770.read_container(buried.getvalue(), "sub.zip")
    assert box.near_misses[vdi2770.METADATA_XML] == ("in-a-subfolder", "docs/VDI2770_Metadata.xml")

    # Both branches, because only one of them was checked and a mutation putting
    # "it must sit at the root" back into the other walked straight through. A
    # package whose first line is that it decides nothing may not say "must".
    for kind, found in box.near_misses.values():
        assert " " not in kind, f"{kind!r} is a sentence, not a kind"
        assert "must" not in (kind + found).lower()


# -- the three properties ----------------------------------------------------

def test_a_budget_breach_is_a_defect_and_not_an_exception():
    """One hostile member must not cost the caller the other four hundred."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", META)
        z.writestr("bomb.bin", b"\0" * (vdi2770.zipread.MAX_MEMBER_BYTES + 1))
        z.writestr("ok.pdf", b"%PDF-1.7\n")
    box = vdi2770.read_container(buf.getvalue(), "doc.zip")
    assert box.metadata_bytes == META, "the good metadata still came back"
    assert "ok.pdf" in box.file_names, "the innocent member survived its neighbour"
    assert box.defects or box.rejected, "the oversized member was reported"
    for d in box.defects:
        assert isinstance(d, vdi2770.Defect) and d.kind


def test_an_entity_declaration_is_refused_rather_than_resolved():
    evil = (b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b'<Document xmlns="http://www.vdi.de/schemas/vdi2770">&x;</Document>')
    with pytest.raises(vdi2770.UnsafeXml):
        vdi2770.parse_xml(evil)
    assert issubclass(vdi2770.UnsafeXml, vdi2770.XmlError)


def test_reading_from_a_path_names_the_container_by_its_basename():
    """`read_container_file` is the first line of the README and had no test."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "sub" / "handover.zip"
        p.parent.mkdir()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("VDI2770_Metadata.xml", META)
        p.write_bytes(buf.getvalue())
        box = vdi2770.read_container_file(str(p))
    assert box.path == "handover.zip", "the caller's directory layout is not the container's name"
    assert box.kind is vdi2770.Kind.DOCUMENT


def test_nothing_is_written_to_disk(tmp_path, monkeypatch):
    """Both entry points, because the one the README recommends is the one that
    opens a file, and a mutation that made it write survived when this test
    only exercised the other.

    Watched at the interpreter's audit boundary rather than by replacing
    `builtins.open`: `io.open` is a second name for the same function, and a
    reader using it wrote sixty-four bytes per container while this passed.
    """
    from nodisk import hook_is_working, no_disk_writes

    assert hook_is_working(), "the watcher cannot see a write; it is proving nothing"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", META)
        z.writestr("a.pdf", b"%PDF-1.7\n")
    on_disk = tmp_path / "in" / "doc.zip"
    on_disk.parent.mkdir()
    on_disk.write_bytes(buf.getvalue())

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    with no_disk_writes():
        for box in (vdi2770.read_container(buf.getvalue(), "doc.zip"),
                    vdi2770.read_container_file(str(on_disk))):
            vdi2770.build_document(vdi2770.parse_xml(box.metadata_bytes), box.where)
            for _ in box.walk():
                pass
            vdi2770.read_pdf(vdi2770.member_bytes(buf.getvalue(), "a.pdf") or b"")
    assert not list(work.iterdir()), f"the library left {list(work.iterdir())} behind"


def test_nothing_reaches_for_the_network():
    """At the interpreter's boundary. The test below patches names on the
    `socket` module, and a caller that bound the constructor at import time
    reaches a different object — the same shape as the `io.open` hole this
    package's disk guard was rewritten for."""
    from nonetwork import hook_is_working, no_network

    assert hook_is_working(), "the audit hook is not seeing sockets"
    with no_network():
        box = container({"VDI2770_Metadata.xml": META})
        vdi2770.build_document(vdi2770.parse_xml(box.metadata_bytes), box.where)
        vdi2770.read_pdf(b"%PDF-1.7\ntrailer<</Root 1 0 R>>\n%%EOF")


def test_no_socket_is_opened(monkeypatch):
    import socket

    def boom(*a, **kw):
        raise AssertionError("the library opened a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    box = container({"VDI2770_Metadata.xml": META})
    vdi2770.build_document(vdi2770.parse_xml(box.metadata_bytes), box.where)


# -- what a PDF claims, and only that ----------------------------------------

def test_the_pdf_reader_reports_a_claim_and_never_a_verdict():
    facts = vdi2770.read_pdf(b"%PDF-1.7\n<?xpacket begin='' id='W5M0'?>"
                             b"<x><pdfaid:part>3</pdfaid:part>"
                             b"<pdfaid:conformance>A</pdfaid:conformance></x>"
                             b"<?xpacket end='w'?>")
    assert facts.is_pdf and facts.pdfa_claim == "3a"
    names = [f.name for f in dataclasses.fields(facts)]
    assert "pdfa_claim" in names
    assert not any(n in names for n in ("is_pdfa", "pdfa_valid", "conforms")), \
        f"a field named like a verdict invites one: {names}"


def test_a_file_that_is_not_a_pdf_says_so_without_guessing():
    facts = vdi2770.read_pdf(b"MZ\x90\x00not a pdf at all")
    assert facts.is_pdf is False and facts.pdfa_claim is None


def test_the_module_docstring_example_actually_runs(tmp_path, monkeypatch):
    """`help(vdi2770)` shipped an example using `c.at` and `doc.id`, neither of
    which exists. It was the first thing a new user would type."""
    import re
    import textwrap

    block = re.search(r"\n\n((?:    .*\n|\n)+?)\nThree properties", vdi2770.__doc__)
    assert block, "the docstring no longer starts with an example; update this test"
    code = textwrap.dedent(block.group(1))
    assert "read_container_file" in code

    box = io.BytesIO()
    with zipfile.ZipFile(box, "w") as z:
        z.writestr("VDI2770_Metadata.xml", META)
    (tmp_path / "manuals.zip").write_bytes(box.getvalue())
    monkeypatch.chdir(tmp_path)
    exec(compile(code, "<vdi2770 docstring>", "exec"), {})


def test_an_unterminated_xmp_opener_does_not_cost_quadratic_time():
    """`<?xpacket begin` repeated with no closer used to make every opener rescan
    the whole buffer. 128 KiB took 2.6 seconds and the cost squared with size, so
    a member sized just under the compression-ratio floor — which the reader
    accepts without a single defect — would have run for hours on a file small
    enough to email. The budgets did not catch it: they bound inflation, and this
    is the pass over the raw bytes.

    Timing is a blunt instrument in a test, so this asserts a ceiling loose
    enough to survive a slow machine and tight enough that quadratic cannot pass:
    the old code needed about eleven seconds for this input.
    """
    import time

    evil = b"%PDF-1.7\n" + (b"<?xpacket begin='" * (256 * 1024 // 17))
    start = time.perf_counter()
    facts = vdi2770.read_pdf(evil)
    elapsed = time.perf_counter() - start

    assert facts.is_pdf and facts.pdfa_claim is None
    assert elapsed < 1.0, f"took {elapsed:.1f}s for a {len(evil) // 1024} KiB scan"


def test_a_real_packet_is_still_found_after_a_broken_one():
    """The scan gives up on a kind once an opener has no closer. A file whose
    xpacket is malformed but whose xmpmeta is intact must still be read."""
    good = (b"<x:xmpmeta xmlns:x='adobe:ns:meta/'>"
            b"<rdf:Description xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/'>"
            b"<pdfaid:part>2</pdfaid:part><pdfaid:conformance>B</pdfaid:conformance>"
            b"</rdf:Description></x:xmpmeta>")
    assert vdi2770.read_pdf(b"%PDF-1.7\n<?xpacket begin='no end here'\n" + good).pdfa_claim == "2b"


def test_text_of_many_character_references_is_linear():
    """`node.text += chunk` is quadratic through an attribute — CPython's
    in-place-append shortcut needs a refcount-1 local and never gets one — and
    `&#120;` makes expat deliver one callback per reference. A 198 KB archive of
    them cost sixty seconds, with a clean verdict and nothing over budget: the
    metadata caps bound the bytes, and the work was superlinear in the bytes.

    Timed, so the ceiling is loose enough for a slow machine and tight enough
    that quadratic cannot pass: the old code needed about five seconds here.
    """
    import time

    body = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            b"<Summary>" + b"&#120;" * 800_000 + b"</Summary></Document>")
    start = time.perf_counter()
    node = vdi2770.parse_xml(body)
    elapsed = time.perf_counter() - start

    assert node.children[0].text == "x" * 800_000
    assert elapsed < 1.5, f"took {elapsed:.1f}s to parse {len(body) // 1024} KiB"


def test_text_split_across_callbacks_still_arrives_whole():
    """The chunks are joined at end-element. A CDATA section, an entity-free
    ampersand escape and a plain run all reach one element in several callbacks."""
    body = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            b"<Summary>plain <![CDATA[and bracketed]]> and &amp; escaped</Summary>"
            b"</Document>")
    assert vdi2770.parse_xml(body).children[0].text == "plain and bracketed and & escaped"


def test_a_member_the_reader_refused_cannot_be_read_by_a_later_layer():
    """The budgets in `read_container` are worth nothing if a caller can reopen
    the archive and inflate a member the reader threw out. `member_bytes` takes
    the allow-list for exactly that reason.

    This lived in the validator's suite, which is the wrong place for the SDK's
    only coverage of its own defence-in-depth: a packager building this
    distribution alone ran neither of these.
    """
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", b"<x/>")
        # Over MIN_SUSPICIOUS_BYTES and compressing about a thousandfold. Below
        # that floor the ratio is not treated as hostile, because a megabyte of
        # anything exhausts nothing.
        z.writestr("bomb.bin", b"0" * (16 * 1024 * 1024))
    raw = buf.getvalue()

    box = vdi2770.read_container(raw, "x.zip")
    assert "bomb.bin" in box.rejected, "the ratio cap should have refused it"
    allowed = set(box.file_names)
    assert vdi2770.member_bytes(raw, "bomb.bin", allowed=allowed) is None
    assert vdi2770.member_bytes(raw, "VDI2770_Metadata.xml", allowed=allowed) == b"<x/>"


def test_member_bytes_refuses_what_it_cannot_find():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", b"x")
    raw = buf.getvalue()
    assert vdi2770.member_bytes(raw, "missing.txt", allowed={"a.txt"}) is None
    assert vdi2770.member_bytes(b"not a zip", "a.txt") is None


def test_a_file_that_is_not_a_zip_is_the_defect_that_says_so():
    """Four behaviours lost their only coverage inside this distribution when the
    validator's duplicate suite was deleted: this one, the line on an XML error,
    the PDF facts, and an unreadable inner archive. A packager who builds
    `vdi2770` alone runs this suite and nothing else — `tools/check_sdist.py`
    makes that literal — so it has to hold them.
    """
    box = vdi2770.read_container(b"this is not a zip at all", "x.zip")
    assert box.kind is vdi2770.Kind.UNREADABLE
    assert [d.kind for d in box.defects] == ["not-a-zip"], [d.kind for d in box.defects]


def test_a_malformed_document_says_where_it_went_wrong():
    """The line number is why this package parses XML itself instead of handing
    back an ElementTree. The success path was covered; the error path was not."""
    with pytest.raises(vdi2770.XmlError) as caught:
        vdi2770.parse_xml(b"<Document>\n  <Open>\n</Document>")
    assert caught.value.line == 3, caught.value.line
    assert caught.value.column is not None
    # The position lives on the exception's attributes, not in its message —
    # which is the contract a caller builds a report from.
    assert (caught.value.line, caught.value.column) != (None, None)


def test_the_pdf_reader_reads_the_file_rather_than_assuming():
    """`encrypted` hard-coded to True would have passed this distribution's suite
    in every build."""
    plain = vdi2770.read_pdf(b"%PDF-1.7\nnothing to see here\n")
    assert plain.is_pdf and not plain.encrypted and plain.pdfa_claim is None
    locked = vdi2770.read_pdf(b"%PDF-1.7\ntrailer\n<< /Encrypt 12 0 R >>\n")
    assert locked.encrypted, "an encrypted PDF was read as plain"


def test_an_inner_archive_we_cannot_open_is_still_a_child():
    """Dropping unreadable children from the tree passed this suite; the caller
    would have seen a container that simply did not mention them."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'/>")
        z.writestr("broken.zip", b"PK\x03\x04 not really a zip")
    box = vdi2770.read_container(buf.getvalue(), "x.zip")
    unreadable = [c for c in box.children if c.kind is vdi2770.Kind.UNREADABLE]
    assert len(unreadable) == 1, [c.kind for c in box.children]
    assert unreadable[0].member_name == "broken.zip"


ENCRYPT_CASES = [
    ("a trailer that references an encryption dictionary",
     b"%PDF-1.7\n1 0 obj<</Type/Page>>endobj\n"
     b"trailer\n<< /Root 1 0 R /Encrypt 14 0 R >>\nstartxref\n9\n%%EOF", True),
    ("the same token inside a content stream",
     b"%PDF-1.7\n1 0 obj<</Type/Page>>endobj\n2 0 obj\nstream\n"
     b"(see /Encrypt 3 0 R for details)\nendstream endobj\n"
     b"trailer<</Root 1 0 R>>\n%%EOF", False),
    ("the same token in a comment",
     b"%PDF-1.7\n% /Encrypt 9 0 R was removed in revision 2\n"
     b"trailer<</Root 1 0 R>>\n%%EOF", False),
    ("no trailer at all",
     b"%PDF-1.7\n1 0 obj<</Type/Page>>endobj\n%%EOF", False),
]


@pytest.mark.parametrize("why,body,expected", ENCRYPT_CASES, ids=[c[0] for c in ENCRYPT_CASES])
def test_encryption_is_read_from_the_trailer_and_nowhere_else(why, body, expected):
    """`docs/scope.md` says this pattern "does not fire on the word appearing in
    a comment or a content stream". It did: the indirect reference was matched
    anywhere in the file, so a readable PDF that merely mentions `/Encrypt` in a
    string was reported as encrypted — an error on a file that is fine.

    A PDF whose trailer lives in a cross-reference stream is not read here and
    comes back False. That is a miss rather than a false alarm, and scope.md
    says so.
    """
    assert vdi2770.read_pdf(body).encrypted is expected, why


def test_every_node_carries_the_namespace_it_was_written_in():
    """`Node.ns` is populated on every element and `NS` is exported, and nothing
    in either package or either suite ever read either — setting `ns` to `""`
    everywhere left the whole suite green. A published field nobody checks is a
    claim nobody can rely on.
    """
    doc = vdi2770.parse_xml(
        b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'>"
        b"<DocumentId DomainId='d'>x</DocumentId>"
        b"<other xmlns='urn:something-else'/>"
        b"</Document>")
    assert doc.ns == vdi2770.NS
    kids = {n.tag: n.ns for n in doc.children}
    assert kids["DocumentId"] == vdi2770.NS
    assert kids["other"] == "urn:something-else", kids


@pytest.mark.parametrize("declared", ["XXXX", "utf-7", "utf-32", "cp99999"])
def test_an_encoding_this_parser_will_not_use_is_the_documents_problem(declared):
    """expat raises `LookupError` for an encoding nobody has and `ValueError`
    for one it will not decode, and neither is an `ExpatError`. Both escaped
    `parse`, so a caller that catches `XmlError` — which is the whole contract
    of this module — saw them as an unexpected crash.

    Downstream that became "a check in this tool raised an error", `about: tool`,
    with a remedy telling the sender nothing in their container needs changing.
    The document declares an encoding that does not exist. That is the
    document's problem, and it has a line number.
    """
    body = f'<?xml version="1.0" encoding="{declared}"?><a/>'.encode()
    with pytest.raises(vdi2770.XmlError) as e:
        vdi2770.parse_xml(body)
    assert not isinstance(e.value, vdi2770.UnsafeXml), "this is malformed, not hostile"
    assert declared.lower() in str(e.value).lower(), str(e.value)
    assert e.value.line, "a malformed document is reported at a line"


def test_encryption_is_found_however_long_the_trailer_dictionary_is():
    """The scan looked at a fixed window after each `trailer` keyword, so a
    legal dictionary whose `/ID` strings push `/Encrypt` past it read as *not
    encrypted* — and the report then told the producer to re-export as PDF/A, a
    remedy for a different problem, on a file it could not open.

    A window is the wrong shape for a dictionary. The dictionary ends where its
    braces balance, and that is what is read — still bounded, because a file
    that never closes them stops at the same cap the window used to impose.
    """
    big = b"<" + b"A" * 6000 + b">"
    enc = (b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n"
           b"trailer\n<< /Size 5 /Root 1 0 R /ID [" + big + b" " + big + b"]"
           b" /Encrypt 4 0 R >>\nstartxref\n0\n%%EOF")
    assert vdi2770.read_pdf(enc).encrypted, "the /Encrypt entry is in the trailer dictionary"

    plain = enc.replace(b"/Encrypt 4 0 R ", b"")
    assert not vdi2770.read_pdf(plain).encrypted

    # And the token outside any dictionary still does not count -- the false
    # positive this scan was narrowed to fix.
    inside = (b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n"
              b"2 0 obj<< /Length 20 >>stream\n/Encrypt 9 0 R\nendstream endobj\n"
              b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n0\n%%EOF")
    assert not vdi2770.read_pdf(inside).encrypted
