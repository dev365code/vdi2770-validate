"""The same container must produce the same bytes, twice, and regardless of the
order its members happen to be stored in."""
import io
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate import report as rendering
from vdi2770_validate.runner import check_bytes, check_file


def test_two_runs_are_byte_identical():
    a = rendering.as_json(check_file(str(CLEAN_DOCUMENT)))
    b = rendering.as_json(check_file(str(CLEAN_DOCUMENT)))
    assert a == b


def test_member_order_does_not_change_the_verdict():
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    names = src.namelist()
    forward, backward = io.BytesIO(), io.BytesIO()
    with zipfile.ZipFile(forward, "w") as z:
        for n in names:
            z.writestr(n, src.read(n))
    with zipfile.ZipFile(backward, "w") as z:
        for n in reversed(names):
            z.writestr(n, src.read(n))
    a = check_bytes(forward.getvalue(), "x.zip")
    b = check_bytes(backward.getvalue(), "x.zip")
    assert [f.rule.id for f in a.sorted()] == [f.rule.id for f in b.sorted()]


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
    crowded = tmp_path / "many_undeclared.zip"
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in src.namelist():
            z.writestr(n, src.read(n))
        for n in ("anlage.txt", "notiz.txt", "zusatz.txt", "beiblatt.txt",
                  "liste.txt", "extra.txt", "info.txt", "rest.txt"):
            z.writestr(n, b"x")
    crowded.write_bytes(buf.getvalue())

    targets = [str(crowded), str(CLEAN_DOCUMENT), str(CLEAN_DOCUMENTATION)]
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
