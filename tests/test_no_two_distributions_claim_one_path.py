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
