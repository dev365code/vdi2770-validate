"""The same container must produce the same bytes, twice, and regardless of the
order its members happen to be stored in."""
import io
import re
import zipfile

import pytest
from vdi2770_validate.model import MAX_LISTED_PER_RULE
from vdi2770_validate.runner import check_bytes, check_file

from conftest import CLEAN_DOCUMENT, CORPUS, FIXTURES
from vdi2770_validate import report as rendering
from vdi2770_validate import runner, xsdvalidate


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
    # The one container whose report quotes an exception. Byte-identity inside
    # one process cannot see an address that is stable for that process's life;
    # this is the same comparison run in two of them. If it is what breaks, read
    # the failure as "the report changed between processes" -- the seed is what
    # this test varies, not necessarily what moved.
    targets.append(str(FIXTURES / "x4-too-deep.zip"))
    assert len(targets) >= 8, targets

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
    first = check_bytes(data, fixture.name)
    # The premise, asserted rather than hoped for. Both halves of it belong to
    # somebody else: this fixture's depth is `tools/make_fixtures.py`'s number
    # and the limit it trips is `xmlschema`'s. Move either and the container
    # reports like any other -- at which point the two lines below would compare
    # two ordinary reports and call that a pass, with the bug live and the file
    # green. `tests/fixtures` is generated and `make clean` deletes it, so this
    # is not a hypothetical way for the file to stop testing anything.
    gave_up = [f for f in first.findings if f.rule.id == "X4"]
    assert gave_up, ("the fixture no longer makes a check give up, so this compares "
                     f"two ordinary reports: {sorted(f.rule.id for f in first.findings)}")
    quoted = gave_up[0].detail or ""
    assert "<" in quoted, ("the report no longer quotes an exception that names an "
                           f"object, which is what an address rides in on: {quoted}")
    a = rendering.as_json(first)
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
    # Every archive under both trees, not three hand-named directories: two zips
    # live a level down from where the first version of this looked, and keying
    # the set on the file name rather than the path would have dropped a fixture
    # that ever shared a corpus name.
    archives = sorted({p.resolve() for p in
                       [*FIXTURES.rglob("*.zip"), *CORPUS.rglob("*.zip")]})
    carrying, quoting = [], []
    for z in archives:
        report = check_bytes(z.read_bytes(), z.name)
        if any(f.rule.id in ("X4", "X5") for f in report.findings):
            quoting.append(z.name)
        if addr.search(rendering.as_json(report)):
            carrying.append(z.name)
    # Two premises, because this sweep has two ways to check nothing and pass.
    # `tests/fixtures` is generated by `make fixtures` and removed by `make
    # clean`, so the first glob can legitimately come back empty; and a sweep in
    # which *no* container makes a check give up renders no exception's words at
    # all, which is the only thing an address can ride in on.
    assert len(archives) >= 40, f"the corpus did not come up; this swept {len(archives)}"
    assert quoting, ("no container here makes a check give up, so no report quotes an "
                     "exception and this sweep cannot catch what it was written for")
    assert not carrying, (
        f"these reports name a memory address, so they are not reproducible "
        f"between runs and they print this tool's internals at a reader: {carrying}")


class Surprise(Exception):
    """In no hierarchy a guard could name, so catching it proves "anything"."""


def _naming_an_object(*a, **k):
    """Raise the way a third-party library does: with an object in the message."""
    raise Surprise(f"gave up on {io.BytesIO()!r}")


def _naming_an_object_generator(*a, **k):
    """The same, through the door a rule module uses.

    A rule module's `check` is a generator, and a plain function that raises is
    not the same thing to the runner: it would raise where the runner expects to
    be handed an iterator. The `yield` is never reached; it is what makes this a
    generator function at all.
    """
    raise Surprise(f"gave up on {io.BytesIO()!r}")
    yield                                    # never reached


SITES = ["rule module", "parse step", "domain build", "schema check"]


@pytest.mark.parametrize("site", SITES)
def test_a_crashed_check_does_not_name_an_address(monkeypatch, site):
    """The runner renders an exception's words in three places of its own.

    They were fixed alongside the schema check's, and nothing held them to it:
    reverting all three left the whole suite green. No container reaches them --
    `X5` is bug-shaped rather than data-shaped -- so the crash is injected here,
    which is how the file that guards these paths already works.
    """
    if site == "rule module":
        monkeypatch.setattr(runner, "r_files",
                            type("M", (), {"check": staticmethod(_naming_an_object_generator)}))
    elif site == "parse step":
        monkeypatch.setattr(runner.xmlread, "parse", _naming_an_object)
    elif site == "domain build":
        monkeypatch.setattr(runner, "build", _naming_an_object)
    else:
        monkeypatch.setattr(xsdvalidate, "validate", _naming_an_object)

    report = check_file(str(CLEAN_DOCUMENT))
    text = rendering.as_json(report)
    # The premise: the crash really did land in the report as a finding, rather
    # than being swallowed somewhere that leaves nothing to inspect.
    said_so = [f for f in report.findings if "Surprise" in (f.detail or "")]
    assert said_so, f"the injected crash is not in the report: {sorted(f.rule.id for f in report.findings)}"
    assert "gave up on" in (said_so[0].detail or ""), said_so[0].detail
    assert not re.search(r"0x[0-9a-fA-F]{4,}", text), (
        f"a crash at the {site} put an address in the report: {said_so[0].detail}")


def test_an_unreadable_path_does_not_name_an_address(monkeypatch, capsys):
    """The CLI has a rendering site of its own, and it is the machine-readable one.

    `--json` carries `unreadable` for every path the tool could not read, and
    that field is the exception's own words whenever the failure is not an
    `OSError` with a `strerror`. A consumer diffing two runs of one drop folder
    would see a change that is not about their files.
    """
    from vdi2770_validate import cli

    monkeypatch.setattr(cli, "check_file",
                        lambda path: (_ for _ in ()).throw(Surprise(f"gave up on {io.BytesIO()!r}")))
    code = cli.main(["check", "--json", "--no-bundle", "whatever.zip"])
    assert code == 2, f"a path that could not be read is exit 2, not {code}"
    out = capsys.readouterr()
    both = out.out + out.err
    assert "gave up on" in both, both
    assert not re.search(r"0x[0-9a-fA-F]{4,}", both), both
