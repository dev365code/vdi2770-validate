"""The tree budgets bound bytes and archives. They did not bound the objects
built out of them.

`MAX_CONTAINERS` caps how many archives one read opens; `MAX_TOTAL_METADATA_BYTES`
and `MAX_TOTAL_DECOMPRESSED` cap what it inflates. None of them caps the number
of `Member` and `Defect` records retained — and one is built per entry in every
archive's directory. At the caps that is 10,000 x 1,000 = ten million records,
measured at roughly 460 bytes each: about 4.6 GB, from an input small enough to
email. Measured at one fiftieth of the cap: a 2.34 MB archive produced 320,000
defects and 147 MB, growing linearly.

The largest real container in this repository's corpus lists **twenty** members.
"""
import io
import zipfile

import pytest

from vdi2770 import zipread


def pack(members, compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


META = b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'/>"


def a_wide_tree(kids, members_each, name=lambda i: f"/abs{i}.txt"):
    """Members with unsafe names, so each one costs a `Defect` as well."""
    inner = pack({"VDI2770_Metadata.xml": META,
                  **{name(i): b"" for i in range(members_each)}})
    return pack({"VDI2770_Main.xml": META,
                 **{f"c{i:04d}.zip": inner for i in range(kids)}})


def records(box):
    return sum(len(c.members) + len(c.defects) + len(c.rejected) for c in box.walk())


def test_the_records_one_read_retains_are_bounded(monkeypatch):
    monkeypatch.setattr(zipread, "MAX_TOTAL_MEMBERS", 2_000)
    box = zipread.read(a_wide_tree(kids=40, members_each=1_000), "wide.zip")
    kept = records(box)
    assert kept < 20_000, f"the budget was 2,000 entries and the read kept {kept:,} records"
    assert any(d.kind == "member-budget-exhausted" for c in box.walk() for d in c.defects), (
        "it stopped and said nothing")


def test_stopping_is_reported_as_this_tool_stopping():
    """Not as a verdict on the archive. Whoever sent it may have sent something
    fine; we declined to hold it all."""
    from vdi2770 import DEFECT_KINDS
    assert "member-budget-exhausted" in DEFECT_KINDS


def test_an_ordinary_tree_is_nowhere_near_the_budget():
    """The largest real container lists twenty members. A budget that a real
    delivery could reach is not a budget, it is a bug waiting for a customer."""
    box = zipread.read(a_wide_tree(kids=3, members_each=5), "small.zip")
    assert not any(d.kind == "member-budget-exhausted"
                   for c in box.walk() for d in c.defects)
    assert len(box.children) == 3, "an ordinary tree must still be opened in full"


@pytest.mark.parametrize("kids,members_each", [(20, 500), (40, 500), (40, 1000)])
def test_growth_stays_bounded_as_the_input_grows(kids, members_each, monkeypatch):
    """The shape that made this a finding was linear growth with no ceiling."""
    monkeypatch.setattr(zipread, "MAX_TOTAL_MEMBERS", 5_000)
    box = zipread.read(a_wide_tree(kids, members_each), "x.zip")
    assert records(box) < 40_000, records(box)


# --- the XML tree, which had no bound at all -------------------------------
#
# The two budgets above bound the archives and the bytes taken out of them. The
# tree built *from* those bytes had no limit of any kind, and the expansion from
# one to the other is what an attacker gets to choose.
#
# A metadata member of 7.98 MB -- just under `MIN_SUSPICIOUS_BYTES`, so the
# compression-ratio guard never looks at it, and well under the 16 MB
# `MAX_METADATA_BYTES` -- holding 1.14 million nested elements compresses to a
# 115 KB archive and drives this process to **952 MB**, measured. The reader's
# own first paragraph says an untrusted archive does not get to decide how much
# memory we spend.
#
# The largest metadata file in this repository's corpus has **53 elements** and
# nests **five** deep.

def test_a_metadata_file_cannot_choose_how_many_nodes_we_build():
    from vdi2770 import xmlread

    body = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            + b"<a/>" * (xmlread.MAX_ELEMENTS + 2)
            + b"</Document>")
    with pytest.raises(xmlread.XmlTooLarge) as e:
        xmlread.parse(body)
    assert "element" in str(e.value).lower(), str(e.value)


def test_depth_alone_is_not_expensive_once_the_count_is_bounded():
    """The obvious second axis, measured rather than assumed.

    A depth limit was written and then removed. `find_all` and `find` read one
    level, `domain.build` never recurses, and the cost of a node is the same
    whether it is the hundredth sibling or the hundredth descendant -- so the
    count bounds both. A depth limit would also have taken a real limit away
    from the caller: the schema checker gives up on a deep document and says so,
    and refusing it here first replaces that with a limit invented to have one.
    """
    from vdi2770 import xmlread
    from vdi2770.domain import build
    from vdi2770.model import Location

    d = 20_000
    body = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            + b"<a>" * d + b"</a>" * d
            + b"</Document>")
    root = xmlread.parse(body)          # neither a RecursionError nor a refusal
    assert build(root, Location(container="x")) is not None


def test_the_bound_is_generous_next_to_anything_real():
    """A limit tight enough to refuse a real handover document is a bug of its
    own. The corpus's largest metadata file has 53 elements."""
    from vdi2770 import xmlread

    assert xmlread.MAX_ELEMENTS >= 50_000, xmlread.MAX_ELEMENTS


def test_the_text_a_document_carries_is_bounded_too():
    """The element cap bounds the *nodes*. It says nothing about the text hung
    off them, and text is the other thing a document is made of.

    `&#120;` is one `CharacterDataHandler` callback and one transient string
    each. 1.3 million of them is a document of three elements — charged three
    against a budget of half a million — that costs **287 MB**, measured, from a
    4.2 KiB archive. The quadratic-time defect this handler already carries a
    comment about is genuinely fixed; the allocation was never bounded by
    anything.

    The largest metadata file in this repository's corpus carries about 1 KB of
    text in total.
    """
    from vdi2770 import xmlread

    body = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            b"<a>" + b"&#120;" * (xmlread.MAX_TEXT_PIECES + 1000) + b"</a>"
            b"</Document>")
    with pytest.raises(xmlread.XmlTooLarge) as e:
        xmlread.parse(body)
    assert "pieces" in str(e.value).lower(), str(e.value)


def test_the_text_bound_is_generous_next_to_anything_real():
    """A limit tight enough to refuse a real handover is its own defect. The
    corpus's largest metadata file arrives in a few hundred pieces."""
    from vdi2770 import xmlread

    assert xmlread.MAX_TEXT_PIECES >= 50_000, xmlread.MAX_TEXT_PIECES


def test_one_element_may_not_carry_unboundedly_many_attributes():
    """The third axis of this parse, and the one nobody was charging.

    Elements were bounded and text pieces were bounded; attributes were not.
    They are cheap to write -- `a="x"` is seven bytes -- and the schema check
    downstream is *quadratic* in how many sit on one element: 12,000 of them, in
    a 27 KiB archive, cost 13.6 seconds. The corpus's worst real element carries
    three.
    """
    from vdi2770 import xmlread

    body = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770" '
            + b" ".join(b'a%d="x"' % i
                        for i in range(xmlread.MAX_ATTRIBUTES_PER_ELEMENT + 1))
            + b"></Document>")
    with pytest.raises(xmlread.XmlTooLarge) as e:
        xmlread.parse(body)
    assert str(xmlread.MAX_ATTRIBUTES_PER_ELEMENT) in str(e.value)


def test_a_document_may_not_carry_unboundedly_many_attributes_in_total():
    """And the axis the per-element bound leaves open.

    A cap on one element still lets a sender put that many on each of thousands
    of elements; the quadratic becomes a linear cost multiplied by however many
    elements they care to write. Bounding one axis and calling the cost bounded
    is the mistake this reader has now made three times, so both are named.
    """
    from vdi2770 import xmlread

    per = 8
    elements = xmlread.MAX_ATTRIBUTES // per + 2
    one = b"<E " + b" ".join(b'a%d="x"' % i for i in range(per)) + b"/>"
    body = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            + one * elements + b"</Document>")
    with pytest.raises(xmlread.XmlTooLarge) as e:
        xmlread.parse(body)
    assert str(xmlread.MAX_ATTRIBUTES) in str(e.value)


def test_the_attribute_bounds_leave_a_real_document_far_below_them():
    """Both caps are enormous next to anything VDI 2770 describes.

    Measured over every metadata file in the corpus: the worst element carries
    three attributes and the worst document 51. A bound written to stop an
    attack must not be one a real delivery can reach, and these are two orders
    of magnitude away from the real worst.
    """
    from vdi2770 import xmlread

    assert xmlread.MAX_ATTRIBUTES_PER_ELEMENT >= 64
    assert xmlread.MAX_ATTRIBUTES >= 10_000
