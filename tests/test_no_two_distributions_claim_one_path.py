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
import sys
import zipfile

sys.path.insert(0, "tools")

from check_paths_are_disjoint import claims, overlaps  # noqa: E402


def wheel(tmp_path, distribution, version, files, scripts=()):
    """A wheel, as far as this gate is concerned: a zip with a `.dist-info`."""
    made = tmp_path / f"{distribution.replace('-', '_')}-{version}-py3-none-any.whl"
    info = f"{distribution.replace('-', '_')}-{version}.dist-info"
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
    """Different files, same top-level directory. Uninstalling one takes the
    directory the other is importing from."""
    said = overlaps([
        wheel(tmp_path, "reader", "1.0", ["shared/one.py"]),
        wheel(tmp_path, "rules", "1.0", ["shared/two.py"]),
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
