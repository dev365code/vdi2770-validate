"""Who declares an identifier is answered once for the delivery, not once per
document that asks.

`M11`/`M12` ask, for each `DocumentRelationship`, whether any *other* document
declares the identifier it names. The first spelling built the answer as a set
per referring document -- every identifier in the delivery, minus that
document's own -- and memoised it in a dict that is never emptied. So a delivery
with R referring documents and T identifiers built R sets of T entries and held
all of them at once: cost R*T in time and in memory, on a conforming delivery,
with no budget watching that axis. `MAX_CONTAINERS` bounds R and
`MAX_TOTAL_ELEMENTS` bounds elements; nothing bounds their product.

Measured before the repair, with `_delivery` below -- this file's own harness:
359 MB peak at R=400, T=4,000 and 790 MB at R=400, T=8,000 -- the median of three
runs, since the first run in a process also carries its imports and reads 373 --
from two archives of 483 KB whose exact size varies from build to build. (The figures first written here, 403 and
834 MB from "the same 43.6 MB archive, sixty-eight bytes apart", came from a
different script that also packed a PDF into every container; they could not be
reproduced from anything in this repository, which is the one thing a figure in
a test has to allow.) And exhaustion here does not merely take time: the runner
turns an exception out of a check into `X5`, so a clean delivery comes back as
an error against the sender.

The count is the thing to assert, not the clock: a stopwatch here has failed
under load before and said nothing about the bound it was defending. Every
identity the rule builds passes through `_identity`, so counting those calls
measures exactly the work that grew, on any machine, deterministically.
"""
import io
import re
import zipfile

import pytest
from vdi2770_validate.runner import check_file

from conftest import CLEAN_DOCUMENTATION
from vdi2770.validate.rules import delivery

DOC = zipfile.ZipFile(CLEAN_DOCUMENTATION)
MAIN = DOC.read("VDI2770_Main.xml").decode("utf-8")
INNER = zipfile.ZipFile(io.BytesIO(DOC.read("documentcontainer.zip")))
META = INNER.read("VDI2770_Metadata.xml").decode("utf-8")


def _ids(meta, ids):
    block = "".join(f'<DocumentId DomainId="BSP-OEM">{i}</DocumentId>' for i in ids)
    return re.sub(r'(<DocumentId\b[^>]*>[^<]*</DocumentId>\s*)+', block, meta, count=1)


def _refers_to(meta, target):
    # Inside `DocumentVersion`, before the first `DigitalFile`, which is where
    # the corpus's own main document puts it. Anywhere else is schema-invalid
    # and the delivery comes back full of `X2` instead of exercising this.
    rel = ('<DocumentRelationship Type="RefersTo">'
           f'<DocumentId DomainId="BSP-OEM">{target}</DocumentId>'
           '</DocumentRelationship>')
    return meta.replace("<DigitalFile", rel + "<DigitalFile", 1)


def _container(meta):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", meta)
    return buf.getvalue()


def _delivery(path, referrers, declared):
    """R documents that refer, and one that declares T identifiers."""
    entries = [("VDI2770_Main.xml", MAIN.encode()),
               ("farm.zip", _container(_ids(META, [f"FARM{i}" for i in range(declared)])))]
    for i in range(referrers):
        entries.append((f"ref{i}.zip",
                        _container(_refers_to(_ids(META, [f"DOC{i}"]), "FARM0"))))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
    path.write_bytes(buf.getvalue())
    return str(path)


def _identities_built(path, monkeypatch):
    made = []
    real = delivery._identity
    monkeypatch.setattr(delivery, "_identity",
                        lambda i: (made.append(1), real(i))[1])
    check_file(path)
    return len(made)


@pytest.mark.parametrize("referrers,declared", [(60, 300), (120, 300)])
def test_the_delivery_is_not_read_once_per_document_that_asks(
        tmp_path, monkeypatch, referrers, declared):
    """Linear in R + T, not in R * T."""
    path = _delivery(tmp_path / "d.zip", referrers, declared)
    built = _identities_built(path, monkeypatch)
    # Generous: the rule builds an identity for each declaration and each
    # relationship target, a few times over. What it must not do is build one
    # per (referring document, identifier) pair, which is 18,000 at the first
    # size here and 36,000 at the second.
    assert built <= 8 * (referrers + declared), (
        f"{referrers} referring documents and {declared} identifiers built "
        f"{built} identities; that is the delivery re-read once per document "
        f"that asks, which is R*T = {referrers * declared}")


def test_doubling_the_documents_that_ask_does_not_double_the_reading(
        tmp_path, monkeypatch):
    """The shape, stated as growth, so a constant factor cannot hide it."""
    one = _identities_built(_delivery(tmp_path / "a.zip", 40, 400), monkeypatch)
    two = _identities_built(_delivery(tmp_path / "b.zip", 80, 400), monkeypatch)
    assert two <= one * 1.5, (
        f"doubling the referring documents took the work from {one} to {two}; "
        f"the identifiers they ask about did not change")


def test_an_identifier_two_documents_declare_is_still_declared_by_the_other(
        tmp_path):
    """The reason this counts instead of subtracting a set.

    A relationship naming the identifier of the document it sits in is dangling
    -- unless some *other* document declares it too. Build the answer as one
    set of every identity with the asking document's own removed, and an
    identifier that two documents declare disappears with the first of them:
    the delivery is told it carries nothing by that name while a second
    document is sitting there declaring it. Counting the documents and taking
    your own out of the count is the same question, asked so that repeats
    survive it.
    """
    shared = "SHARED-ID"
    entries = [("VDI2770_Main.xml", MAIN.encode())]
    # The document that both declares the identifier and refers to it.
    entries.append(("asks.zip", _container(_refers_to(_ids(META, [shared]), shared))))
    # And another that declares the very same one.
    entries.append(("also.zip", _container(_ids(META, [shared]))))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
    path = tmp_path / "shared.zip"
    path.write_bytes(buf.getvalue())

    report = check_file(str(path))
    # Only about this identifier: the sample main document carries a
    # relationship of its own, to a document these fixtures do not build, and
    # that one is correctly dangling here.
    dangling = [f for f in report.findings
                if f.rule.id in ("M11", "M12") and shared in (f.detail or "")]
    assert not dangling, (
        f"two documents declare {shared!r} and the relationship naming it was "
        f"still called dangling: {[f.detail for f in dangling]}")


def _peak_bytes(path, runs=3):
    """Median peak allocation for one run over `path`. Allocation, not time:
    what must not happen here is that a *set per referring document* gets
    built and kept, and that is a thing `tracemalloc` counts exactly."""
    import statistics
    import tracemalloc

    seen = []
    for _ in range(runs):
        tracemalloc.start()
        check_file(path)
        seen.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    return statistics.median(seen)


def test_the_documents_that_ask_do_not_multiply_what_is_held(tmp_path):
    """Counting `_identity` says each identity is built once. It does not say
    they are not then collected into one set per document that asks.

    Normalising the identities up front and *then* restoring the old shape --
    one set of the delivery's identities per referring document, all held at
    once -- leaves the call counter untouched (422 calls against a bound of
    2,880, exactly what the repaired code makes) and puts the memory back: 413
    MB where the repair holds 17. The counter cannot see it, because the calls
    really are linear; what is quadratic is what is kept.

    So the other half is measured. Four times the documents that ask, with the
    same identifiers to ask about, should not cost four times the allocation.
    Measured on this tree: about 1.4x. A set per document: about 3x.

    What this does not catch: a leaner structure per document -- a list rather
    than a set -- stays under the threshold, and so does work that is repeated
    without being kept. Both are cost the delivery pays and this does not see.
    """
    small = _peak_bytes(_delivery(tmp_path / "small.zip", 50, 1500))
    large = _peak_bytes(_delivery(tmp_path / "large.zip", 200, 1500))
    assert large < small * 2.5, (
        f"four times the referring documents cost {large / small:.1f}x the "
        f"allocation ({small:,} -> {large:,} bytes), and the identifiers they "
        f"ask about did not change: the delivery is being held once per "
        f"document that asks")


def test_the_domain_is_compared_without_ascii_case(tmp_path):
    """`_identity` folds case on both halves, and only one half was held.

    `_identity`'s own docstring says both halves matter and both are easy to get
    wrong *in the expensive direction*. The id half has a test. The domain half
    did not, so folding could be dropped there and every test in this repository
    stayed green -- while a delivery that declares `BSP-OEM` and refers to
    `bsp-oem` was told the document it carries is not there. That is an error
    raised against a sender who did nothing wrong.

    This holds ASCII case only. It was first named for comparing "the way the
    reference compares", and that is not what it holds: Python's `casefold()`
    and Java's `equalsIgnoreCase` disagree outside ASCII -- `MASSBLATT` and
    `Maßblatt` are equal here and not there, `İD` and `id` the other way round.
    Whether to follow the reference on those is a change in what the rule
    decides, and is not made here.
    """
    declared = _ids(META, ["SHARED"]).replace('DomainId="BSP-OEM"',
                                              'DomainId="BSP-OEM"')
    asking = _refers_to(_ids(META, ["ASKER"]), "SHARED").replace(
        'DomainId="BSP-OEM"', 'DomainId="bsp-oem"')
    entries = [("VDI2770_Main.xml", MAIN.encode()),
               ("has.zip", _container(declared)),
               ("asks.zip", _container(asking))]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
    path = tmp_path / "cased.zip"
    path.write_bytes(buf.getvalue())

    dangling = [f for f in check_file(str(path)).findings
                if f.rule.id in ("M11", "M12") and "SHARED" in (f.detail or "")]
    assert not dangling, (
        "a delivery declaring `SHARED@BSP-OEM` and referring to it as "
        f"`SHARED@bsp-oem` was told it carries no such document: "
        f"{[f.detail for f in dangling]}")
