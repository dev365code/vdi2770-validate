"""Finding the contradiction must not cost the square of the claims.

`M13` asks whether one identifier was filed as more than one kind of thing.
The first version answered it by building every pair:

    clash = [(a, b) for i, a in enumerate(claims) for b in claims[i + 1:] ...]

which is the square of the claims in time *and* in the list it materialises.
Nothing bounds that list. The reader's caps are on elements and bytes -- a
hundred thousand elements in one metadata file, sixteen mebibytes of it -- and
a hundred thousand `ObjectId` elements naming one identifier is a conforming
document a hundred kilobytes long. Measured before the repair: 109 KiB of
container, 8.3 seconds, and the curve rising with the square while the file
grew by one kilobyte.

That shape is the one `SECURITY.md` names among what 0.5.0 to 0.7.0 were spent
hardening away, so shipping a new one in the release that writes that sentence
is not on.

Two properties here, and the cost one does not read a clock. A wall-clock
assertion fails on a loaded machine and passes on a fast one, which makes it a
gate that reports the runner. Counting the comparisons reports the algorithm.
"""
import io
import random
import re
import zipfile

import pytest
from vdi2770_validate.runner import check_bytes

from conftest import CORPUS
from vdi2770.validate.rules import delivery

SAMPLE = CORPUS / "container" / "documentcontainer.zip"
OPEN, CLOSE = "<ReferencedObject>", "</ReferencedObject>"


#: The claim the sample container already makes about `BR-01`: a product
#: type. Every group these fixtures build contains it.
SAMPLE_CLAIM = ("Type", "product type")


def container_declaring(claims, identifier="BR-01"):
    """The clean sample, with `claims` extra `ObjectId` elements on its object.

    `claims` is a sequence of `(object_type, ref_type)`; `ref_type` of `None`
    leaves the attribute off, which is the case that matters -- a blank register
    matches every register, so it is the one a narrower reading would drop.
    """
    with zipfile.ZipFile(SAMPLE) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    meta = next(n for n in names if n.endswith("VDI2770_Metadata.xml"))
    text = data[meta].decode("utf-8")
    assert OPEN in text and CLOSE in text, "the sample no longer declares an object"
    added = "".join(
        "<ObjectId{ref} ObjectType=\"{kind}\">{ident}</ObjectId>".format(
            ref="" if ref is None else f' RefType="{ref}"',
            kind=kind, ident=identifier)
        for kind, ref in claims)
    text = text.replace(CLOSE, added + CLOSE, 1)
    data[meta] = text.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as o:
        for n in names:
            o.writestr(n, data[n])
    return out.getvalue()


def m13_of(raw):
    return [f for f in check_bytes(raw, "claims.zip").findings if f.rule.id == "M13"]


def test_the_comparisons_do_not_square_with_the_claims(monkeypatch):
    """The gate on the defect itself, counted rather than timed.

    The first spelling of this counted calls to `different_registers` -- and
    `contradicting` does not call it. It normalises through `_register` and
    compares the results, so the counter stayed at nought and the assertion
    read `0 <= 4800` on every input, for ever. It caught a literal revert to
    the previous implementation and nothing else: a pairwise scan spelling the
    register comparison inline passed it while costing 4x per doubling.
    A cost gate has to count something the code being measured actually runs.

    `_register` is that thing: `contradicting` normalises each claim's register
    exactly once, so the count is the number of claims. The bound is two-sided
    on purpose. Too many means the claims are being paired. **Too few means the
    normalisation was spelled inline** and this gate is measuring nothing again,
    which is the failure it replaces.

    What it still does not catch: keeping one `_register` per claim and then
    walking the *kinds* for each of them, which is quadratic only where the
    kinds grow with the claims -- reachable, because this rule runs on
    schema-invalid input too. Nothing in this repository carries that shape
    yet -- not this file and not the mutation table -- and that is the gap.
    """
    made = []
    real = delivery._register
    monkeypatch.setattr(delivery, "_register",
                        lambda ref: (made.append(1), real(ref))[1])

    n = 600
    raw = container_declaring([("Type" if i % 2 else "Individual", "product type")
                               for i in range(n)])
    assert m13_of(raw), "the contradiction this measures is not being reported"
    # The pairwise version made 180,600 `_register` calls for this input --
    # the pair count, n*(n-1)/2 = 179,700, is a different number, and the
    # gate reads calls. Anything
    # that walks the claims a constant number of times is far under the bound;
    # anything that pairs them is far over it, and the gap is three orders of
    # magnitude rather than a margin to argue about.
    assert len(made) <= 8 * n, (
        f"{len(made)} register normalisations for {n} claims; a pairwise scan "
        f"would make {n * (n - 1) // 2}, and this is closer to that than to {n}")
    assert len(made) >= n, (
        f"{len(made)} register normalisations for {n} claims, fewer than one "
        f"each: the register is being normalised somewhere this cannot see, so "
        f"this gate is no longer measuring the cost it names")


@pytest.mark.parametrize("seed", range(12))
def test_it_reports_exactly_what_a_pairwise_scan_would(seed):
    """Correctness, against the definition the slow version implemented.

    A faster answer that is a different answer is not a repair. The registers
    here include the blank one on purpose: `different_registers` is true only
    when *both* sides name a register and they differ, so a blank one matches
    everything and the relation is not an equivalence -- which is exactly the
    kind of relation a regrouping gets wrong.
    """
    rng = random.Random(seed)
    # Three kinds, not two. With two, "reports a kind that does not contradict"
    # cannot be expressed at all -- every kind in the group is one of the pair
    # that contradicts -- so a regrouping that named every claim it saw passed
    # this test while changing what the report said.
    kinds = ["Type", "Individual", "Zebra"]
    registers = [None, "product type", "serial number", "   "]
    claims = [(rng.choice(kinds), rng.choice(registers))
              for _ in range(rng.randint(2, 6))]

    def register(ref):
        return " ".join(str(ref or "").split()).casefold()

    def differ(a, b):
        left, right = register(a), register(b)
        return bool(left) and bool(right) and left != right

    # The sample declares `BR-01` itself, as a product type, and
    # `container_declaring` hangs these claims on *that* identifier -- so the
    # sample's own claim is in the group and the oracle has to count it. The
    # comment here used to say the added claims were the only ones under the
    # id, which was false, and two kinds could not show it: `Type` was the
    # sample's kind and also one of the two, so an oracle that dropped it
    # produced the same answer. A third kind made the omission visible.
    group = [SAMPLE_CLAIM] + list(claims)
    expected_pairs = [(i, j) for i in range(len(group)) for j in range(i + 1, len(group))
                      if group[i][0] != group[j][0] and not differ(group[i][1], group[j][1])]
    expected_kinds = {group[i][0] for pair in expected_pairs for i in pair}

    findings = m13_of(container_declaring(claims))
    if not expected_pairs:
        assert not findings, (
            f"no two of {claims} contradict each other, and it reported "
            f"{[f.detail for f in findings]}")
        return
    assert len(findings) == 1, f"{claims} drew {len(findings)} findings"
    detail = findings[0].detail or ""
    # The kinds it names, exactly -- not "each expected one appears somewhere".
    # A one-sided check cannot see an extra: reporting every claim in the group
    # rather than the ones that take part adds a kind that contradicts nothing,
    # and each expected kind is still in the string.
    named = re.search(r"is declared as (.+?) in this delivery", detail)
    assert named, f"the finding no longer says what it is declared as: {detail}"
    assert set(named.group(1).split(", ")) == expected_kinds, (
        f"{claims} contradicts as {sorted(expected_kinds)} and the finding "
        f"names {named.group(1)}")
    # The location is the first *participating* claim's, and this test does not
    # pin it: mapping a claim's index back to a line and column in the built
    # metadata needs machinery this file does not have. The kind set above
    # catches the regrouping that moved it -- that one named a third kind as
    # well -- but a change that moved the location and left the kinds alone
    # would still pass here. Written down rather than implied.
    assert findings[0].where is not None, "the finding points nowhere"


#: The register relation, as a table rather than as a sentence. Random shapes
#: are not enough here: twelve seeds of two-to-six claims never once produced
#: two stated *and different* registers with no blank beside them, which is the
#: single shape that tells "compare only where the registers allow it" apart
#: from "any other kind contradicts". A mutation that dropped the register test
#: altogether survived the random cases and dies on this one.
REGISTERS = [
    ("the same register contradicts", "serial number", "serial number", True),
    ("two stated registers that differ do not", "serial number", "article number", False),
    ("a missing register matches a stated one", "serial number", None, True),
    ("a blank register matches a stated one", "serial number", "   ", True),
    ("two missing registers match each other", None, None, True),
]


@pytest.mark.parametrize("why,left,right,contradicts",
                         REGISTERS, ids=[r[0] for r in REGISTERS])
def test_a_register_decides_whether_two_kinds_contradict(why, left, right, contradicts):
    """`different_registers` is true only where both sides name a register and
    the two differ -- so a blank one matches every register. An article number
    and a serial number may be spelled alike and are different things; a claim
    with no register named has not said they are."""
    findings = m13_of(container_declaring([("Type", left), ("Individual", right)]))
    assert bool(findings) == contradicts, (
        f"{why}: RefType {left!r} against {right!r} "
        f"{'drew nothing' if contradicts else 'drew ' + str([f.detail for f in findings])}")


@pytest.mark.parametrize("bystanders", [1, 2, 3])
def test_it_names_only_the_kinds_that_take_part(bystanders):
    """A kind in the group that contradicts nothing must not be named.

    Written by hand, because the random shapes above cannot reach it: in all
    twelve seeds every kind present takes part, so "reports a kind that
    contradicts nothing" never arises and a regrouping that named the whole
    group passed all of them.

    Parametrised over how many bystanders there are, because a single row
    pinned a single kind-count and nothing above it. The first spelling had one
    bystander -- three kinds in all -- and a regrouping that returned the whole
    group once there were *more than three* kinds sailed past it while doing
    exactly what this test is named for.

    The sample declares `BR-01` as a product type. A second claim on the same
    register contradicts it. Each further claim names a register of its own, so
    it contradicts nothing: `different_registers` is true only where both sides
    name a register and the two differ.
    """
    registers = ["serial number", "article number", "drawing number"]
    claims = [("Individual", "product type")]
    claims += [(f"Kind{i}", registers[i]) for i in range(bystanders)]
    findings = m13_of(container_declaring(claims))
    assert len(findings) == 1, f"expected one finding, got {len(findings)}"
    named = re.search(r"is declared as (.+?) in this delivery", findings[0].detail or "")
    assert named, f"the finding no longer says what it is declared as: {findings[0].detail}"
    assert set(named.group(1).split(", ")) == {"Type", "Individual"}, (
        f"with {bystanders} kind(s) naming a register nothing else names, only "
        f"Type and Individual contradict; the finding names {named.group(1)}")


def _peak_bytes(raw, runs=3):
    """Median peak allocation for one run over `raw`.

    Allocation, not the clock. A stopwatch here has failed under load before
    and said nothing about the bound it was defending; what this rule must not
    do is *build* something that grows with the square, and that is exactly
    what `tracemalloc` counts. The median of three keeps the first run's
    import traffic out of the answer.
    """
    import statistics
    import tracemalloc

    seen = []
    for _ in range(runs):
        tracemalloc.start()
        m13_of(raw)
        seen.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    return statistics.median(seen)


def test_the_work_does_not_square_with_the_claims():
    """Counting `_register` says the registers are normalised once. It does not
    say the claims are not then paired.

    Precomputing the registers and pairing afterwards calls `_register` exactly
    once per claim -- 4,003 for 4,000 claims, against a bound of 32,000 -- and
    is quadratic in everything that matters: 24 MB at n=1,000 and 376 MB at
    n=4,000, from a container that grows by a few kilobytes. The call counter
    cannot see it, because the calls really are linear; what is quadratic is
    the list of pairs.

    So the other half of the same claim is measured directly. Four times the
    claims should cost about four times the allocation. Measured on this tree:
    3.7x. The pairing version: 15.6x.
    """
    def claims(n):
        return container_declaring([("Type" if i % 2 else "Individual", "product type")
                                    for i in range(n)])

    small = _peak_bytes(claims(1000))
    large = _peak_bytes(claims(4000))
    assert large < small * 8, (
        f"four times the claims cost {large / small:.1f}x the allocation "
        f"({small:,} -> {large:,} bytes). Linear is about 4x and the square is "
        f"about 16x, so something here is being built for every pair")
