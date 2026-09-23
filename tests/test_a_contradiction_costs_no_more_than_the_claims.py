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
        f"{len(made)} register normalisations for {n} claims; a scan that pairs "
        f"them makes on the order of n*n/2, and this is closer to that than to {n}")
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
    claims should cost about four times the allocation, and the pairing version
    costs about sixteen. (The exact ratio moves a little with what else ran in
    the process first: 3.6x in a fresh interpreter, nearer 4x inside the suite.)

    What this does not catch: pairs streamed through a generator. That is
    quadratic in time and flat in allocation, and it passes both this and the
    call counter above -- at 16,000 claims it takes seconds where the repair
    takes milliseconds. Catching it needs a measure of work done rather than
    of memory held, and there is not one here yet.
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


def _across_containers(tmp_path, kinds, identifier="SHARED"):
    """One document container per entry of `kinds`, all claiming the same
    identifier. An entry that is a tuple is several claims in one container.

    `container_declaring` puts every claim in a single container, so a test
    written on it can never see the container list grow -- which is how the
    first spelling of the test below passed against the very behaviour it was
    written to catch.
    """
    with zipfile.ZipFile(SAMPLE) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    meta = next(n for n in names if n.endswith("VDI2770_Metadata.xml"))
    text = data[meta].decode("utf-8")
    inner = []
    for i, kind in enumerate(kinds):
        claims = kind if isinstance(kind, tuple) else (kind,)
        one = text.replace(
            CLOSE, "".join(f'<ObjectId ObjectType="{k}">{identifier}</ObjectId>'
                           for k in claims) + CLOSE, 1)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z2:
            for n in names:
                z2.writestr(n, one.encode("utf-8") if n == meta else data[n])
        inner.append((f"doc{i:02d}.zip", buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as o:
        for n, d in inner:
            o.writestr(n, d)
    path = tmp_path / "across.zip"
    path.write_bytes(out.getvalue())
    return str(path)



def test_one_finding_does_not_grow_without_bound():
    """`MAX_LISTED_PER_RULE` bounds how many findings a rule may list. It does
    not bound how large one of them is, and `M13` emits one finding per
    identifier -- so the cap never engages while the sentence grows with the
    kinds the sender wrote. Measured before the bound: a 232 KB archive
    produced one finding whose detail was 8.1 million characters and a report
    of 8.2 MB, an amplification of thirty-five times, on the one axis the cap
    does not watch.

    The count stays exact; it is the listing that is bounded, the way every
    other list this report prints is bounded.
    """
    kinds = [f"Kind{i:04d}" for i in range(400)]
    raw = container_declaring([(k, None) for k in kinds])
    findings = m13_of(raw)
    assert len(findings) == 1, f"expected one finding, got {len(findings)}"
    detail = findings[0].detail or ""
    assert len(detail) < 600, (
        f"one finding's detail is {len(detail)} characters for {len(kinds)} "
        f"kinds; it grows with what the sender wrote")
    # And it still says how many there were, so the reader is not told less.
    assert str(len(kinds)) in detail or str(len(kinds) + 1) in detail, (
        f"the detail no longer says how many kinds were declared: {detail}")



def test_every_container_that_takes_part_is_counted(tmp_path):
    """No container that takes part may go missing without the report saying so.

    The first bound on this list was silent: seven of twelve containers
    appeared in no field of the report and nothing said there had been more.
    Listing every one in full fixed that and broke something worse (the list had
    no bound on its size). What the reader is owed is not every path but the
    truth about how many there were, so a count they can act on -- by searching
    the delivery for the identifier, ignoring case and surrounding spaces -- is
    what this holds.
    """
    from vdi2770_validate.runner import check_file

    n = 12
    # The first container claims the identifier twice, as two kinds: thirteen
    # claims in twelve containers, so counting claims reads 13, and a list built
    # from claims names the first container twice.
    kinds = [("Individual", "Type")] + ["Type" if i % 2 else "Individual"
                                        for i in range(1, n)]
    path = _across_containers(tmp_path, kinds)
    findings = [f for f in check_file(path).findings if f.rule.id == "M13"]
    assert len(findings) == 1, f"expected one finding, got {len(findings)}"
    detail = findings[0].detail or ""
    assert f"{n} containers in all" in detail, (
        f"{n} containers take part and the finding does not say so: {detail}")
    listed = re.search(r"in this delivery \(([^)]*)\)", detail).group(1).split(", ")
    assert all(re.fullmatch(r"\S+\.zip", p) for p in listed), (
        f"the container list carries something that is not a path: {listed}")
    assert len(listed) == len(set(listed)) == delivery.MOST_LISTED, (
        f"the finding says {delivery.MOST_LISTED} of them are here and lists {listed}")



def test_the_count_sits_outside_the_list_it_counts():
    """A marker inside a comma-separated run is read back as one of the items.

    The project's own way of reading this sentence is
    `is declared as (.+?) in this delivery`, and with the marker inside the run
    it returned `Kind04 -- 5 of 6 shown` as the name of a kind -- a value no
    sender wrote -- while the kind sorting after it vanished from the report.
    """
    kinds = [f"Kind{i:02d}" for i in range(6)]
    findings = m13_of(container_declaring([(k, None) for k in kinds]))
    named = re.search(r"is declared as (.+?) in this delivery",
                      findings[0].detail or "").group(1).split(", ")
    assert all(k in kinds or k == "Type" for k in named), (
        f"the parsed kinds contain something no document declared: {named}")
    assert str(len(kinds) + 1) in (findings[0].detail or ""), (
        "the finding no longer says how many kinds there were")



def _under_a_long_name(tmp_path, n, name_len):
    """`n` document containers inside one container whose name is `name_len`
    characters long, each claiming the same identifier as alternating kinds.

    A member name may be tens of thousands of characters long, and a container
    holding others repeats its own name in every one of their paths -- so the
    length of the list of paths is n times name_len, whatever MAX_CONTAINERS
    says about n."""
    import pathlib

    inner = io.BytesIO()
    src = pathlib.Path(_across_containers(tmp_path, ["Type" if i % 2 else "Individual"
                                                     for i in range(n)]))
    with zipfile.ZipFile(src) as z, zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as o:
        for name in z.namelist():
            o.writestr(name, z.read(name))
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", zipfile.ZIP_DEFLATED) as o:
        o.writestr("M" * name_len + ".zip", inner.getvalue())
    path = tmp_path / "long.zip"
    path.write_bytes(outer.getvalue())
    return str(path)


def test_a_long_name_is_not_repeated_once_per_container(tmp_path):
    """The list of containers is bounded by count *and* so by size.

    Naming every container in full, a long name on the container that holds
    them is paid for once in the archive and then printed once per child: this
    input made one finding 81,177 characters. Bounded to a few paths, the same
    input costs a few times the name, not forty -- 10,270 characters.
    """
    from vdi2770_validate.runner import check_file

    n, name_len = 40, 2000
    findings = [f for f in check_file(_under_a_long_name(tmp_path, n, name_len)).findings
                if f.rule.id == "M13"]
    assert len(findings) == 1, f"expected one finding, got {len(findings)}"
    detail = findings[0].detail or ""
    assert len(detail) < 8 * name_len, (
        f"one finding is {len(detail):,} characters for {n} containers under a "
        f"{name_len}-character name: the name is being repeated once per container")
    assert f"{n} containers in all" in detail, "the finding no longer says how many"
