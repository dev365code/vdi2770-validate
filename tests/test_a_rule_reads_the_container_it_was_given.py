"""`is_main` was a boolean the runner computed and handed to the metadata rules.
It was a restatement of state the rule already had.

Not an exactly equivalent one, which is worth writing down: a refused
`VDI2770_Main.xml` still classifies the archive as a documentation container
while `metadata_name` stays None, so the two *can* disagree — reproduced below.
They agree wherever the rule runs, because the runner does not reach it without
metadata it parsed. Reading the container is the version that stays true if that
stops being so.

A boolean argument is usually two functions. This one was neither — it was one
function being told something it could see.
"""
import inspect

from conftest import FIXTURES
from vdi2770_validate.rules import files as r_files
from vdi2770_validate.rules import metadata as r_metadata
from vdi2770_validate.runner import check_file


def fired(name):
    return {f.rule.id for f in check_file(str(FIXTURES / name)).findings}


def test_m7_still_fires_on_a_documentation_container_that_is_not_released():
    assert "M7" in fired("m7-main-not-released.zip")


def test_m7_does_not_fire_inside_a_document_container():
    """The rule is about the *main* document. A document container's own
    metadata carries a LifeCycleStatus too, and it is not the main document."""
    from conftest import CLEAN_DOCUMENT
    assert "M7" not in {f.rule.id for f in check_file(str(CLEAN_DOCUMENT)).findings}


def test_the_two_document_level_rule_modules_take_the_same_arguments():
    """They answer the same question about the same two things. One taking a
    third argument meant the runner had to know which rule needed what."""
    assert (list(inspect.signature(r_metadata.check).parameters)
            == list(inspect.signature(r_files.check).parameters))


def test_the_two_can_disagree_where_the_rule_does_not_run(monkeypatch):
    """The claim that replaced `is_main` is "read the container", not "they are
    the same thing". Here they are not."""
    import io
    import zipfile

    from vdi2770 import Kind, zipread

    monkeypatch.setattr(zipread, "MAX_METADATA_BYTES", 32)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'/>")
        z.writestr("VDI2770_Main.pdf", b"%PDF-1.7\n")
    box = zipread.read(buf.getvalue(), "x.zip")

    assert box.kind is Kind.DOCUMENTATION
    assert box.metadata_name is None, "the refused member left no metadata name"
    assert box.metadata_bytes is None, "and the rule below is never reached for it"
