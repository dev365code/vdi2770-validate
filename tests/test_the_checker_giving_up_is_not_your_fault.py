"""Two different failures wore one flag, and one of them blamed the wrong party.

`xsdvalidate.validate` returned `broken: True` when the bundled schema would not
load — genuinely ours — and also when `iter_errors` blew up part-way through
somebody's document. The second case is annotated "hostile input" in the source
and was reported as `X0`, whose remedy is *"Check the installation … Re-install
with pip"* and whose `whyOurs` says *"This is about us, not about the
container."* Re-installing does not help a document nested a thousand levels
deep, and the whole point of this project's obligation vocabulary is not to say
that sort of thing.
"""
import io
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.catalog import rule
from vdi2770_validate.runner import check_file

DEEP = (b'<Document xmlns="http://www.vdi.de/schemas/vdi2770">'
        + b"<a>" * 1001 + b"</a>" * 1001 + b"</Document>")


def build(tmp_path, name, metadata):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", metadata)
        z.writestr("a.pdf", b"%PDF-1.7\n")
    p.write_bytes(buf.getvalue())
    return str(p)


def findings(path):
    return {f.rule.id: f for f in check_file(path).findings}


def test_a_document_the_checker_cannot_finish_is_not_a_broken_installation(tmp_path):
    got = findings(build(tmp_path, "deep.zip", DEEP))
    assert "X4" in got, sorted(got)
    assert "X0" not in got, "the container was blamed on our installation"
    assert "depth" in (got["X4"].detail or "").lower(), got["X4"].detail


def test_that_finding_does_not_tell_the_user_to_reinstall(tmp_path):
    remedy = findings(build(tmp_path, "deep2.zip", DEEP))["X4"].remedy.lower()
    for wrong in ("re-install", "reinstall", "pip install", "dependency"):
        assert wrong not in remedy, f"the remedy says {wrong!r}: {remedy}"


def test_the_two_remedies_point_in_opposite_directions():
    """X0 is about this tool; X4 is about the document it was given. Neither may
    drift into the other's territory, which is what put them in one branch."""
    ours, theirs = rule("X0").remedy.lower(), rule("X4").remedy.lower()
    assert "install" in ours and "install" not in theirs
    assert "metadata" in theirs
    assert rule("X4").why_ours, "an `ours` rule has to say why"


def test_an_ordinary_schema_violation_is_still_a_schema_violation(tmp_path):
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    bad = src.read("VDI2770_Metadata.xml").replace(b"<ClassId>", b"<NotAThing>", 1) \
                                          .replace(b"</ClassId>", b"</NotAThing>", 1)
    got = findings(build(tmp_path, "bad.zip", bad))
    assert "X2" in got and not {"X0", "X4"} & set(got), sorted(got)


def test_a_broken_installation_is_still_ours(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_xmlschema(name, *a, **k):
        if name == "xmlschema":
            raise ImportError("no xmlschema here")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_xmlschema)
    got = findings(str(CLEAN_DOCUMENT))
    assert "X0" in got and "X4" not in got, sorted(got)


@pytest.mark.parametrize("path", [CLEAN_DOCUMENT])
def test_no_container_can_produce_x0(path):
    """`tools/rule_coverage.py` justifies X0 as "only fires when this tool's own
    installation is broken, which no container can cause". That sentence was
    false while the two cases shared a flag."""
    assert "X0" not in findings(str(path))
