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

    Sized just under `MAX_TEXT_PIECES`, which now refuses this shape past a
    point — the two bounds answer different questions and both have to hold. That
    cap is why the count here is no longer 800,000.
    """
    import time

    from vdi2770 import xmlread

    n = xmlread.MAX_TEXT_PIECES - 1
    body = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            b"<Summary>" + b"&#120;" * n + b"</Summary></Document>")
    start = time.perf_counter()
    node = vdi2770.parse_xml(body)
    elapsed = time.perf_counter() - start

    assert node.children[0].text == "x" * n
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


def test_a_dictionary_ends_at_its_own_braces_and_not_inside_a_string():
    """Balancing `<< >>` closed one hole and opened another. PDF strings and
    comments contain arbitrary bytes, so `(value <<redacted)` counted as a
    dictionary opening, the depth never returned to zero, and the scan ran to
    its cap — picking up an `/Encrypt` that a *comment* mentioned. The tool then
    told the sender their unencrypted file was encrypted, which is the exact
    false positive the trailer scan was narrowed to fix.
    """
    plain = (b"%PDF-1.4\ntrailer\n<< /ID [(note: value <<redacted)] /Root 1 0 R >>\n"
             b"% reminder: strip /Encrypt 3 0 R from the export profile\n%%EOF")
    assert not vdi2770.read_pdf(plain).encrypted

    hexed = (b"%PDF-1.4\ntrailer\n<< /ID [<3c3c>] /Root 1 0 R >>\n"
             b"/Encrypt 3 0 R\n%%EOF")
    assert not vdi2770.read_pdf(hexed).encrypted

    # And the thing it is for still works, including a nested dictionary.
    real = (b"%PDF-1.4\ntrailer\n<< /Root 1 0 R /Extra << /Deep 1 >> "
            b"/ID [(x) (y)] /Encrypt 4 0 R >>\n%%EOF")
    assert vdi2770.read_pdf(real).encrypted


def test_a_file_full_of_the_word_trailer_is_not_expensive():
    """The docstring said a bounded window means "a file full of the word
    `trailer` cannot make this quadratic". Replacing the window with a brace walk
    kept the sentence and lost the property: with no `<<` after the keyword the
    walk scans its whole 64 KiB cap, once per keyword. A 128 KB member cost
    **135 seconds**, measured — from an archive of 1.5 KB.
    """
    import time

    body = b"%PDF-1.4\n" + b"trailer\n" * 16_000
    started = time.process_time()
    assert not vdi2770.read_pdf(body).encrypted
    assert time.process_time() - started < 5, (
        "a keyword with no dictionary after it costs a scan")


# --- the trailer scan, as a class rather than as three fixed instances -------
#
# This scan has been repaired three times and each repair addressed the shape
# that had been found: a whole-file token search, then a fixed window, then a
# brace walk, then a brace walk that skips strings. Each one left the same class
# open somewhere else, because the class is "ad-hoc byte scanning of a format
# that has structure". These are all the shapes at once.

ENC = b"%PDF-1.4\ntrailer\n<< /Size 5 /Root 1 0 R %s/Encrypt 4 0 R >>\nstartxref\n0\n%%EOF"


def _pdf(dictionary: bytes) -> bytes:
    return b"%PDF-1.4\ntrailer\n" + dictionary + b"\nstartxref\n0\n%%EOF"


@pytest.mark.parametrize("name,body,expected", [
    ("plain dictionary",
     b"<< /Size 5 /Root 1 0 R /Encrypt 4 0 R >>", True),
    ("no encrypt at all",
     b"<< /Size 5 /Root 1 0 R >>", False),
    ("nested dictionary before it",
     b"<< /Root 1 0 R /Extra << /Deep 1 >> /Encrypt 4 0 R >>", True),
    ("long /ID pushes it past any window",
     b"<< /ID [<" + b"A" * 6000 + b"> <" + b"A" * 6000 + b">] /Encrypt 4 0 R >>", True),
    # The token in a comment or a string is not a key. Reporting it told the
    # sender to send an unprotected copy of a file that was never protected.
    ("token inside a comment",
     b"<< /Size 5 %/Encrypt 4 0 R was stripped\n>>", False),
    ("token inside a literal string",
     b"<< /Info (see /Encrypt 4 0 R in the old file) >>", False),
    # Not `<< /ID [<2f456e...>] >>`, which was here and could not fail: the
    # bytes are hex, so no scanner finds `/Encrypt` in them with the branch or
    # without it. What the branch actually protects is a hex string whose `>`
    # abuts the dictionary's -- remove it and `<41>>` closes the dictionary one
    # byte early, and the reference after it is never seen.
    ("a hex string whose close abuts the dictionary's",
     b"<< /X <41>> /Encrypt 4 0 R >>", True),
    ("token after a string holding >>",
     b"<< /Info (ends with >> here) /Encrypt 4 0 R >>", True),
    ("token after a string holding <<",
     b"<< /Info (opens with << here) /Encrypt 4 0 R >>", True),
    ("token outside the dictionary",
     b"<< /Size 5 >>\n/Encrypt 4 0 R", False),
    ("escaped paren does not end the string",
     rb"<< /Info (a \) /Encrypt 4 0 R still inside) >>", False),
    ("comment inside a string is not a comment",
     b"<< /Info (100% /Encrypt 4 0 R) >>", False),
])
def test_the_trailer_scan_reads_pdf_structure(name, body, expected):
    assert vdi2770.read_pdf(_pdf(body)).encrypted is expected, name


@pytest.mark.parametrize("name,body", [
    ("a keyword with no dictionary", b"trailer\n" * 16_000),
    ("a dictionary that opens and never closes", b"trailer<<" * 8_000),
    ("a string that never closes", b"trailer\n<< /Info (" + b"x" * 200_000),
    ("nesting with no end", b"trailer\n" + b"<<" * 30_000),
    ("comments to the horizon", b"trailer\n<< " + b"%c\n" * 60_000),
    # The same shapes, as many times as the keyword cap allows. Each case above
    # is one keyword, so all five passed while the *product* of the two bounds
    # went unmeasured: 64 comment dictionaries cost 11.6 seconds from an archive
    # that deflates to five kilobytes. A bound nobody multiplied out is not a
    # bound, which is the sentence this module has now earned twice.
    ("comments to the horizon, once per trailer",
     (b"trailer\n<< " + b"%c\n" * 60_000) * 64),
    ("a dictionary that opens and never closes, once per trailer",
     (b"trailer<<" + b"x" * 70_000) * 64),
# Named by the case, not by the body: pytest builds the id out of every
# parameter, and a 4 MB `bytes` in the id turned one failure into fourteen
# megabytes of output on the terminal that was supposed to explain it.
], ids=lambda v: v if isinstance(v, str) else "")
def test_no_shape_of_trailer_is_expensive(name, body):
    """The budget is for the file, not for each keyword. Per-keyword bounds meant
    every new shape that reached the bound multiplied by however many keywords a
    sender cared to write: 16,000 bare ones cost 135 s, and when that was fixed,
    8,000 that *open* a dictionary cost 28 s on a 20 KB archive. A total is the
    only bound that does not have another shape behind it.
    """
    # CPU time, not wall clock. This is a claim about how much work the scan
    # does, and a wall clock also measures every other process on the box: the
    # assertion below has flaked on a loaded machine, both
    # times on code whose cost had just been *reduced*. Four timed assertions in
    # this project have now failed for that reason; the ones that could be
    # counted have been, and this is the residue that cannot.
    import time

    started = time.process_time()
    vdi2770.read_pdf(b"%PDF-1.4\n" + body)
    spent = time.process_time() - started
    assert spent < 3, f"{name}: {len(body) / 1024:.0f} KiB cost {spent:.1f}s CPU"


@pytest.mark.parametrize("name,body,expected", [
    # An incremental update appends a trailer, and the *last* one is the
    # authoritative one. A file-wide scan budget let an ordinary earlier trailer
    # -- a long `/ID`, a long `/Info` -- spend it, after which the real one was
    # never looked at. That is the false-negative direction: the report then
    # tells the producer to re-export as PDF/A, on a file it could not open.
    ("an earlier trailer with a long /ID",
     b"trailer\n<< /ID [<" + b"A" * 66000 + b">] >>\ntrailer\n<< /Encrypt 4 0 R >>", True),
    ("an earlier trailer with a long /Info",
     b"trailer\n<< /Info (" + b"x" * 70000 + b") >>\ntrailer\n<< /Encrypt 4 0 R >>", True),
    # A comment is legal between the keyword and the dictionary. Comments were
    # skipped inside the dictionary and not at the door to it -- the same
    # "handled it in one place and not the symmetric one" this file keeps
    # producing.
    ("a comment between the keyword and the dictionary",
     b"trailer\n%binary marker\n<< /Encrypt 4 0 R >>", True),
    # And the other direction: the token is only the trailer's encryption
    # reference where a key can be. Matching it at any depth made an array
    # element and a nested dictionary's value count.
    ("the token inside an array",
     b"trailer\n<< /Foo [/Encrypt 4 0 R] >>", False),
    ("the token as a nested dictionary's value",
     b"trailer\n<< /Root << /X /Encrypt 4 0 R >> >>", False),
])
def test_the_trailer_scan_reads_the_whole_file_and_only_keys(name, body, expected):
    assert vdi2770.read_pdf(b"%PDF-1.4\n" + body + b"\nstartxref\n0\n%%EOF"
                            ).encrypted is expected, name


def test_the_trailers_that_are_read_are_the_last_ones():
    """More trailers than the cap, and the encryption reference in the newest.

    An incremental update appends: the file's history is at the front and its
    present state is at the back. Reading the first `MAX_TRAILERS` would report
    the document as it was before it was encrypted, which is the wrong answer
    from a scan whose whole job is to say whether this file can be read.
    """
    from vdi2770.pdfread import MAX_TRAILERS

    older = b"trailer\n<< /Size 9 >>\n" * (MAX_TRAILERS + 40)
    pdf = (b"%PDF-1.4\n" + older
           + b"trailer\n<< /Size 9 /Encrypt 4 0 R >>\nstartxref\n0\n%%EOF")
    assert vdi2770.read_pdf(pdf).encrypted is True


def test_no_more_of_the_trailers_is_read_than_the_budget_names(monkeypatch):
    """Counted, not timed.

    The cost of this scan is the number of dictionaries walked times the bytes
    walked in each. Without a bound, 16,000 `trailer` keywords in a 125 KB file
    cost 135 seconds. What is bounded is now the product rather than each factor
    -- a cap on how many to read was a cap on *where* to look, and an appender
    pushed the real trailer past it with 658 bytes -- so this counts the bytes,
    not the calls. A stopwatch assertion in this project has twice failed under
    load and said nothing about the bound it was written to defend.
    """
    from vdi2770 import pdfread

    read = []
    real = pdfread._scan_dictionary

    def counting(data, start, budget):
        spent, found = real(data, start, budget)
        read.append(spent)
        return spent, found

    monkeypatch.setattr(pdfread, "_scan_dictionary", counting)
    vdi2770.read_pdf(b"%PDF-1.4\n" + b"trailer\n<< /Size 9 >>\n" * 4000)
    # The declared-offset attempt is one call outside the budgeted loop, and it
    # is bounded on its own, so it is allowed on top rather than inside.
    assert sum(read) <= pdfread.MAX_TRAILER_BYTES + pdfread.MAX_TRAILER_SCAN, (
        f"{sum(read)} bytes of trailer dictionaries read for a file allowed "
        f"{pdfread.MAX_TRAILER_BYTES}")


def test_a_trailer_written_where_nothing_reads_it_is_not_a_trailer(monkeypatch):
    """The decoys were not merely out of the window; they were in comments.

    `%trailer` is the word after a `%`, which runs to the end of the line, so no
    conformant reader ever saw it as a keyword. This one did, and then paid for
    it twice: the token spent budget the real trailer needed, and the scan's
    lead-in -- which skips comments looking for `<<` -- walked forward through
    every decoy that followed. Five thousand of them turned a 60 KB file into a
    quadratic one.
    """
    from vdi2770 import pdfread

    calls = []
    real = pdfread._scan_dictionary

    def counting(data, start, budget):
        calls.append(1)
        return real(data, start, budget)

    monkeypatch.setattr(pdfread, "_scan_dictionary", counting)
    pdf = (b"%PDF-1.4\ntrailer\n<< /Size 9 >>\n" + b"\n%trailer\n" * 5000
           + b"startxref\n9\n%%EOF\n")
    vdi2770.read_pdf(pdf)
    assert len(calls) <= 3, (
        f"{len(calls)} dictionaries walked for a file with one trailer and "
        f"5,000 mentions of the word in comments")


def _pdf_with_xref(trailer: bytes) -> bytes:
    """A minimal PDF whose `startxref` really points at its cross-reference.

    Built rather than vendored: this package is tested standalone, with no
    repository around it, so a fixture from `corpus/` is not available to it.
    """
    head = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    table = b"xref\n0 2\n0000000000 65535 f \n0000000009 00000 n \n"
    body = head + table + b"trailer\n" + trailer + b"\n"
    return body + b"startxref\n" + str(len(head)).encode() + b"\n%%EOF\n"


def test_a_decoy_after_the_end_cannot_hide_the_real_trailer():
    """Ten bytes of `%trailer` repeated, appended after `%%EOF`.

    An earlier version read the *last* `MAX_TRAILERS` dictionaries, because an
    incremental update appends and the newest trailer is the authoritative one.
    That is true of a file nobody is attacking. Sixty-four occurrences of the
    token appended after the end -- 640 bytes, ignored by every conformant
    reader -- push the real trailer out of the window, and a genuinely encrypted
    PDF comes back clean. The report then drops `P2` (*remove the protection*)
    and offers `P3` (*produce the file as PDF/A*): a remedy for a defect the
    producer's exporter does not have.

    Every window this scan has used was a guess about where to look, and every
    guess was pushable by an appender. `startxref` is not a guess -- it is where
    the format says the answer is, and it is what a reader follows.
    """
    real = _pdf_with_xref(b"<< /Size 2 /Encrypt 4 0 R >>")
    assert vdi2770.read_pdf(real).encrypted is True, "premise"
    for decoys in (1, 63, 64, 200, 5_000):
        grown = real + b"\n%trailer\n" * decoys
        assert vdi2770.read_pdf(grown).encrypted is True, f"{decoys} decoys"


def test_a_decoy_that_brings_its_own_startxref_cannot_hide_the_real_trailer():
    """The decoy test above pinned the half that was fixed.

    Following `startxref` is not a guess about where to look -- but `rfind` takes
    the *last* one, and an appender writes decoys and then a `startxref` of its
    own. Twenty more bytes: the declared offset resolves to nothing, the fallback
    is the same positional window as before, and the encrypted PDF is clean
    again. `P2` (*remove the protection*) goes and `P3` (*produce the file as
    PDF/A*) arrives, which is a remedy for a defect the producer does not have.

    A bound on *where* to look is pushable by definition. The bound has to be on
    *how much* is read: a decoy that is not a dictionary costs a couple of bytes
    to reject, so thousands of them no longer buy an attacker anything.
    """
    real = _pdf_with_xref(b"<< /Size 2 /Encrypt 4 0 R >>")
    assert vdi2770.read_pdf(real).encrypted is True, "premise"
    for decoys in (1, 64, 200, 5_000):
        grown = (real + b"\n%trailer\n" * decoys
                 + b"startxref\n9\n%%EOF\n")
        assert vdi2770.read_pdf(grown).encrypted is True, f"{decoys} decoys"


def test_an_offset_too_long_to_be_an_offset_is_not_an_exception():
    """`int()` on a long digit run raises, and this is a library.

    CPython 3.11 caps integer parsing at 4,300 digits; the pattern took `\\d+`
    and handed whatever it caught to `int()`. Five thousand digits after
    `startxref` -- a file of a few kilobytes -- came back as `ValueError` out of
    `read_pdf` on 3.12 and 3.13, which this package's CI runs and whose contract
    is that it records a defect rather than raising. Through the validator it
    took the whole PDF layer down with it: `P1` through `P4` never ran, so it was
    also a second, cheaper way to make an encrypted file look unencrypted.

    No offset into a real file has twenty digits, so nothing that could have been
    an answer is lost by declining to read one.
    """
    huge = b"%PDF-1.4\nstartxref\n" + b"9" * 5000 + b"\n%%EOF\n"
    assert vdi2770.read_pdf(huge).encrypted is False

    # And the bound itself, because the interpreter this suite happens to run on
    # decides whether the line above can fail at all: 3.9 has no cap and parses
    # five thousand digits without complaint, so on 3.9 the assertion passes
    # against the very code that raises in CI.
    from vdi2770.pdfread import _STARTXREF

    hit = _STARTXREF.match(b"startxref\n" + b"9" * 5000)
    assert hit is None or len(hit.group(1)) <= 20, (
        f"the pattern accepts a {len(hit.group(1))}-digit offset, which `int` "
        f"refuses above 4,300 on 3.11 and later")


def test_a_cross_reference_stream_trailer_is_read():
    """PDF 1.5 puts the trailer in an object, and this said it read it.

    `_declared_trailer`'s own docstring said the dictionary "opens within a few
    bytes of the offset" and returned the offset -- which points at `4 0 obj`,
    not at `<<`, so the scan found no dictionary there and every such file came
    back unencrypted. Forty lines above, the other docstring said the same file
    "comes back False". One of them had to go; the one worth keeping is the one
    that makes the file readable.
    """
    head = b"%PDF-1.5\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    obj = b"4 0 obj\n<< /Type /XRef /Size 5 /Encrypt 6 0 R >>\nstream\nendstream\nendobj\n"
    body = head + obj
    pdf = body + b"startxref\n" + str(len(head)).encode() + b"\n%%EOF\n"
    assert b"trailer" not in pdf, "the point is that there is no trailer keyword"
    assert vdi2770.read_pdf(pdf).encrypted is True


def test_a_file_with_no_startxref_is_still_read():
    """Damaged, truncated, or hand-written: the token scan is still there.

    Following `startxref` is right for every file that has one -- all fifty-five
    PDFs in this repository's corpus do -- and a file that does not is exactly
    the file that needs the fallback most.
    """
    assert vdi2770.read_pdf(b"%PDF-1.4\ntrailer\n<< /Encrypt 4 0 R >>\n").encrypted is True
    assert vdi2770.read_pdf(b"%PDF-1.4\ntrailer\n<< /Size 9 >>\n").encrypted is False


def test_a_size_the_archive_only_claims_is_not_stated_as_fact():
    """A 120 KiB archive said one of its members was 629,145,600 bytes.

    Every size in the readability sweep comes from the central directory, which
    is whatever the writer put there. `member_bytes` re-checks the declared size
    against the bytes it actually inflates and says in its own docstring that a
    ZIP header can lie about it; the sweep quotes the number and does not.

    Nothing here can be cheaper — checking would mean inflating the member,
    which is the work the budget exists to avoid — so the sentence has to say
    whose number it is. A recipient cannot compare *629,145,600 bytes* against
    the file in their hand and find anything but a contradiction.
    """
    import io
    import struct
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", b"<x/>")
        z.writestr("B.pdf", b"%PDF-1.4\n")
    raw = bytearray(buf.getvalue())
    at = raw.rfind(b"PK\x01\x02")
    while at != -1:
        length = struct.unpack("<H", bytes(raw[at + 28:at + 30]))[0]
        if bytes(raw[at + 46:at + 46 + length]) == b"B.pdf":
            raw[at + 24:at + 28] = struct.pack("<I", 600 * 1024 * 1024)
            break
        at = raw.rfind(b"PK\x01\x02", 0, at)
    else:
        raise AssertionError("could not find B.pdf in the central directory")

    box = vdi2770.read_container(bytes(raw), "forged.zip")
    said = " ".join(d.detail or "" for d in box.rejected.values())
    assert "629145600" in said, said
    assert "says" in said or "claims" in said, (
        f"a size the archive only claims is stated as fact: {said}")
