"""The schema check has no budget, and it is quadratic.

`docs/scope.md` sells the budget model as bounding CPU — "a container at the
2 GiB ceiling costs roughly two seconds and the whole-read ceiling of 4 GiB costs
about four". Nothing in that model reaches this path. Measured: 410 KB of
metadata with 16,000 schema errors cost **29 s**, doubling the input quadrupling
the time, and `MAX_METADATA_BYTES` (16 MiB) admits about forty times that.

Two things cost. `xmlschema.iter_errors` is super-linear on its own, and
`_resolve` rebuilt the whole sibling list once per error to index one of them —
38 % of the 29 s. Fixing `_resolve` halves a curve that is still a curve, so the
work itself is bounded and the report says it stopped.
"""
import io
import re
import time
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770 import xmlread
from vdi2770_validate import xsdvalidate
from vdi2770_validate.runner import check_bytes

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = SRC.read("VDI2770_Metadata.xml").decode()
ONE = re.search(r"<DocumentId[^>]*>[^<]*</DocumentId>", META).group(0)


def metadata_with(n):
    return META.replace(ONE, ONE + "<DocumentId>x</DocumentId>" * n, 1).encode()


def container_with(n):
    buf = io.BytesIO()
    body = metadata_with(n)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name in SRC.namelist():
            z.writestr(name, body if name == "VDI2770_Metadata.xml" else SRC.read(name))
    return buf.getvalue()


def test_a_document_full_of_schema_errors_does_not_cost_minutes():
    body = metadata_with(16_000)
    started = time.monotonic()
    xsdvalidate.validate(body, xmlread.parse(body))
    elapsed = time.monotonic() - started
    assert elapsed < 5, f"{len(body) / 1024:.0f} KB of metadata cost {elapsed:.1f}s"


def test_the_cost_stops_growing_once_the_budget_is_spent():
    """Flat, not merely smaller — which means comparing the points rather than
    holding each under its own ceiling.

    The parametrised version of this asserted `elapsed < 5` three times with no
    comparison between them, so two of its three cases could not fail on the
    axis their name described, and the third was the same input as the test
    above."""
    # Counted, not timed. This asserted on `time.monotonic()` and flaked on a
    # loaded machine — and a wall-clock ratio is a poor way to ask this anyway,
    # because it measures the machine as much as the code. What the budget
    # actually bounds is how many errors are rendered, and rendering is what the
    # cost was quadratic in.
    rendered = {}
    for n in (2_000, 8_000, 32_000):
        body = metadata_with(n)
        rendered[n] = len(xsdvalidate.validate(body, xmlread.parse(body)))

    assert len(set(rendered.values())) == 1, (
        f"the budget is supposed to be the ceiling, and the work still grows "
        f"with the document: {rendered}")
    # The budget plus the one finding that says it was spent — a truncated check
    # that reports nothing about being truncated is the failure the test below
    # this one is about.
    assert max(rendered.values()) == xsdvalidate.MAX_SCHEMA_ERRORS + 1, (
        f"{rendered} against a budget of {xsdvalidate.MAX_SCHEMA_ERRORS}")


def test_it_says_that_it_stopped():
    """A truncated check that reports nothing about being truncated is the
    quieter-verdict failure again: the reader would read the count as the
    document's error count."""
    rep = check_bytes(container_with(16_000), "many.zip")
    fired = {f.rule.id for f in rep.findings}
    assert "X4" in fired, f"it stopped checking and did not say so: {sorted(fired)}"
    assert not rep.clean


def test_a_document_under_the_budget_is_still_checked_in_full():
    rep = check_bytes(container_with(5), "few.zip")
    x2 = [f for f in rep.findings if f.rule.id == "X2"]
    assert len(x2) == 5, f"a small document must be reported completely: {len(x2)}"
    assert "X4" not in {f.rule.id for f in rep.findings}


def test_a_schema_complaint_carries_the_line_it_is_about():
    """The whole reason `xsdvalidate.py` walks our own tree: xmlschema reports an
    XPath and ElementTree threw the lines away. `_resolve` returning `None` for
    everything — no complaint ever gets a position — left the suite green."""
    from conftest import FIXTURES
    from vdi2770_validate.runner import check_file

    x2 = [f for f in check_file(str(FIXTURES / "x2-schema-violation.zip")).findings
          if f.rule.id == "X2"]
    assert x2, "the fixture no longer produces a schema violation"
    assert any(f.where.line for f in x2), (
        "no schema complaint carries a line; the tree walk is doing nothing")


def test_an_index_of_zero_is_not_the_last_child():
    """`i = int(idx) - 1` makes `[0]` into `-1`, which passes an upper-bound-only
    test and indexes the *last* sibling — a complaint with a confidently wrong
    line. XPath is 1-based so `[0]` should never arrive, which is exactly why
    nobody would notice."""
    from vdi2770 import parse_xml
    from vdi2770_validate.xsdvalidate import _resolve

    tree = parse_xml(b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'>"
                     b"<A>first</A><A>second</A></Document>")
    assert _resolve(tree, "/Document/A[1]").text == "first"
    assert _resolve(tree, "/Document/A[2]").text == "second"
    assert _resolve(tree, "/Document/A[0]") is None, "[0] resolved to a sibling"


def test_resolving_many_complaints_over_one_parent_is_not_quadratic():
    """`_resolve` rebuilt the whole sibling list once per error to index one of
    them — 38 % of the 29 s this file is about. The budget alone hides that:
    remove the cache and the total stays under the ceiling while the cost per
    error quadruples."""
    from vdi2770_validate.xsdvalidate import _resolve

    body = metadata_with(4_000)
    tree = xmlread.parse(body)
    path = "/Document/DocumentId[%d]"        # the shape xmlschema actually reports
    assert _resolve(tree, path % 2) is not None, "the probe path does not resolve"

    shared: dict = {}
    started = time.monotonic()
    for i in range(1, 2_001):
        _resolve(tree, path % i, shared)
    cached = time.monotonic() - started

    started = time.monotonic()
    for i in range(1, 2_001):
        _resolve(tree, path % i)
    uncached = time.monotonic() - started

    # And `validate` has to be the caller that passes it. Measuring `_resolve`
    # alone leaves the wiring free to drop the cache, which is what a mutation
    # found: the total stays under the budget's ceiling either way.
    seen = {}
    real = xsdvalidate._resolve

    def watched(root, path, kids_of=None):
        seen["cache"] = kids_of
        return real(root, path, kids_of)

    xsdvalidate._resolve = watched
    try:
        xsdvalidate.validate(body, tree)
    finally:
        xsdvalidate._resolve = real
    assert isinstance(seen.get("cache"), dict), (
        "validate calls _resolve without the cache, so every complaint rebuilds "
        "the sibling list")

    assert uncached > cached * 3, (
        f"the cache saved nothing: {cached:.3f}s vs {uncached:.3f}s — either it is "
        f"gone or this input no longer has many siblings under one parent")
