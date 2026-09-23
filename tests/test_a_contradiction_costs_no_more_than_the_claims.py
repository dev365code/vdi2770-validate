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
import zipfile

import pytest
from vdi2770_validate.runner import check_bytes

from conftest import CORPUS
from vdi2770.validate.rules import delivery

SAMPLE = CORPUS / "container" / "documentcontainer.zip"
OPEN, CLOSE = "<ReferencedObject>", "</ReferencedObject>"


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
    schema-invalid input too. `tools/mutation_table.py` carries that shape.
    """
    made = []
    real = delivery._register
    monkeypatch.setattr(delivery, "_register",
                        lambda ref: (made.append(1), real(ref))[1])

    n = 600
    raw = container_declaring([("Type" if i % 2 else "Individual", "product type")
                               for i in range(n)])
    assert m13_of(raw), "the contradiction this measures is not being reported"
    # The pairwise version made n*(n-1)/2 -- 179,700 for this input. Anything
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
    kinds = ["Type", "Individual"]
    registers = [None, "product type", "serial number", "   "]
    claims = [(rng.choice(kinds), rng.choice(registers))
              for _ in range(rng.randint(2, 6))]

    def register(ref):
        return " ".join(str(ref or "").split()).casefold()

    def differ(a, b):
        left, right = register(a), register(b)
        return bool(left) and bool(right) and left != right

    # The sample container already declares its own object; this rule compares
    # per identifier, so the claims added here are the only ones under the id.
    expected_pairs = [(i, j) for i in range(len(claims)) for j in range(i + 1, len(claims))
                      if claims[i][0] != claims[j][0] and not differ(claims[i][1], claims[j][1])]
    expected_kinds = {claims[i][0] for pair in expected_pairs for i in pair}

    findings = m13_of(container_declaring(claims))
    if not expected_pairs:
        assert not findings, (
            f"no two of {claims} contradict each other, and it reported "
            f"{[f.detail for f in findings]}")
        return
    assert len(findings) == 1, f"{claims} drew {len(findings)} findings"
    detail = findings[0].detail or ""
    for kind in expected_kinds:
        assert kind in detail, f"{claims} contradicts as {sorted(expected_kinds)}: {detail}"


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
