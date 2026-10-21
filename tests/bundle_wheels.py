"""Small wheels for offline build tests; every altered wheel gets a new digest."""
import hashlib
import io
import zipfile


def wheels_at(folder, requirement="elementpath>=5,<6", version="4.2.0", element_version="5.1.4",
              requires_python=">=3.9"):
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, ver, needs in [("elementpath", element_version, ""), ("xmlschema", version, requirement)]:
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as z:
            info = f"{name}-{ver}.dist-info"
            z.writestr(f"{info}/METADATA", f"Metadata-Version: 2.4\nName: {name}\nVersion: {ver}\n"
                       f"Requires-Python: {requires_python}\nLicense-Expression: MIT\n"
                       + (f"Requires-Dist: {needs}\n" if needs else ""))
            z.writestr(f"{info}/licenses/LICENSE", "the MIT text\n")
            z.writestr(f"{name}/__init__.py", f"__version__ = {ver!r}\n")
        body = raw.getvalue()
        filename = f"{name}-{ver}-py3-none-any.whl"
        (folder / filename).write_bytes(body)
        entries.append({"name": name, "version": ver, "file": filename,
                        "url": f"https://files.pythonhosted.org/packages/ab/cd/{filename}",
                        "sha256": hashlib.sha256(body).hexdigest(), "size": len(body),
                        "requires_python": requires_python, "tags": None})
    return entries
