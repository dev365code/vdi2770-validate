"""The lock describes the bytes carried across, including transitive requirements."""
import importlib
import io
import json
import sys

import pytest

from bundle_wheels import wheels_at
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
    ("tags", ["py3-none-any"]), ("requires_python", "not a specifier"),
    ("file", "elementpath-5.1.4-cp313-none-any.whl"),
])
def test_a_malformed_lock_is_refused(field, value, tmp_path):
    tool = lock_tool()
    entries = tool.read_lock()
    if field == "url":
        value = value.replace("a.whl", entries[0]["file"])
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


def test_an_extra_alternative_does_not_hide_a_required_dependency():
    from email import message_from_string
    meta = message_from_string('Requires-Dist: unknown; extra == "docs" or python_version >= "3.9"\n')
    with pytest.raises(SystemExit, match="unknown.*outside the lock"):
        lock_tool().check_requirements(meta, lock_tool().read_lock())


def test_an_extra_on_a_required_distribution_cannot_escape_the_lock():
    from email import message_from_string
    with pytest.raises(SystemExit, match="extra"):
        lock_tool().check_requirements(message_from_string('Requires-Dist: xmlschema[docs]\n'),
                                       lock_tool().read_lock())


@pytest.mark.parametrize("version,filename,accepted", [
    ("5.2.0", "elementpath-5.2.0-py3-none-any.whl", True),
    ("6.1.0", "elementpath-6.1.0-py3-none-any.whl", False),
    ("5.2.0", "elementpath-5.2.0-cp313-none-any.whl", False),
])
def test_an_update_checks_the_entire_candidate_before_writing(version, filename, accepted, tmp_path, monkeypatch):
    tool = lock_tool()
    current = wheels_at(tmp_path / "current")
    candidate = wheels_at(tmp_path / "candidate", element_version=version)
    new = candidate[0]
    monkeypatch.setattr(tool, "read_lock", lambda: current)
    output = tmp_path / "bundle.lock.json"
    output.write_text("unchanged\n", encoding="utf-8")
    monkeypatch.setattr(tool, "LOCK", output)
    response = {"urls": [{"packagetype": "bdist_wheel", "filename": filename,
                          "url": new["url"], "digests": {"sha256": new["sha256"]}, "size": new["size"]}]}
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(response).encode()))
    import build_zipapp
    payloads = {e["url"]: (tmp_path / "candidate" / e["file"]).read_bytes() for e in candidate}
    monkeypatch.setattr(build_zipapp, "fetch", lambda url, *args: payloads[url])
    if accepted:
        tool.set_version(f"elementpath=={version}")
        assert json.loads(output.read_text(encoding="utf-8"))[0] == new
    else:
        with pytest.raises(SystemExit):
            tool.set_version(f"elementpath=={version}")
        assert output.read_text(encoding="utf-8") == "unchanged\n"


def test_normalized_metadata_names_are_compared_as_distribution_names(tmp_path):
    tool = lock_tool()
    entries = wheels_at(tmp_path)
    assert tool.distribution_name("Some_Package>=1") == "some-package"
    import zipfile
    with zipfile.ZipFile(tmp_path / entries[1]["file"]) as z:
        from email import message_from_bytes
        meta = message_from_bytes(z.read("xmlschema-4.2.0.dist-info/METADATA"))
    for name, accepted in [("XMLSchema", True), ("somethingelse", False)]:
        meta.replace_header("Name", name)
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as z:
            z.writestr("xmlschema-4.2.0.dist-info/METADATA", meta.as_bytes())
        if accepted:
            assert tool.wheel_metadata(raw.getvalue(), entries[1], entries)["Name"] == name
        else:
            with pytest.raises(SystemExit, match="METADATA name or version"):
                tool.wheel_metadata(raw.getvalue(), entries[1], entries)


def test_an_installed_version_mismatch_says_how_to_install_the_lock(monkeypatch):
    tool = lock_tool()
    monkeypatch.setattr(tool.metadata, "metadata", lambda name: {"Version": "99.0"})
    with pytest.raises(SystemExit, match=r"differs from locked 5\.0\.4; run `make bundle-install`"):
        tool.check_installed(tool.read_lock())


def test_an_update_refuses_metadata_that_excludes_the_projects_python_floor(tmp_path, monkeypatch):
    tool = lock_tool()
    entries = [dict(e, requires_python=None) for e in wheels_at(tmp_path, requires_python=">=3.10")]
    monkeypatch.setattr(tool, "read_lock", lambda: entries)
    output = tmp_path / "bundle.lock.json"
    output.write_text("unchanged\n", encoding="utf-8")
    monkeypatch.setattr(tool, "LOCK", output)
    new = entries[0]
    response = {"urls": [{"packagetype": "bdist_wheel", "filename": new["file"],
                          "url": new["url"], "digests": {"sha256": new["sha256"]}, "size": new["size"]}]}
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(response).encode()))
    import build_zipapp
    payloads = {e["url"]: (tmp_path / e["file"]).read_bytes() for e in entries}
    monkeypatch.setattr(build_zipapp, "fetch", lambda url, *args: payloads[url])
    with pytest.raises(SystemExit, match=r"Requires-Python >=3\.10.*project.*3\.9"):
        tool.set_version("elementpath==5.1.4")
    assert output.read_text(encoding="utf-8") == "unchanged\n"


def test_the_repeated_build_claim_names_each_artifacts_python_scope():
    said = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 0.12.0", 1)[0]
    assert "single file on any supported Python" in said
    assert "page built on the Python it carries (3.13)" in said
