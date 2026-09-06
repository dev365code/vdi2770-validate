"""`MAX_STREAMS` is 512 and the scan stopped at 257.

The marker the scan looks for is `stream` followed by an end of line, and
`endstream` ends in exactly that. So every real stream in an ordinary PDF
matched twice — once where it opens and once where it closes — and the budget
that says 512 was spent after 256 streams. Measured, not reasoned: a synthetic
PDF with 256 streams scans to the end and one with 257 comes back cut short.

That is not a number nobody reaches. The largest PDF in this repository's
corpus holds eleven streams, but a handover document is a manual, and the
finding a reader gets when the scan gives up is `P3` — *this scan found no
PDF/A claim* — about a file that was inside the published budget all along.

The other half was waste, in places rather than in time: every `endstream` cost
a slice and a `decompressobj` whose `decompress` then raised on the two-byte
header. Half the budget's places, and a small fraction of its work, because
that failure is immediate.

Fixed by refusing the match where the three bytes `end` precede it. Not "where
a letter precedes it": this scan runs over compressed bodies as well as over
syntax, and the broader rule dropped the marker after any blob whose last byte
happened to be a letter — which the reader's own budget suite caught.

The filter sits outside the pattern on purpose, and the marker budget beside
`MAX_STREAMS` exists because the filter sits there. Both have their own tests
below and their own reasons, which are not the same reason.
"""

import zlib

import pytest

from vdi2770 import pdfread
from vdi2770.pdfread import MAX_STREAMS


def a_pdf_with(streams: int, per_stream: bytes = None) -> bytes:
    """A PDF carrying `streams` real streams and no PDF/A claim.

    No claim on purpose: `_read` only reports where the scan stopped when it
    found nothing, which is the state this file is about.
    """
    body = per_stream if per_stream is not None else zlib.compress(b"a page\n")
    out = [b"%PDF-1.7\n", b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"]
    for i in range(2, streams + 2):
        out.append(b"%d 0 obj\n<< /Length %d /Filter /FlateDecode >>\nstream\n"
                   % (i, len(body)))
        out.append(body)
        out.append(b"\nendstream\nendobj\n")
    out.append(b"trailer\n<< /Size 1 >>\n%%EOF\n")
    return b"".join(out)


def cut_reason(data: bytes):
    return pdfread._read(data, None)[1]


def test_one_stream_offers_the_scan_one_place_to_start():
    """The defect itself, where it lives. `endstream` ends in `stream`, so the
    marker matched twice per stream and the budget was spent at half its
    published size."""
    one = b"1 0 obj\n<< /Length 5 >>\nstream\nHELLO\nendstream\nendobj\n"
    assert list(pdfread._stream_starts(one)) == [one.index(b"HELLO")], (
        "the scan starts reading where a stream ends as well as where one "
        "begins, so every stream costs two of the budget's places")


def test_a_stream_at_the_very_start_of_a_file_still_counts():
    """The filter looks at the byte before the match, and at offset zero there
    is none. Dropping the first stream of a file would be a quieter defect than
    the one being fixed."""
    assert list(pdfread._stream_starts(b"stream\nx\nendstream\n")) == [7]


def test_a_marker_after_some_other_letter_is_still_a_stream():
    """The filter names `endstream`, not "a letter before it".

    This scan runs over compressed bodies as well as over syntax, and a blob
    whose last byte is a letter would have had the marker after it dropped by
    the broader rule. The reader's budget suite found exactly that: its fixture
    abuts each stream against the previous one's adler32.
    """
    assert list(pdfread._stream_starts(b"Xstream\nbody")) == [8]
    assert list(pdfread._stream_starts(b"send\nstream\nbody")) == [12]
    assert list(pdfread._stream_starts(b"endstream\nbody")) == []


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
def test_both_line_endings_still_count(eol):
    assert len(list(pdfread._stream_starts(b">>" + eol + b"stream" + eol))) == 1


def test_the_marker_stays_a_bare_literal():
    """A load-bearing performance decision that reads like an oversight.

    Filtering `endstream` out *in the pattern* is the obvious move and it is
    the wrong one: a leading lookbehind, or a leading character class, throws
    away CPython's literal prefilter and the scan walks the file byte by byte.
    Measured over one 198 MB PDF, 0.06s as a plain literal against 4.2s either
    other way — seventy times, on the reader's untrusted-input path, for a
    filter that costs one byte test per match where it is now.

    Asserted rather than timed, because a timing test on a shared machine
    fails for reasons that have nothing to do with this.
    """
    assert pdfread._STREAM.pattern.startswith(b"stream"), (
        f"{pdfread._STREAM.pattern!r} no longer begins with the literal; if the "
        f"`endstream` filter moved back into the pattern, re-measure before "
        f"keeping it")


def test_a_file_inside_the_published_budget_is_read_to_the_end():
    """The reader's README names this budget among the ones it says a caller can
    read for themselves, so whatever it holds is what a file is entitled to
    spend. The README names it and does not print its value, which is why this
    reads the constant rather than a number."""
    assert cut_reason(a_pdf_with(MAX_STREAMS - 2)) is None


def test_the_scan_stops_where_the_budget_says_and_not_at_half_of_it():
    """Both sides of the boundary, because a ceiling nobody has seen hold is a
    ceiling nobody knows the height of."""
    assert cut_reason(a_pdf_with(MAX_STREAMS)) is None
    assert cut_reason(a_pdf_with(MAX_STREAMS + 1)) == "streams"


def test_the_budget_is_not_spent_on_closing_brackets():
    """The consequence stated as work rather than as a count: a file of this
    many streams used to spend the whole budget and stop, and now finishes."""
    half_and_one = MAX_STREAMS // 2 + 1
    assert cut_reason(a_pdf_with(half_and_one)) is None, (
        f"{half_and_one} streams is well inside a budget of {MAX_STREAMS} and "
        f"the scan gave up: each stream is being counted twice")


def test_markers_the_filter_rejects_still_cost_something():
    """The filter was put in front of the counter, and that removed the ceiling.

    Only yielded positions reach the caller's `seen`, so a member whose markers
    are *all* rejected never advances it and the caller's `seen >= MAX_STREAMS`
    never fires. The scan then walks every match in the file. Measured on 198 MB
    of `endstream\\n`: the old code stopped at marker 512 in no measurable time
    and this walked all 19.8 million of them.

    That shape is free to build — `endstream\\n` compresses to almost nothing —
    so it arrives as a small upload. Two budgets now: one on the streams that
    are opened, which is what `MAX_STREAMS` has always claimed to be, and one on
    the places looked at, which is what actually bounds the walk.
    """
    from vdi2770.pdfread import MAX_STREAM_MARKERS

    data = b"%PDF-1.7\n" + b"endstream\n" * (MAX_STREAM_MARKERS * 4)
    assert list(pdfread._stream_starts(data)) == [], "these are all closings"

    cut = [None]
    consumed = sum(1 for _ in pdfread._stream_starts(data, cut))
    assert consumed == 0
    assert cut[0] == "streams", (
        "the scan gave up on this file and reported nothing, so the report says "
        "it read to the end of a file it abandoned")


def test_the_places_looked_at_are_bounded_even_when_none_of_them_count():
    """Proved by putting a real stream where only an unbounded walk would find
    it. No timing and nothing patched: if the marker budget holds, the scan
    never reaches the one position it would have yielded.
    """
    from vdi2770.pdfread import MAX_STREAM_MARKERS

    beyond = b"endstream\n" * (MAX_STREAM_MARKERS + 5) + b">>\nstream\nBODY"
    assert list(pdfread._stream_starts(beyond)) == [], (
        "the scan walked past its budget of places and found the stream that "
        "was planted beyond it")

    # And it does find that stream when it is inside the budget, so the
    # assertion above is about the ceiling and not about the planted bytes.
    within = b"endstream\n" * 4 + b">>\nstream\nBODY"
    assert list(pdfread._stream_starts(within)) == [len(within) - 4]


def test_a_conforming_file_still_gets_the_whole_stream_budget():
    """The marker budget must not be what stops an ordinary file. A conforming
    PDF closes every stream it opens, so it needs two markers per stream — and
    one more, so that a file with too many streams trips the stream budget and
    gets that sentence rather than this one."""
    from vdi2770.pdfread import MAX_STREAM_MARKERS

    assert MAX_STREAM_MARKERS == 2 * MAX_STREAMS + 1
    assert cut_reason(a_pdf_with(MAX_STREAMS)) is None
    assert cut_reason(a_pdf_with(MAX_STREAMS + 1)) == "streams"
