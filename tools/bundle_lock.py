#!/usr/bin/env python3
"""Keep the third-party wheels carried by the single file and the page explicit.

    python tools/bundle_lock.py --check
    python tools/bundle_lock.py --set NAME==VERSION
    python tools/bundle_lock.py --requirements /tmp/bundle-requirements.txt

An update commit also records a CHANGELOG entry, the versions in both
THIRD_PARTY.md files, and measured corpus and fixture verdict changes on the
oldest supported Python and the Python the page carries. A dependency update
can change a judgment even when none of the rules changed.

The requirements file is generated rather than committed: this JSON is the
one list of accepted files. Checking it is offline; the installed distributions
must have the locked versions before their METADATA can speak for those wheels.
"""
from __future__ import annotations

import argparse
import email
import http.client
import io
import json
import re
import shlex
import urllib.request
import zipfile
from importlib import metadata
from pathlib import Path

try:
    from packaging.markers import Marker
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename
    from packaging.version import InvalidVersion, Version
except ImportError:
    raise SystemExit("install packaging before reading the bundle lock") from None

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tools/bundle.lock.json"
FIELDS = {"name", "version", "file", "url", "sha256", "size", "requires_python", "tags"}


def distribution_name(spec: str) -> str:
    return canonicalize_name(re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip())


def validate(entries: list) -> list:
    if not isinstance(entries, list) or not entries:
        raise SystemExit("the bundle lock must be a nonempty array")
    names = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != FIELDS:
            raise SystemExit("each bundle lock entry must name exactly the wheel fields")
        if any(not isinstance(entry[k], str) or not entry[k]
               for k in ("name", "version", "file", "url", "sha256")):
            raise SystemExit("bundle names, versions, files, URLs and hashes must be nonempty strings")
        name = entry["name"]
        if name != distribution_name(name) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise SystemExit(f"{name} is not a normalized distribution name")
        names.append(name)
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise SystemExit(f"{name} needs a lowercase, 64-digit sha256")
        if type(entry["size"]) is not int or entry["size"] <= 0:
            raise SystemExit(f"{name} needs a positive wheel size")
        if not entry["url"].startswith("https://files.pythonhosted.org/packages/"):
            raise SystemExit(f"{name} needs a https://files.pythonhosted.org/packages/ URL")
        if not entry["url"].endswith("/" + entry["file"]):
            raise SystemExit(f"{name}'s URL does not name its wheel file")
        if entry["tags"] is not None:
            raise SystemExit(f"{name}: tags are reserved and must be null")
        requires_python = entry["requires_python"]
        if requires_python is not None:
            if not isinstance(requires_python, str) or not requires_python:
                raise SystemExit(f"{name}: requires_python must be a nonempty string or null")
            try:
                SpecifierSet(requires_python)
            except InvalidSpecifier as exc:
                raise SystemExit(f"{name}: invalid Requires-Python {requires_python}: {exc}") from None
        try:
            wheel_name, wheel_version, _build, tags = parse_wheel_filename(entry["file"])
            version = Version(entry["version"])
        except (InvalidWheelFilename, InvalidVersion) as exc:
            raise SystemExit(f"{name}: {exc}") from None
        if (distribution_name(wheel_name), str(wheel_version)) != (name, str(version)):
            raise SystemExit(f"{entry['file']} disagrees with the locked name or version")
        if {str(t) for t in tags} != {"py3-none-any"} or not entry["file"].endswith("-py3-none-any.whl"):
            raise SystemExit(f"{entry['file']}: this build takes only py3-none-any wheels")
    if names != sorted(set(names)):
        raise SystemExit("the bundle lock must be sorted by name without duplicates")
    return entries


def read_lock(path: Path = LOCK) -> list:
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read the bundle lock: {exc}") from None
    return validate(entries)


def check_extra(entries: list) -> None:
    reader = (ROOT / "packages/vdi2770/pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^validate\s*=\s*\[(.*?)\]", reader, re.M | re.S)
    specs = re.findall(r'"([^"]+)"', block.group(1)) if block else []
    schema = next((e["version"] for e in entries if e["name"] == "xmlschema"), None)
    if specs != [f"xmlschema=={schema}"]:
        raise SystemExit("the validate extra and the bundle lock must name the same xmlschema version")


def check_requirements(meta, entries: list) -> None:
    versions = {e["name"]: e["version"] for e in entries}
    for said in meta.get_all("Requires-Dist", []):
        try:
            req = Requirement(said)
        except InvalidRequirement as exc:
            raise SystemExit(f"invalid Requires-Dist {said}: {exc}") from None
        # No extras are requested by these bundles. Other markers are treated
        # as required even when false here: a file copied elsewhere must not
        # quietly acquire a dependency this build's interpreter did not need.
        if req.marker and not needed_without_extras(req.marker):
            continue
        name = distribution_name(req.name)
        if name not in versions:
            raise SystemExit(f"{said} requires {name} outside the lock")
        if req.extras or req.url:
            raise SystemExit(f"{said}: the bundle lock does not select extras or requirement URLs")
        if not req.specifier.contains(versions[name], prereleases=True):
            raise SystemExit(f"{said} does not accept locked {name} {versions[name]}")


def needed_without_extras(marker: Marker) -> bool:
    """Can this requirement apply with no extra, on any other environment?

    Keep extra comparisons and let every other comparison be true: even one
    possible environment makes it required. Split packaging's canonical text
    with quotes intact, then use its evaluator for the extra comparisons and
    the AND/OR structure, including parentheses and reversed operands.
    """
    tokens = shlex.shlex(str(marker), posix=False, punctuation_chars="()")
    tokens.whitespace_split = True
    projected, atom = [], []
    for token in [*tokens, "and"]:
        if token in ("and", "or") or token[0] in "()":
            if atom:
                projected.append(" ".join(atom) if "extra" in atom else 'extra == ""')
                atom = []
            projected.append(token)
        else:
            atom.append(token)
    return Marker(" ".join(projected[:-1])).evaluate(environment={"extra": ""})


def check_installed(entries: list) -> None:
    for entry in entries:
        try:
            meta = metadata.metadata(entry["name"])
        except metadata.PackageNotFoundError:
            raise SystemExit(f"install locked {entry['name']} before checking its METADATA; "
                             "run `make bundle-install`") from None
        if meta["Version"] != entry["version"]:
            raise SystemExit(f"installed {entry['name']} {meta['Version']} differs from locked {entry['version']}; "
                             "run `make bundle-install`")
        check_requirements(meta, entries)


def wheel_metadata(data: bytes, entry: dict, entries: list):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            directories = set()
            for name in wheel.namelist():
                parts = name.split("/")
                for i, part in enumerate(parts):
                    if part.endswith(".dist-info"):
                        directories.add("/".join(parts[:i + 1]))
            paths = sorted(directories)
            if len(paths) != 1:
                raise SystemExit(f"{entry['file']} has {len(paths)} dist-info directories; this build takes exactly one")
            if paths[0] != "-".join(entry["file"].split("-")[:2]) + ".dist-info":
                raise SystemExit(f"{entry['file']} dist-info directory name or version differs from the lock")
            metadata_path = paths[0] + "/METADATA"
            count = wheel.namelist().count(metadata_path)
            if count != 1:
                raise SystemExit(f"{entry['file']} has {count} METADATA files; this build takes exactly one")
            meta = email.message_from_bytes(wheel.read(metadata_path))
    except zipfile.BadZipFile as exc:
        raise SystemExit(f"{entry['file']} is not a wheel: {exc}") from None
    if (distribution_name(meta.get("Name", "")), meta.get("Version")) != (entry["name"], entry["version"]):
        raise SystemExit(f"{entry['file']} METADATA name or version differs from the lock")
    check_requirements(meta, entries)
    return meta


def requirements(entries: list, output: Path) -> None:
    output.write_text("".join(f"{e['name']} @ {e['url']} --hash=sha256:{e['sha256']}\n"
                              for e in entries), encoding="utf-8")


def set_version(spec: str) -> None:
    from build_zipapp import fetch, python_floor
    try:
        name, version = spec.split("==")
        name = distribution_name(name)
        Version(version)
    except ValueError:
        raise SystemExit("--set takes NAME==VERSION") from None
    entries = read_lock()
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=300) as answer:
            files = json.load(answer)["urls"]
    except (OSError, http.client.HTTPException) as exc:
        reason = " ".join(str(exc).split())
        raise SystemExit(f"cannot fetch PyPI metadata for {spec} from {url}: {reason}; "
                         "build from the existing lock with local copies via --wheels DIR, "
                         "--runtime FILE and --notices DIR") from None
    wheels = [f for f in files if f["packagetype"] == "bdist_wheel"]
    if len(wheels) != 1 or not wheels[0]["filename"].endswith("-py3-none-any.whl"):
        raise SystemExit(f"{spec}: this build takes one py3-none-any wheel")
    wheel = wheels[0]
    new = {"name": name, "version": version, "file": wheel["filename"], "url": wheel["url"],
           "sha256": wheel["digests"]["sha256"], "size": wheel["size"], "requires_python": None, "tags": None}
    candidate = sorted([e for e in entries if e["name"] != name] + [new], key=lambda e: e["name"])
    validate(candidate)
    check_extra(candidate)
    for entry in candidate:
        data = fetch(entry["url"], entry["sha256"], entry["file"])
        if len(data) != entry["size"]:
            raise SystemExit(f"{entry['file']} has size {len(data)}, and the lock takes only {entry['size']}")
        meta = wheel_metadata(data, entry, candidate)
        # A header with nothing after it states no requirement, and the lock
        # spells "none" as null: the empty string is what its own check refuses.
        requires_python = meta.get("Requires-Python") or None
        floor = python_floor()
        if requires_python and not SpecifierSet(requires_python).contains(floor, prereleases=True):
            raise SystemExit(f"{entry['file']}: Requires-Python {requires_python} excludes project Python floor {floor}")
        entry["requires_python"] = requires_python
    LOCK.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    action = ap.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--set", metavar="NAME==VER")
    action.add_argument("--requirements", type=Path, metavar="OUT")
    args = ap.parse_args()
    if args.set:
        set_version(args.set)
    else:
        entries = read_lock()
        check_extra(entries)
        if args.check:
            check_installed(entries)
            print("the bundle lock, validate extra and wheel requirements agree")
        else:
            requirements(entries, args.requirements)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
