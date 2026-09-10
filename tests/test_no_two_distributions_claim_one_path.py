"""The gate that compares artifacts rather than manifests, and what it must see.

pip uninstalls by the record it wrote at install time. Two distributions that
ever write one path do not conflict when they are installed — the second simply
overwrites — and they conflict when either is removed, because the record being
uninstalled lists a file the other is still using. Nothing warns, `pip check`
stays green, and the tool stops running.

The wheels are made here rather than built, because the collisions this has to
see are ones neither of this project's manifests produces: build them and there
is nothing to catch, so deleting the check would leave the suite green.

Each wheel below differs from the passing case on exactly one axis — a shared
path, a shared command, a shared import name — so no assertion is propped up by
another.
"""
import hashlib
import io
import sys
import zipfile

import pytest
from packaging.utils import parse_wheel_filename

sys.path.insert(0, "tools")

import check_paths_are_disjoint as gate  # noqa: E402
from check_paths_are_disjoint import claims, overlaps, wheels_in  # noqa: E402


def wheel(tmp_path, distribution, version, files, scripts=(), info_name=None):
    """A wheel, as far as this gate is concerned: a zip with a `.dist-info`.

    `info_name` spells the `.dist-info` directory differently from the metadata
    name, which is not a hypothetical: setuptools wrote `a-b-1.0.dist-info` for
    years and writes `a_b-1.0.dist-info` now, and this gate reads the directory.
    """
    made = tmp_path / f"{distribution.replace('-', '_')}-{version}-py3-none-any.whl"
    info = f"{info_name or distribution.replace('-', '_')}-{version}.dist-info"
    with zipfile.ZipFile(made, "w") as z:
        for name in files:
            z.writestr(name, "")
        z.writestr(f"{info}/METADATA",
                   f"Metadata-Version: 2.1\nName: {distribution}\nVersion: {version}\n")
        if scripts:
            z.writestr(f"{info}/entry_points.txt",
                       "[console_scripts]\n"
                       + "".join(f"{name} = {target}\n" for name, target in scripts))
    return made


def test_two_distributions_that_share_nothing_are_fine(tmp_path):
    assert overlaps([
        wheel(tmp_path, "reader", "1.0", ["reader/__init__.py"]),
        wheel(tmp_path, "rules", "1.0", ["rules/__init__.py"]),
    ]) == []


def test_two_distributions_that_ship_one_file_are_caught(tmp_path):
    """The mechanism itself: one path in two records."""
    said = overlaps([
        wheel(tmp_path, "reader", "1.0", ["shared/thing.py"]),
        wheel(tmp_path, "rules", "1.0", ["shared/thing.py"]),
    ])
    assert said and "path shared/thing.py" in said[0]


def test_two_distributions_that_install_one_command_are_caught(tmp_path):
    """No wheel RECORD has a `bin/` entry — measured, zero — because pip writes
    the console scripts at install time from `entry_points.txt`. A comparison of
    recorded paths alone is blind to the files that vanished first the last time
    an installation here was destroyed."""
    said = overlaps([
        wheel(tmp_path, "reader", "1.0", ["reader/__init__.py"],
              scripts=[("check-it", "reader.cli:main")]),
        wheel(tmp_path, "rules", "1.0", ["rules/__init__.py"],
              scripts=[("check-it", "rules.cli:main")]),
    ])
    assert said and "command check-it" in said[0]


def test_two_distributions_that_ship_one_import_name_are_caught(tmp_path):
    """Two packages, one name.

    Both ship `shared/__init__.py`, which is what makes it a package rather than
    a namespace: installing the second overwrites the first's `__init__.py` and
    uninstalling either deletes the file the other needs. Without those files it
    would be a PEP 420 namespace, where sharing a top-level name is the intended
    behaviour — the case below this one.
    """
    said = overlaps([
        wheel(tmp_path, "reader", "1.0", ["shared/__init__.py", "shared/one.py"]),
        wheel(tmp_path, "rules", "1.0", ["shared/__init__.py", "shared/two.py"]),
    ])
    assert said and "import shared" in said[0]


def test_two_versions_of_one_distribution_may_share_everything(tmp_path):
    """pip replacing its own files is the normal case, and requiring these to be
    disjoint would fail every release this project ever makes."""
    assert overlaps([
        wheel(tmp_path, "reader", "1.0", ["reader/__init__.py"],
              scripts=[("check-it", "reader.cli:main")]),
        wheel(tmp_path, "reader", "2.0", ["reader/__init__.py"],
              scripts=[("check-it", "reader.cli:main")]),
    ]) == []


def test_a_command_is_read_from_the_section_it_is_declared_in(tmp_path):
    """`entry_points.txt` is parsed, not searched.

    The name on the left is a command; the module path on the right is not, and
    neither is a name under some other section. A substring search over that
    file reports all three.
    """
    made = wheel(tmp_path, "rules", "1.0", ["rules/__init__.py"])
    with zipfile.ZipFile(made, "a") as z:
        z.writestr("rules-1.0.dist-info/entry_points.txt",
                   "[console_scripts]\nreal-command = rules.cli:main\n\n"
                   "[some.other.group]\nnot-a-command = rules.plugin:go\n")
    _, owned = claims(made)
    assert "command real-command" in owned
    assert "command not-a-command" not in owned
    assert "command main" not in owned


def test_a_script_installed_by_a_data_directory_is_still_a_command(tmp_path):
    """A wheel installs `{dist}-{ver}.data/scripts/x` as `bin/x`.

    Recorded verbatim, two distributions installing one `vdi2770-validate` that
    way claim two different strings — the directory carries their own name and
    version — and collide anyway. A console script is the file that went first
    the last time an installation here was destroyed, and this is the second of
    the two routes pip supports for creating one.
    """
    said = overlaps([
        wheel(tmp_path, "alpha", "1.0",
              ["alpha-1.0.data/scripts/check-it", "alpha/__init__.py"]),
        wheel(tmp_path, "beta", "1.0",
              ["beta-1.0.data/scripts/check-it", "beta/__init__.py"]),
    ])
    assert said and "command check-it" in said[0]


def test_a_payload_installed_by_a_data_directory_lands_where_it_lands(tmp_path):
    """`{dist}-{ver}.data/purelib/shared/…` is `shared/…` in site-packages, and
    two distributions putting a package there share it exactly as if they had
    shipped it at the top of the archive."""
    said = overlaps([
        wheel(tmp_path, "gamma", "1.0", ["gamma-1.0.data/purelib/shared/__init__.py"]),
        wheel(tmp_path, "delta", "1.0", ["delta-1.0.data/purelib/shared/__init__.py"]),
    ])
    assert said and "import shared" in said[0]


def test_two_spellings_of_one_distribution_are_one_distribution(tmp_path):
    """setuptools wrote `a-b-1.0.dist-info` for years and writes `a_b-1.0` now.

    Compared as written, the built alias and the published alias read as two
    distributions and every path they share — which is all of them — is a
    collision. That is a red release for a reason that has nothing to do with
    the release.
    """
    assert overlaps([
        wheel(tmp_path, "vdi2770-validate", "0.7.0", ["vdi2770_validate/__init__.py"],
              info_name="vdi2770-validate"),
        wheel(tmp_path, "vdi2770-validate", "0.8.0", ["vdi2770_validate/__init__.py"]),
    ]) == []


def test_a_namespace_package_is_not_a_collision(tmp_path):
    """PEP 420 lets two distributions share a top-level name on purpose, and pip
    removes only the files it recorded. Reporting it would block the layout this
    project has just moved to."""
    assert overlaps([
        wheel(tmp_path, "ns1", "1.0", ["ns/one/__init__.py"]),
        wheel(tmp_path, "ns2", "1.0", ["ns/two/__init__.py"]),
    ]) == []


def test_a_gui_script_is_a_command_too(tmp_path):
    """The other section pip writes scripts from. Its support was in the code
    and in nothing that could fail without it."""
    made = wheel(tmp_path, "one", "1.0", ["one/__init__.py"])
    other = wheel(tmp_path, "two", "1.0", ["two/__init__.py"])
    for w, target in ((made, "one.gui:main"), (other, "two.gui:main")):
        with zipfile.ZipFile(w, "a") as z:
            info = [n for n in z.namelist() if n.endswith(".dist-info/METADATA")][0]
            z.writestr(info.rsplit("/", 1)[0] + "/entry_points.txt",
                       f"[gui_scripts]\nsee-it = {target}\n")
    said = overlaps([made, other])
    assert said and "command see-it" in said[0]



# What follows is the other half of the comparison: which published wheels the
# gate is shown at all. None of it touches the network. The property under test
# is what the gate does with an answer, and the index gives a different answer
# after every release.
#
# Each `main()` case puts one collision in place, between one wheel this tree
# builds and one served wheel of the other name, and the assertion asks for the
# line that names both. A collision among the served wheels would satisfy a
# looser assertion on its own -- the first version of these cases did exactly
# that, and a gate that stopped looking at this tree's wheels stayed green.

def answer(served):
    """What the index says about one name when it serves these files."""
    return {
        "files": [{"filename": w.name, "url": w.as_uri(),
                   "hashes": {"sha256": hashlib.sha256(w.read_bytes()).hexdigest()}}
                  for w in served],
        "versions": sorted({str(parse_wheel_filename(w.name)[1]) for w in served}),
    }


def run_the_gate(monkeypatch, tmp_path, built, served):
    """`main()`, with its two builds and the index answered from here."""
    projects = []
    for n, _ in enumerate(built):
        projects.append(tmp_path / f"project{n}")
        projects[-1].mkdir()
    monkeypatch.setattr(gate, "PROJECTS", tuple(projects))
    monkeypatch.setattr(gate, "_build",
                        lambda project, out: built[projects.index(project)])
    monkeypatch.setattr(gate, "_ask",
                        lambda name, timeout=15.0: answer(served.get(name, [])))
    return gate.main()


def places(tmp_path, *names):
    made = [tmp_path / n for n in names]
    for d in made:
        d.mkdir()
    return made


def ours(where, engine=(), alias=()):
    """The two wheels this tree builds, each with its own package and `extra`."""
    return [wheel(where, "vdi2770-validate", "1.0",
                  ["vdi2770_validate/__init__.py", *alias]),
            wheel(where, "vdi2770", "1.0", ["vdi2770/__init__.py", *engine])]


def named_together(err, one, other):
    """Whether a single reported pair names both of these files."""
    return any(one in line and other in line for line in err.splitlines())


ALIAS_BUILT = "vdi2770_validate-1.0-py3-none-any.whl"
ENGINE_BUILT = "vdi2770-1.0-py3-none-any.whl"


def test_a_release_newer_than_anything_written_here_is_compared(
        tmp_path, monkeypatch, capsys):
    """This gate used to carry the newest release as a constant, and the next
    release left it comparing against the one before -- green, because nothing
    collided with that one either.

    The collision here is between the alias this tree builds and a release of
    the engine numbered past anything this repository could have written down.
    A list kept in the file cannot see it; an answer from the index does.
    """
    built, old, new = places(tmp_path, "built", "old", "new")
    served = {
        "vdi2770": [wheel(old, "vdi2770", "0.1", ["vdi2770/__init__.py"]),
                    wheel(new, "vdi2770", "9.9.9",
                          ["vdi2770/__init__.py", "shared/thing.py"])],
        "vdi2770-validate": [wheel(old, "vdi2770-validate", "0.1",
                                   ["vdi2770_validate/__init__.py"])],
    }
    assert run_the_gate(monkeypatch, tmp_path,
                        ours(built, alias=["shared/thing.py"]), served) == 1
    assert named_together(capsys.readouterr().err, ALIAS_BUILT,
                          "vdi2770-9.9.9-py3-none-any.whl")


def test_a_collision_in_an_old_release_is_still_a_collision(
        tmp_path, monkeypatch, capsys):
    """Somebody who installed 0.1 upgrades with the same command as somebody
    who installed the newest release. A gate that asks only about the newest
    one has the old defect with a fresher number in it."""
    built, old, new = places(tmp_path, "built", "old", "new")
    served = {
        "vdi2770": [wheel(old, "vdi2770", "0.1",
                          ["vdi2770/__init__.py", "shared/thing.py"]),
                    wheel(new, "vdi2770", "9.9.9", ["vdi2770/__init__.py"])],
        "vdi2770-validate": [wheel(new, "vdi2770-validate", "9.9.9",
                                   ["vdi2770_validate/__init__.py"])],
    }
    assert run_the_gate(monkeypatch, tmp_path,
                        ours(built, alias=["shared/thing.py"]), served) == 1
    assert named_together(capsys.readouterr().err, ALIAS_BUILT,
                          "vdi2770-0.1-py3-none-any.whl")


def test_every_name_the_index_serves_is_asked(tmp_path, monkeypatch, capsys):
    """Both names have releases, and a collision can be with either. This one
    is between the engine this tree builds and a release of the old name."""
    built, old = places(tmp_path, "built", "old")
    served = {
        "vdi2770": [wheel(old, "vdi2770", "0.1", ["vdi2770/__init__.py"])],
        "vdi2770-validate": [wheel(old, "vdi2770-validate", "0.1",
                                   ["vdi2770_validate/__init__.py",
                                    "shared/thing.py"])],
    }
    assert run_the_gate(monkeypatch, tmp_path,
                        ours(built, engine=["shared/thing.py"]), served) == 1
    assert named_together(capsys.readouterr().err, ENGINE_BUILT,
                          "vdi2770_validate-0.1-py3-none-any.whl")


def test_two_releases_already_published_are_not_this_releases_to_answer_for(
        tmp_path, monkeypatch, capsys):
    """A collision between two releases on the index is a fact no commit can
    change. Failing on it would fail every release after it -- the one meant to
    repair things included -- and yanking does not remove it from what people
    have. It is reported, and it is not counted."""
    built, old = places(tmp_path, "built", "old")
    served = {
        "vdi2770": [wheel(old, "vdi2770", "0.1",
                          ["vdi2770/__init__.py", "shared/thing.py"])],
        "vdi2770-validate": [wheel(old, "vdi2770-validate", "0.1",
                                   ["vdi2770_validate/__init__.py",
                                    "shared/thing.py"])],
    }
    assert run_the_gate(monkeypatch, tmp_path, ours(built), served) == 0
    err = capsys.readouterr().err
    assert "note, not counted" in err
    assert named_together(err, "vdi2770-0.1-py3-none-any.whl",
                          "vdi2770_validate-0.1-py3-none-any.whl")


def test_an_index_that_lists_no_wheel_is_a_refusal():
    """A comparison against nothing passes: every release of this name would
    drop out of the comparison without a word."""
    with pytest.raises(SystemExit) as refused:
        wheels_in("vdi2770", {"files": [], "versions": []})
    assert "lists no wheel for vdi2770" in str(refused.value)


def test_a_release_the_index_lists_without_a_wheel_is_a_refusal(tmp_path):
    """pip would build that release from its source, and what it puts on a disk
    is not something this gate can read out of a wheel. Leaving it out would
    make the comparison smaller without saying so."""
    listed = answer([wheel(tmp_path, "vdi2770", "1.0", ["vdi2770/__init__.py"])])
    listed["versions"].append("0.5")
    with pytest.raises(SystemExit) as refused:
        wheels_in("vdi2770", listed)
    assert "vdi2770 0.5 with no wheel" in str(refused.value)


def test_a_release_known_only_by_its_source_archive_is_a_refusal(tmp_path):
    """`versions` is a later addition to the index format, and an answer without
    it still names the release -- in the filename of its source archive."""
    listed = answer([wheel(tmp_path, "vdi2770", "1.0", ["vdi2770/__init__.py"])])
    del listed["versions"]
    listed["files"].append({"filename": "vdi2770-0.5.tar.gz",
                            "url": "https://example.invalid/vdi2770-0.5.tar.gz",
                            "hashes": {"sha256": "0" * 64}})
    with pytest.raises(SystemExit) as refused:
        wheels_in("vdi2770", listed)
    assert "vdi2770 0.5 with no wheel" in str(refused.value)


def test_a_file_listed_twice_is_a_refusal(tmp_path):
    """Both would be downloaded to one name, the second replacing the first,
    and one of the two archives would never be read."""
    listed = answer([wheel(tmp_path, "vdi2770", "1.0", ["vdi2770/__init__.py"])])
    listed["files"].append(dict(listed["files"][0], hashes={"sha256": "1" * 64}))
    with pytest.raises(SystemExit) as refused:
        wheels_in("vdi2770", listed)
    assert "lists vdi2770-1.0-py3-none-any.whl twice" in str(refused.value)


@pytest.mark.parametrize("shape", [
    {"files": ["not an entry"]},
    {"files": [{"filename": None}]},
    {"files": [{"filename": "vdi2770-1.0-py3-none-any.whl",
                "hashes": {"sha256": "0" * 64}}]},
    {"files": [{"filename": "not-a-wheel-name.whl",
                "url": "https://example.invalid/x", "hashes": {"sha256": "0" * 64}}]},
    {"files": [], "versions": "0.5"},
], ids=["entry-not-a-mapping", "no-filename", "no-url", "bad-wheel-name",
        "versions-not-a-list"])
def test_an_answer_this_cannot_read_is_a_refusal_that_says_so(shape):
    """Each of these used to end in a traceback. That still failed the gate,
    but it said nothing about why, and a reader of the log had to work out
    that the index had answered in a shape nobody expected."""
    with pytest.raises(SystemExit) as refused:
        wheels_in("vdi2770", shape)
    assert "in a shape this cannot read" in str(refused.value)


def test_a_yanked_release_is_still_compared(tmp_path):
    """pip still installs a yanked release when it is pinned, and whoever has
    it upgrades with the same command as everybody else."""
    listed = answer([wheel(tmp_path, "vdi2770", "1.0", ["vdi2770/__init__.py"])])
    listed["files"][0]["yanked"] = "withdrawn"
    assert [f for f, _, _ in wheels_in("vdi2770", listed)] == [
        "vdi2770-1.0-py3-none-any.whl"]


def test_a_download_that_is_not_the_published_file_is_refused(tmp_path):
    """Whatever arrives is compared only if it is the file the index gave a
    digest for. Anything else answers a question about some other archive."""
    made = wheel(tmp_path, "vdi2770", "1.0", ["vdi2770/__init__.py"])
    with pytest.raises(SystemExit) as refused:
        gate._fetch(made.as_uri(), "0" * 64, tmp_path / "fetched.whl")
    assert "is not the file the index published" in str(refused.value)
    assert not (tmp_path / "fetched.whl").exists()


def test_the_index_is_asked_not_to_answer_from_a_cache(monkeypatch):
    """The request says it wants the index rather than a copy somebody stored,
    of the page pip reads, in the form pip reads it.

    It is a request. PyPI's own CDN does not honour it -- measured, the same
    request twice was answered from its cache -- and the tool says so where it
    sends it. A cache on the way that does honour it cannot then hand back a
    page from before an upload.
    """
    asked = []

    def urlopen(request, timeout=None):
        asked.append(request)
        return io.BytesIO(b'{"files": []}')

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    gate._ask("vdi2770")
    assert asked[0].full_url == "https://pypi.org/simple/vdi2770/"
    assert asked[0].get_header("Cache-control") == "no-cache"
    assert asked[0].get_header("Accept") == "application/vnd.pypi.simple.v1+json"
