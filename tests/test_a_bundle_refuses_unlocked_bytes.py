"""A local wheel directory is transport, never an alternative dependency list."""
import importlib
import sys
import zipfile

import pytest

from bundle_wheels import wheels_at
from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
BUILD = importlib.import_module("build_zipapp")
LOCK = importlib.import_module("bundle_lock")
PAGE = importlib.import_module("build_browser")


@pytest.fixture
def local_wheels(tmp_path, monkeypatch):
    folder = tmp_path / "wheels"
    entries = wheels_at(folder)
    monkeypatch.setattr(LOCK, "read_lock", lambda: LOCK.validate(entries))
    return folder, entries


def test_a_wheel_with_the_right_name_and_wrong_digest_is_refused(local_wheels, tmp_path):
    folder, entries = local_wheels
    entry = entries[0]
    (folder / entry["file"]).write_bytes(b"another wheel")
    with pytest.raises(SystemExit, match=rf"{entry['file']} has sha256 .*, and this build takes only {entry['sha256']}"):
        BUILD.stage(tmp_path / "app", wheels=folder)
    assert not (tmp_path / "app/__main__.py").exists()


def test_a_wheel_cannot_require_a_distribution_outside_the_lock(tmp_path, monkeypatch):
    folder = tmp_path / "wheels"
    entries = wheels_at(folder, requirement="somethingelse>=1")
    monkeypatch.setattr(LOCK, "read_lock", lambda: entries)
    with pytest.raises(SystemExit, match="somethingelse.*outside the lock"):
        BUILD.stage(tmp_path / "app", wheels=folder)


def test_a_wheel_cannot_claim_another_version_in_metadata(local_wheels, tmp_path):
    folder, entries = local_wheels
    import hashlib
    entry = entries[0]
    path = folder / entry["file"]
    # Replace inside a real zip rather than corrupting its central directory.
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n).replace(b"Version: 5.1.4", b"Version: 5.1.3") for n in z.namelist()}
    with zipfile.ZipFile(path, "w") as z:
        for name, body in parts.items():
            z.writestr(name, body)
    body = path.read_bytes()
    entry.update(sha256=hashlib.sha256(body).hexdigest(), size=len(body))
    with pytest.raises(SystemExit, match="METADATA name or version"):
        BUILD.stage(tmp_path / "app", wheels=folder)


def test_the_locked_size_is_checked_too(local_wheels, tmp_path):
    folder, entries = local_wheels
    entries[0]["size"] += 1
    with pytest.raises(SystemExit, match="has size.*takes only"):
        BUILD.stage(tmp_path / "app", wheels=folder)


def test_a_missing_local_wheel_does_not_fall_back_to_the_network(local_wheels, tmp_path, monkeypatch):
    folder, entries = local_wheels
    (folder / entries[0]["file"]).rename(folder / "different.whl")
    monkeypatch.setattr(BUILD.urllib.request, "urlopen", lambda *a, **k: pytest.fail("local mode fetched a wheel"))
    with pytest.raises(SystemExit, match="cannot read.*whl"):
        BUILD.stage(tmp_path / "app", wheels=folder)


def test_staging_uses_the_lock_without_a_pip_subprocess(local_wheels, tmp_path, monkeypatch):
    folder, entries = local_wheels
    monkeypatch.setattr(BUILD.subprocess, "run", lambda *a, **k: pytest.fail("staging invoked pip"))
    into = tmp_path / "app"
    notices = []
    BUILD.stage(into, wheels=folder, notices=notices)
    assert [n["name"] for n in notices] == [e["name"] for e in entries]
    assert [n["version"] for n in notices] == [e["version"] for e in entries]
    assert all(n["licence"] == "MIT" for n in notices)
    assert all(n["texts"] == {"licenses/LICENSE": "the MIT text\n"} for n in notices)
    assert not list(into.glob("*.dist-info"))
    assert (into / "xmlschema/__init__.py").read_text() == "__version__ = '4.2.0'\n"


def test_building_twice_from_local_wheels_produces_identical_zipapps(local_wheels, tmp_path):
    folder, _entries = local_wheels
    outputs = []
    for n in range(2):
        staged = tmp_path / f"stage-{n}"
        BUILD.stage(staged, wheels=folder)
        target = tmp_path / f"{n}.pyz"
        BUILD.create_archive(staged, target)
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1]


@pytest.mark.skipif(sys.version_info[:2] != (3, 13), reason="the page is built on the Python 3.13 it carries")
def test_building_twice_from_local_wheels_produces_identical_pages(local_wheels, tmp_path, monkeypatch):
    folder, _entries = local_wheels
    monkeypatch.setattr(PAGE, "fetch", lambda *a, **k: b"runtime notice\n")
    monkeypatch.setattr(PAGE, "runtime_files", lambda data: dict.fromkeys(PAGE.RUNTIME_FILES, b"runtime file"))
    monkeypatch.setattr(PAGE, "notice_text", lambda data, between=None: data.decode())
    first = PAGE.build(tmp_path / "one.html", wheels=folder)
    second = PAGE.build(tmp_path / "two.html", wheels=folder)
    assert first == second


def test_reproducibility_compares_bytes_even_when_sizes_agree(local_wheels, tmp_path, monkeypatch):
    """Exercise the equality assertion with an equal-length changed page.

    A comparison weakened to file size has to fail this control before it can
    call a second build reproducible.
    """
    if sys.version_info[:2] != (3, 13):
        pytest.skip("the page is built on the Python 3.13 it carries")
    original = PAGE.build
    calls = []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        return result if len(calls) == 1 else bytes([result[0] ^ 1]) + result[1:]

    monkeypatch.setattr(PAGE, "build", changed)
    with pytest.raises(AssertionError):
        test_building_twice_from_local_wheels_produces_identical_pages(local_wheels, tmp_path, monkeypatch)


def test_the_page_refuses_a_builder_from_another_python_before_fetching(tmp_path, monkeypatch):
    monkeypatch.setattr(PAGE.platform, "python_version", lambda: "3.12.9")
    monkeypatch.setattr(PAGE, "fetch", lambda *a, **k: pytest.fail("refusal fetched an asset"))
    with pytest.raises(SystemExit, match="Python 3.12.9.*takes only Python 3.13"):
        PAGE.build(tmp_path / "page.html")
    assert not (tmp_path / "page.html").exists()


def test_patch_versions_of_the_pages_python_are_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(PAGE.platform, "python_version", lambda: "3.13.15")
    # Stop at the first fetch: the interpreter gate already made its decision.
    monkeypatch.setattr(PAGE, "fetch", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("accepted")))
    with pytest.raises(RuntimeError, match="accepted"):
        PAGE.build(tmp_path / "page.html")
