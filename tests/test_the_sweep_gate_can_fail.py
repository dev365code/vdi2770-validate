"""`--check-swept` is what stands between a release and published divergence
counts that exclude containers nobody ever swept. Nothing tested it.

Both its comparison and the `assert here` canary beside it survived being
neutered against the whole suite -- the one mutation row in the area checks that
the *workflow calls* `make oracle-fully-swept`, which is a different claim. So
this runs the tool against doctored recordings, one per way the file can lie.
"""
import json
import shutil
import subprocess
import sys

from conftest import ROOT, under_test

TOOL = ROOT / "tools" / "capture_oracle.py"
RECORDING = ROOT / "docs" / "oracle-sweep.json"


def swept(tmp_path, doctor):
    """Run `--check-swept` against a copy whose recording `doctor` has edited."""
    tree = tmp_path / "tree"
    for part in ("corpus", "tools", "src", "tests/fixtures"):
        src = ROOT / part
        if src.exists():
            shutil.copytree(src, tree / part)
    (tree / "docs").mkdir(parents=True, exist_ok=True)
    body = json.loads(RECORDING.read_text(encoding="utf-8"))
    doctor(body)
    (tree / "docs" / "oracle-sweep.json").write_text(json.dumps(body, indent=2),
                                                     encoding="utf-8")
    return subprocess.run([sys.executable, "tools/capture_oracle.py", "--check-swept"],
                          cwd=tree, capture_output=True, text=True, env=under_test())


def test_an_honest_recording_passes(tmp_path):
    """The premise. Without it every case below could be passing for the wrong
    reason -- a copy the tool cannot read at all also exits non-zero."""
    done = swept(tmp_path, lambda body: None)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_container_the_sweep_never_saw_is_refused(tmp_path):
    def drop_one(body):
        body["containers"].pop(sorted(body["containers"])[0])

    done = swept(tmp_path, drop_one)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "disagree about which containers exist" in done.stderr, done.stderr


def test_a_container_the_sweep_invented_is_refused(tmp_path):
    def add_one(body):
        body["containers"]["not-in-this-repository.zip"] = {"reference": ["Z1"], "ours": ["Z1"]}

    done = swept(tmp_path, add_one)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "disagree about which containers exist" in done.stderr, done.stderr


def test_an_empty_recording_is_not_a_complete_sweep(tmp_path):
    """"every one of 0 containers has a reference verdict" is a true sentence and
    a useless gate. The canary beside the comparison exists for this."""
    def empty(body):
        body["containers"] = {}

    done = swept(tmp_path, empty)
    assert done.returncode == 1, done.stdout + done.stderr


def test_a_container_with_no_reference_verdict_is_refused(tmp_path):
    def blank_one(body):
        name = sorted(body["containers"])[0]
        body["containers"][name]["reference"] = None
        body.pop("_unswept", None)

    done = swept(tmp_path, blank_one)
    assert done.returncode == 1, done.stdout + done.stderr


def test_a_container_still_waiting_for_the_reference_is_refused(tmp_path):
    def park_one(body):
        name = sorted(body["containers"])[0]
        body.setdefault("_unswept", {})[name] = "waiting"

    done = swept(tmp_path, park_one)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "never been through the reference" in done.stderr, done.stderr


def test_a_sweep_of_nothing_over_nothing_is_not_a_complete_sweep(tmp_path):
    """The canary, which the cases above cannot reach.

    They doctor the recording; this empties the *repository*. With no containers
    on disk and none in the file the two sets agree, so every comparison passes
    and the tool reports "every one of 0 containers has a reference verdict" --
    a true sentence about nothing, and a green release gate over a corpus that
    failed to build. Removing the canary left the suite green until this.
    """
    tree = tmp_path / "tree"
    shutil.copytree(ROOT / "tools", tree / "tools")
    shutil.copytree(ROOT / "src", tree / "src")
    (tree / "corpus").mkdir(parents=True)
    (tree / "tests" / "fixtures").mkdir(parents=True)
    (tree / "docs").mkdir(parents=True)
    body = json.loads(RECORDING.read_text(encoding="utf-8"))
    body["containers"] = {}
    body.pop("_unswept", None)
    (tree / "docs" / "oracle-sweep.json").write_text(json.dumps(body, indent=2),
                                                     encoding="utf-8")

    done = subprocess.run([sys.executable, "tools/capture_oracle.py", "--check-swept"],
                          cwd=tree, capture_output=True, text=True, env=under_test())
    assert done.returncode != 0, done.stdout + done.stderr
    assert "0 containers has a reference verdict" not in done.stdout, done.stdout


def test_the_sweep_looks_at_every_container_the_coverage_gate_does():
    """Two walks over one set of containers, and they were not the same walk.

    `capture_oracle.containers()` globbed fixed depths — `corpus/examples/*.zip`,
    `corpus/examples/*/*.zip`, `tests/fixtures/*.zip` — while
    `tools/rule_coverage.py` and the docs gate walk both trees recursively. So a
    container one directory deeper satisfied firing coverage, was counted in the
    documents, and was **invisible to the release sweep**, which went on saying
    *our half of the oracle sweep is current: 46 containers* with a
    forty-seventh sitting in the tree. Verified by putting one there.

    A container nobody compares against the reference implementation is a
    container this project has no second opinion about, and the gate that exists
    to say so could be made quiet by choosing a directory.
    """
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from capture_oracle import containers
    from conftest import CORPUS, FIXTURES

    walked = {p.resolve() for p in containers()}
    everywhere = {p.resolve() for p in
                  list(CORPUS.rglob("*.zip")) + list(FIXTURES.rglob("*.zip"))}
    missed = sorted(str(p.relative_to(ROOT)) for p in everywhere - walked)
    assert not missed, (
        "containers the coverage gate counts and the sweep never sees: " + ", ".join(missed))
