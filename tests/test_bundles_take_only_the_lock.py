"""The lock describes the bytes carried across, including transitive requirements."""
import importlib
import json
import sys

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))


def lock_tool():
    return importlib.import_module("bundle_lock")


def test_the_lock_and_the_public_extra_name_the_same_schema():
    tool = lock_tool()
    entries = tool.read_lock()
    tool.check_extra(entries)
    changed = [dict(e, version="0.0.1") if e["name"] == "xmlschema" else e for e in entries]
    with pytest.raises(SystemExit, match="validate extra"):
        tool.check_extra(changed)


def test_the_locked_wheels_require_only_versions_inside_the_lock():
    tool = lock_tool()
    entries = tool.read_lock()
    tool.check_installed(entries)
    # The requirement is read from the installed wheel's METADATA, whose
    # version has to match the lock before its requirements can stand for it.
    changed = [dict(e, version="99.0") if e["name"] == "elementpath" else e for e in entries]
    from importlib.metadata import metadata
    with pytest.raises(SystemExit, match="elementpath.*99.0"):
        tool.check_requirements(metadata("xmlschema"), changed)


def test_both_notice_files_name_every_bundled_version():
    for where in (ROOT, ROOT / "packages/vdi2770"):
        said = (where / "THIRD_PARTY.md").read_text(encoding="utf-8")
        for entry in lock_tool().read_lock():
            assert f"`{entry['name']}` {entry['version']}" in said


@pytest.mark.parametrize("field,value", [
    ("sha256", "A" * 64), ("sha256", "a" * 63), ("sha256", ""),
    ("size", 0), ("size", True), ("url", "https://example.org/packages/a.whl"),
    ("url", "http://files.pythonhosted.org/packages/a.whl"),
    ("name", "Elementpath"), ("name", "element_path"),
    ("tags", ["py3-none-any"]), ("requires_python", ">=3.9"),
    ("file", "elementpath-5.1.4-cp313-none-any.whl"),
])
def test_a_malformed_lock_is_refused(field, value, tmp_path):
    tool = lock_tool()
    entries = tool.read_lock()
    entries[0][field] = value
    path = tmp_path / "bundle.lock.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(SystemExit):
        tool.read_lock(path)


@pytest.mark.parametrize("kind", ["broken", "duplicate", "unsorted", "not-an-array", "missing"])
def test_the_lock_has_one_sorted_entry_per_distribution(kind, tmp_path):
    tool = lock_tool()
    entries = tool.read_lock()
    payload = {"broken": "{", "duplicate": json.dumps(entries + entries[:1]),
               "unsorted": json.dumps(entries[::-1]), "not-an-array": "{}",
               "missing": '[{"name":"xmlschema"}]'}[kind]
    path = tmp_path / "bundle.lock.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(SystemExit):
        tool.read_lock(path)


def test_requirements_are_generated_with_the_locked_urls_and_hashes(tmp_path):
    tool = lock_tool()
    entries = tool.read_lock()
    out = tmp_path / "requirements.txt"
    tool.requirements(entries, out)
    assert out.read_text(encoding="utf-8").splitlines() == [
        f"{e['name']} @ {e['url']} --hash=sha256:{e['sha256']}" for e in entries]


def test_environment_markers_cannot_hide_an_unlocked_requirement():
    from email import message_from_string
    tool = lock_tool()
    entries = tool.read_lock()
    meta = message_from_string('Requires-Dist: unknown; python_version < "3.8"\n')
    with pytest.raises(SystemExit, match="unknown.*outside the lock"):
        tool.check_requirements(meta, entries)
    tool.check_requirements(message_from_string('Requires-Dist: unknown; extra == "docs"\n'), entries)


def test_an_extra_on_a_required_distribution_cannot_escape_the_lock():
    from email import message_from_string
    with pytest.raises(SystemExit, match="extra"):
        lock_tool().check_requirements(message_from_string('Requires-Dist: xmlschema[docs]\n'),
                                       lock_tool().read_lock())
