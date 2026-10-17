"""The page is the command, run where the page was opened.

`tools/browser_gates.py` opens the built page in a browser and holds it to two
things, over every container this repository has: that once it has loaded it
sends nothing anywhere, and that what it reports is what the command reports,
byte for byte. It needs a browser and, once, the network, so it runs in a job of
its own.

What can be asked without either is asked here, on every run. That the code the
page runs is the command and nothing beside it -- the same entry point, the same
arguments, the same bytes on each stream. That the comparison the page is judged
by can see a difference, on each of the three things it compares. That a
counter which saw nothing is not taken for a page that sent nothing. And that the
runtime the page carries is the one this repository names, to the byte.
"""
import bz2
import hashlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tarfile

import pytest

from conftest import CLEAN_DOCUMENT, CORPUS, FIXTURES, ROOT, under_test


def _load(path, name):
    """A file that is not on the import path, as a module. The page's Python
    lives with the page, and the two tools live in `tools/`, which nothing puts
    on the path for the suite."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT / "tools"))
    return module


PAGE = _load(ROOT / "browser" / "vdi2770_page.py", "vdi2770_page")
GATES = _load(ROOT / "tools" / "browser_gates.py", "browser_gates")
BUILD = _load(ROOT / "tools" / "build_browser.py", "build_browser")


def command(argv, cwd):
    """The command line, as somebody at a UTF-8 console runs it."""
    done = subprocess.run([sys.executable, "-m", "vdi2770_validate", *argv],
                          cwd=cwd, capture_output=True, timeout=180,
                          env=under_test(PYTHONIOENCODING="utf-8",
                                         PYTHONDONTWRITEBYTECODE="1"))
    return done.stdout, done.stderr, done.returncode


#: One of each kind of answer the command gives: a container with nothing wrong,
#: one with an error, an official sample that is not an archive at all (whose
#: hint goes to stderr), and two names the page has to pass on with care -- one
#: a shell would read as an option, and one that is not ASCII.
CASES = [
    (CLEAN_DOCUMENT, CLEAN_DOCUMENT.name),
    (FIXTURES / "x3-entity-expansion.zip", "x3-entity-expansion.zip"),
    (CORPUS / "Valid.pdf", "Valid.pdf"),
    (CLEAN_DOCUMENT, "-looks-like-an-option.zip"),
    (CLEAN_DOCUMENT, "Prüfbericht.zip"),
]


@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
@pytest.mark.parametrize("source,name", CASES, ids=[name for _, name in CASES])
def test_the_page_runs_the_command_on_what_it_is_handed(source, name, as_json, tmp_path):
    """Same argv, same stdout, same stderr, same exit code, as bytes.

    The page writes the bytes it was handed to a file, calls the function the
    console script calls, and keeps what that function wrote. Here it does so on
    this interpreter, against the command run in a directory holding the same
    file under the same name; the browser gate asks the same of the runtime the
    page carries.
    """
    data = source.read_bytes()
    room = tmp_path / "room"
    argv, out, err, code = PAGE.check(name, data, as_json, room=str(room))

    beside = tmp_path / "beside"
    beside.mkdir()
    (beside / name).write_bytes(data)
    assert argv == PAGE.argv_for(name, as_json)
    assert (out, err, code) == command(argv, beside)
    assert out, "the command said nothing about a file it was asked to check"


def test_a_name_that_reads_as_an_option_is_passed_as_a_file():
    """`-x.zip` on its own is an option to argparse, and the command refuses it
    with a usage error -- about a file somebody dropped, which is not something
    they typed. A shell user writes `./-x.zip`; so does the page."""
    assert PAGE.argv_for("-x.zip", False) == ["check", "--no-bundle", "./-x.zip"]
    assert PAGE.argv_for("x.zip", True) == ["check", "--no-bundle", "--json", "x.zip"]


@pytest.mark.parametrize("name", ["", ".", "..", "a/b.zip", "a\0b.zip"])
def test_what_is_not_a_file_name_is_refused_before_anything_is_written(name, tmp_path):
    """A browser hands over a leaf name and nothing else. Anything that could
    name a different place is refused rather than written somewhere."""
    with pytest.raises(ValueError):
        PAGE.check(name, b"PK", False, room=str(tmp_path))
    assert not any(tmp_path.iterdir())


def test_the_page_leaves_nothing_behind(tmp_path):
    """The file is removed, the streams are put back, and so is the directory
    the interpreter was in -- the page checks container after container in one
    interpreter, and anything a run leaves is something the next run sees."""
    here = os.getcwd()
    streams = sys.stdout, sys.stderr
    PAGE.check(CLEAN_DOCUMENT.name, CLEAN_DOCUMENT.read_bytes(), False, room=str(tmp_path))
    assert not any(tmp_path.iterdir())
    assert os.getcwd() == here
    assert (sys.stdout, sys.stderr) == streams


def test_the_page_reports_the_code_a_process_would_exit_with(tmp_path, monkeypatch):
    """A `SystemExit` from inside the command is how argparse ends a run. The
    process turns it into an exit status, so the page has to turn it into the
    same one -- not into a failure of the page."""
    import vdi2770.validate.entry as entry

    def stops(argv):
        print("usage: vdi2770-validate check", file=sys.stderr)
        raise SystemExit(2)

    monkeypatch.setattr(entry, "run", stops)
    _, out, err, code = PAGE.check("x.zip", b"PK", False, room=str(tmp_path))
    assert (out, code) == (b"", 2)
    assert err == ("usage: vdi2770-validate check" + os.linesep).encode()


RUN = GATES.Run


def test_the_comparison_sees_a_difference_on_each_stream():
    """The gate is a comparison, and a comparison that cannot fail is a
    sentence. One difference at a time, each has to be named."""
    argv = ["check", "--no-bundle", "a.zip"]
    same = RUN(argv, b"report\n", b"hint\n", 1)
    assert GATES.differences(same, RUN(argv, b"report\n", b"hint\n", 1)) == []
    assert "stdout" in " ".join(GATES.differences(same, RUN(argv, b"report!\n", b"hint\n", 1)))
    assert "stderr" in " ".join(GATES.differences(same, RUN(argv, b"report\n", b"", 1)))
    assert "exit" in " ".join(GATES.differences(same, RUN(argv, b"report\n", b"hint\n", 0)))


def test_two_runs_of_different_commands_are_not_compared():
    """Equal output from two different commands proves nothing about either."""
    page = RUN(["check", "--no-bundle", "a.zip"], b"x", b"", 0)
    cli = RUN(["check", "--no-bundle", "--json", "a.zip"], b"x", b"", 0)
    assert "argv" in " ".join(GATES.differences(page, cli))


def test_a_counter_that_missed_the_control_is_blind_not_quiet():
    """Zero requests after load is the claim, and a counter attached to the
    wrong thing also reads zero. Each counter is shown requests it must see; one
    that does not is named, and the zero it reported earlier is worth nothing."""
    expected = {"browser": 2, "server": 2, "page timing": 1, "worker timing": 1}
    assert GATES.blind(expected, dict(expected)) == []
    assert GATES.blind(expected, {**expected, "worker timing": 0}) == ["worker timing"]
    assert GATES.blind(expected, {"browser": 2}) == ["server", "page timing", "worker timing"]


class _Watched:
    """A page that loaded asking for nothing but itself, sent `after` once it was
    ready, and was seen by every counter when it was made to fetch."""
    url = "http://127.0.0.1:1/vdi2770.html"
    loaded = {"browser": 1, "server": 1, "page timing": 0, "worker timing": 0}
    downloads = ()
    page = None

    def __init__(self, after=()):
        self.after = dict(after)

    def asked_while_loading(self):
        return [self.url]

    def since(self, mark):
        return {name: list(self.after.get(name, ())) for name in GATES.CONTROLS}

    def controls(self, base):
        return dict(GATES.CONTROLS), {}


def _judged(watched, todo=()):
    problems = []
    GATES.judge(watched, "served", list(todo), {}, "http://127.0.0.1:1/", problems)
    return problems


def test_a_request_after_load_is_a_problem_named_by_the_counter_that_saw_it(monkeypatch):
    """The claim itself: anything a counter saw between the page being ready and
    the last container being checked is reported, whichever counter saw it."""
    monkeypatch.setattr(GATES.time, "sleep", lambda seconds: None)
    for counter in GATES.CONTROLS:
        said = _judged(_Watched({counter: ["http://127.0.0.1:9/sent"]}))
        assert [p for p in said if "1 request(s) after load" in p and counter in p], said


def test_the_two_doors_have_to_be_among_the_files_checked(monkeypatch):
    """Nothing sent is worth something only if the reader was asked to send:
    the two containers that ask it to reach the server have to be in the run,
    and if they are not, the gate says so rather than counting a zero that
    nothing tried to break."""
    monkeypatch.setattr(GATES.time, "sleep", lambda seconds: None)
    assert [p for p in _judged(_Watched()) if "reach the server" in p]


def test_every_container_and_every_official_sample_is_compared():
    """The comparison is over everything this repository checks containers
    with: every container the oracle sweep walks, and every file copied from
    the reference implementation's examples, archive or not."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import capture_oracle
    finally:
        sys.path.remove(str(ROOT / "tools"))
    found = GATES.inputs()
    assert len(found) == len(set(found))
    assert set(capture_oracle.containers()) <= set(found)
    samples = {p for p in CORPUS.rglob("*") if p.is_file()}
    assert samples <= set(found)
    assert any(p.suffix != ".zip" for p in samples)


def test_the_runtime_is_the_one_this_repository_names():
    """The page carries a Python that nobody here compiled. Its digest is
    written down, and anything else is refused, not built."""
    data = b"a runtime"
    assert BUILD.verified(data, hashlib.sha256(data).hexdigest(), "a runtime") == data
    with pytest.raises(SystemExit, match=hashlib.sha256(data).hexdigest()):
        BUILD.verified(data, hashlib.sha256(b"another").hexdigest(), "a runtime")


def _tarball(names):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name in names:
            body = f"contents of {name}".encode()
            info = tarfile.TarInfo(f"pyodide/{name}")
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return bz2.compress(raw.getvalue())


#: What the runtime's `.wasm` has compiled into it besides CPython itself, in the
#: build Pyodide 0.29.5 made of it: Emscripten 4.0.9 and the musl it carries, its
#: port of bzip2, libffi, and Pyodide's hiwire; and, inside CPython, expat,
#: libmpdec, zlib, HACL* and the rest of what CPython's licence page lists.
INCORPORATED = ("hiwire", "CPython incorporates", "libffi", "HACL*", "bzip2", "Emscripten", "musl")


def test_the_page_carries_the_notice_of_everything_compiled_into_its_runtime():
    """A binary built from MIT and BSD code carries their notices, and the
    runtime is such a binary. The CPython licence the page printed names none of
    what is compiled into it -- it says that software is under the licences
    listed with it, and that list is in CPython's documentation, not in that
    file -- so expat, libffi, libmpdec, HACL*, bzip2 and musl were in the page
    without a word of their notices."""
    named = " ".join(entry["name"] for entry in BUILD.RUNTIME_LICENCES)
    missing = [component for component in INCORPORATED if component not in named]
    assert not missing, f"the page prints no notice for {missing}"


def test_every_notice_the_page_prints_is_pinned_at_a_revision():
    """Fetched at a tag or a commit, and held to a digest, as the runtime is: a
    branch would print whatever the file says on the day of the build."""
    for entry in BUILD.RUNTIME_LICENCES:
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), entry["name"]
        assert f"/{entry['revision']}/" in entry["url"], (entry["name"], entry["url"])
        assert entry["revision"] in entry["source"], (entry["name"], entry["source"])


def test_the_notice_files_name_each_notice_the_page_prints_at_its_revision():
    """`THIRD_PARTY.md` -- both copies, the repository's and the wheel's -- names
    each component the page prints a notice for, at the revision it was taken
    from, so the two cannot come to describe different builds."""
    for copy in (ROOT / "THIRD_PARTY.md", ROOT / "packages" / "vdi2770" / "THIRD_PARTY.md"):
        text = copy.read_text(encoding="utf-8")
        for entry in BUILD.RUNTIME_LICENCES:
            assert entry["notice"] in text and f"`{entry['revision']}`" in text, (copy.name, entry["name"])


def test_a_notice_kept_in_a_source_file_is_cut_to_the_notice():
    """HACL* keeps its MIT notice at the head of each source file rather than in
    a file of its own; the page prints that comment and not the C after it."""
    source = b"/* MIT License\n *\n * Permission is hereby granted ... */\n\nint f(void) { return 0; }\n"
    cut = BUILD.notice_text(source, ("/* MIT License", "*/"))
    assert cut.startswith("/* MIT License") and cut.endswith("*/") and "int f" not in cut


def test_the_runtime_files_are_taken_by_name():
    """Five files out of the release, each by the name the loader asks for."""
    got = BUILD.runtime_files(_tarball(list(BUILD.RUNTIME_FILES) + ["python.exe"]))
    assert sorted(got) == sorted(BUILD.RUNTIME_FILES)
    assert got["pyodide.asm.wasm"] == b"contents of pyodide.asm.wasm"
    with pytest.raises(SystemExit, match="pyodide.asm.wasm"):
        BUILD.runtime_files(_tarball([n for n in BUILD.RUNTIME_FILES if n != "pyodide.asm.wasm"]))


def test_each_place_in_the_page_is_filled_exactly_once():
    """A marker left in the page is a page that does not start, and one filled
    twice is a second copy of something nobody meant to ship twice."""
    marks = BUILD.MARKS
    template = "<html>" + "".join(marks) + "</html>"
    filled = BUILD.assemble(template, {m: f"[{n}]" for n, m in enumerate(marks)})
    assert filled == "<html>" + "".join(f"[{n}]" for n in range(len(marks))) + "</html>"
    with pytest.raises(SystemExit, match="once"):
        BUILD.assemble(template + marks[0], dict.fromkeys(marks, "x"))
    with pytest.raises(SystemExit, match="once"):
        BUILD.assemble(template.replace(marks[-1], ""), dict.fromkeys(marks, "x"))


def test_nothing_put_in_a_script_block_can_end_it():
    """The worker's source and the embedded runtime sit inside `<script>`
    elements. A `</script` inside one ends it early, and the rest of the page is
    whatever the parser makes of the remainder."""
    with pytest.raises(SystemExit, match="script"):
        BUILD.script_safe("x = '</SCRIPT>'", "the worker")
    assert BUILD.script_safe("x = 1", "the worker") == "x = 1"


def test_the_job_installs_the_browser_the_gate_was_written_against():
    """The gate is a Playwright program, and Playwright moves its API between
    releases. The version the gate names is the version CI installs."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert f'"playwright=={GATES.PLAYWRIGHT}"' in ci


def test_the_job_runs_the_python_the_page_carries():
    """Two interpreters of different minor versions can word one standard-library
    error differently, and a comparison across them could not say which door a
    difference came through. So the command runs on the Python the page runs."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = ci[ci.index("\n  the-page-this-repo-offers:"):]
    minor = ".".join(BUILD.RUNTIME["python"].split(".")[:2])
    assert f'python-version: "{minor}"' in job.split("\n  the-", 2)[1]


def test_the_gate_refuses_to_compare_across_interpreters():
    """Asked to compare a page and a command on two different Pythons, it says
    so rather than reporting the differences as the page's."""
    page = {"python": "3.13.2", "vdi2770": "0.12.0", "xmlschema": "4.2.0", "elementpath": "5.1.4"}
    assert GATES.unlike(page, dict(page, python="3.13.9")) == []
    assert GATES.unlike(page, dict(page, python="3.12.4")) == ["python"]
    assert GATES.unlike(page, dict(page, elementpath="5.2.0")) == ["elementpath"]


def test_the_page_is_built_from_files_that_are_here():
    """The builder reads the page, its worker and its Python from `browser/`."""
    for name in ("page.html", "worker.js", "vdi2770_page.py"):
        assert (ROOT / "browser" / name).is_file(), name


def test_what_is_bundled_is_resolved_for_the_python_that_runs_it(tmp_path, monkeypatch):
    """The single file is resolved for the oldest Python this project supports,
    because it is copied to machines nobody here has seen. The page is not: it
    carries its own Python, and a dependency chosen for another one is a
    dependency the command running beside it may not have chosen. And the
    staging removes each bundled distribution's `.dist-info` -- which is where
    its licence is -- so the page keeps those texts before they go."""
    zipapp = _load(ROOT / "tools" / "build_zipapp.py", "build_zipapp")
    asked = []

    def pip(cmd, **kwargs):
        asked.append(cmd[cmd.index("--python-version") + 1])
        target = cmd[cmd.index("--target") + 1]
        info = os.path.join(target, "somepkg-1.2.dist-info")
        os.makedirs(os.path.join(info, "licenses"))
        with open(os.path.join(info, "METADATA"), "w", encoding="utf-8") as fh:
            fh.write("Metadata-Version: 2.4\nName: somepkg\nVersion: 1.2\nLicense-Expression: MIT\n")
        with open(os.path.join(info, "licenses", "LICENSE"), "w", encoding="utf-8") as fh:
            fh.write("the MIT text\n")
        os.makedirs(os.path.join(target, "somepkg"))

    monkeypatch.setattr(zipapp.subprocess, "run", pip)
    notices = []
    zipapp.stage(tmp_path, python_version="3.13", notices=notices)
    assert asked == ["3.13"]
    assert notices == [{"name": "somepkg", "version": "1.2", "licence": "MIT",
                        "texts": {"licenses/LICENSE": "the MIT text\n"}}]
    assert not list(tmp_path.glob("*.dist-info"))

    asked.clear()
    for leftover in tmp_path.iterdir():
        if leftover.is_dir():
            import shutil
            shutil.rmtree(leftover)
        else:
            leftover.unlink()
    zipapp.stage(tmp_path)
    assert asked == [zipapp.python_floor()]
