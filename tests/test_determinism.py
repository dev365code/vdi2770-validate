"""The same container must produce the same bytes, twice, and regardless of the
order its members happen to be stored in."""
import io
import re
import zipfile

from vdi2770_validate.model import MAX_LISTED_PER_RULE
from vdi2770_validate.runner import check_bytes, check_file

from conftest import CLEAN_DOCUMENT, CORPUS, FIXTURES
from vdi2770_validate import report as rendering


def test_two_runs_are_byte_identical():
    a = rendering.as_json(check_file(str(CLEAN_DOCUMENT)))
    b = rendering.as_json(check_file(str(CLEAN_DOCUMENT)))
    assert a == b


def test_member_order_does_not_change_the_verdict():
    """The subject has to produce many findings and they have to be compared as
    bytes.

    This ran on a container with exactly one finding and compared rule ids, so
    it evaluated `["P4"] == ["P4"]`: replacing `Report.sorted()` with
    `list(self.findings)` — removing the report's ordering entirely — left it
    passing. Rule ids also hide the thing most likely to move, which is the
    order of several findings of the *same* rule.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    # Undeclared inner archives, because `Z11` walks `container.members` and so
    # emits in the order the archive stores them. Plain files were not enough:
    # `F2` sorts its own set before yielding, so its findings come out in the
    # same order either way and the report's sort has nothing left to do.
    tiny = io.BytesIO()
    with zipfile.ZipFile(tiny, "w") as z:
        z.writestr("a.txt", b"x")
    extra = {f"beilage-{i:02d}.zip": tiny.getvalue() for i in range(5)}
    names = src.namelist()

    def built(order):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in order:
                z.writestr(n, extra[n] if n in extra else src.read(n))
        return buf.getvalue()

    every = names + sorted(extra)
    a = check_bytes(built(every), "x.zip")
    b = check_bytes(built(list(reversed(every))), "x.zip")
    # The premise, asserted rather than hoped for: several findings of one rule,
    # emitted in archive order, so reversing the archive really does reverse
    # them before the report sorts.
    emitted = [f.where.member for f in a.findings if f.rule.id == "Z11"]
    reversed_emission = [f.where.member for f in b.findings if f.rule.id == "Z11"]
    assert len(emitted) >= 5, f"nothing here would reorder: {emitted}"
    assert emitted == list(reversed(reversed_emission)), (
        f"the two archives did not emit in opposite orders: {emitted} / {reversed_emission}")
    assert rendering.as_json(a) == rendering.as_json(b)


def test_the_hash_seed_does_not_reach_the_output(tmp_path):
    """Both tests above run in one process, where set iteration order is fixed for
    the life of that process — so neither can see a set leaking into the report.

    Several rules build sets (present, declared, folders, namespace prefixes) and
    sort before emitting. This runs the tool in fresh interpreters with different
    seeds and compares bytes, which is the only way to find the one that forgot.
    """
    import json
    import os
    import subprocess
    import sys

    from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION, FIXTURES, ROOT

    # One container has to hold *several* of whatever a set might reorder,
    # or the seed has nothing to change: with one undeclared file, an unsorted
    # set of one iterates the same way every time. Removing `sorted()` from F2
    # walked straight through the first version of this test for exactly that
    # reason. Eight is enough for the orders to differ between seeds.
    #
    # Eight was also not enough once the report grew a listing cap. Under the
    # cap the *final* sort no longer hides an unsorted set: it decides the order
    # of what is printed, but the set decides which hundred survive to be
    # printed at all. Removing `sorted()` from F2 passed every test in this file
    # until this container held more than MAX_LISTED_PER_RULE of them.
    crowded = tmp_path / "many_undeclared.zip"
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in src.namelist():
            z.writestr(n, src.read(n))
        for i in range(MAX_LISTED_PER_RULE * 2):
            z.writestr(f"anlage-{i:03d}.txt", b"x")
    crowded.write_bytes(buf.getvalue())

    # Z9 emits one finding per container and names the first five folders in its
    # detail, so a set leaks into the output without the listing cap being
    # anywhere near it. No fixture held enough folders for the order to differ.
    foldered = tmp_path / "many_folders.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in src.namelist():
            z.writestr(n, src.read(n))
        for i in range(12):
            z.writestr(f"ordner-{i:02d}/blatt.txt", b"x")
    foldered.write_bytes(buf.getvalue())

    targets = [str(crowded), str(foldered), str(CLEAN_DOCUMENT), str(CLEAN_DOCUMENTATION)]
    targets += [str(p) for p in sorted(FIXTURES.glob("*.zip"))[:6]]
    assert len(targets) >= 7, targets

    script = (
        "import json,sys;"
        "from vdi2770_validate.runner import check_file;"
        "from vdi2770_validate import report as r;"
        "print(json.dumps([r.as_json(check_file(p)) for p in sys.argv[1:]]))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")])

    outputs = []
    for seed in ("0", "524287"):
        env["PYTHONHASHSEED"] = seed
        done = subprocess.run([sys.executable, "-c", script, *targets],
                              capture_output=True, text=True, env=env)
        assert done.returncode == 0, done.stderr[-800:]
        outputs.append(done.stdout)

    assert outputs[0] == outputs[1], "the report changes with the interpreter's hash seed"
    assert json.loads(outputs[0]), "the subprocess produced no findings at all"
    # The premise: the cap has to be biting, or the crowded container is just a
    # bigger version of the case that already passed.
    first = json.loads(json.loads(outputs[0])[0])
    assert first["notListed"], "the listing cap did not engage; this tests nothing new"
    z9 = [f for f in json.loads(json.loads(outputs[0])[1])["findings"] if f["rule"] == "Z9"]
    assert z9 and z9[0]["detail"].count(",") >= 5, (
        "Z9 must be naming several folders, or its truncated list proves nothing")


def test_two_runs_are_byte_identical_when_a_check_could_not_finish():
    """The clean path was the only one this module ever ran twice.

    A document the schema check gives up on reports the exception's own words,
    and `XMLResourceExceeded` names the object it gave up on -- including the
    address that object happened to live at. Two runs of one file then differ in
    bytes, which is the single thing this module exists to forbid. It surfaced
    from the outside: the same container checked in two interpreters produced
    two reports, and the only difference in either was the address.
    """
    fixture = FIXTURES / "x4-too-deep.zip"
    data = fixture.read_bytes()
    a = rendering.as_json(check_bytes(data, fixture.name))
    b = rendering.as_json(check_bytes(data, fixture.name))
    assert a == b


def test_no_report_carries_a_memory_address():
    """Addresses are the shape this file cannot see coming.

    Byte-identity within one process is not enough: `id()` is stable for the
    life of an object, so a report can repeat an address run after run inside
    one interpreter and still differ between two. Every place that renders an
    exception's text into a finding can carry one, so the corpus is swept rather
    than the one container that was caught.
    """
    addr = re.compile(r"0x[0-9a-fA-F]{4,}")
    carrying = []
    for z in sorted({p.name: p for p in
                     [*FIXTURES.glob("*.zip"), *CORPUS.glob("*.zip"),
                      *(CORPUS / "container").glob("*.zip")]}.values()):
        text = rendering.as_json(check_bytes(z.read_bytes(), z.name))
        if addr.search(text):
            carrying.append(z.name)
    assert not carrying, (
        f"these reports name a memory address, so they are not reproducible "
        f"between runs and they print this tool's internals at a reader: {carrying}")
