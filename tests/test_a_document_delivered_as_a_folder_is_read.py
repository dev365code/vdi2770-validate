"""A document container delivered as a folder is read, not refused.

VDI 2770 hands documents over as document containers inside a documentation
container. Some deliveries put a document container's files in a folder of its
own instead of zipping them, and the reference implementation reads such a
folder as the document container it is: given the sample documentation
container with its one document container unpacked into a folder, it reports
nothing louder than a note. This tool said `Z13` -- documents delivered as
folders, which this tool does not open -- and checked nothing inside.

Held here: the same document container, zipped or unpacked into a folder, draws
the same findings. The folder draws `Z9` besides, which says the archive stores
files in folders, and nothing else may differ.
"""
import io
import zipfile
from collections import Counter

from vdi2770_validate.runner import check_bytes

from conftest import CLEAN_DOCUMENTATION


def _unpacked():
    """The sample documentation container with its one document container
    unpacked into a folder of the same name."""
    buf = io.BytesIO()
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as given, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name in given.namelist():
            if name != "documentcontainer.zip":
                out.writestr(name, given.read(name))
                continue
            with zipfile.ZipFile(io.BytesIO(given.read(name))) as inner:
                for part in inner.namelist():
                    out.writestr("documentcontainer/" + part, inner.read(part))
    return buf.getvalue()


def _verdict(data, *, leave_out=()):
    return Counter((f.rule.id, f.severity.value) for f in check_bytes(data, "delivery.zip").findings
                   if f.rule.id not in leave_out)


def test_a_document_container_in_a_folder_draws_what_it_draws_zipped():
    zipped = _verdict(CLEAN_DOCUMENTATION.read_bytes())
    folder = _verdict(_unpacked(), leave_out=("Z9",))
    assert folder == zipped, (
        f"unpacked into a folder: {sorted(folder.items())}; "
        f"zipped: {sorted(zipped.items())}")


def test_a_container_inside_a_document_container_is_one_zipped_or_not():
    """`Z11`: a document container carries another container inside it. A
    folder is a container that was not zipped, and `F2` says nothing about the
    files in one, so a rule that saw only `.zip` members let the same inner
    container through unpacked that it stopped zipped -- the check its reason
    says an inner container gets past."""
    from conftest import CLEAN_DOCUMENT

    def carrying(unpacked):
        buf = io.BytesIO()
        with zipfile.ZipFile(CLEAN_DOCUMENT) as outer, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for name in outer.namelist():
                out.writestr(name, outer.read(name))
            if not unpacked:
                out.writestr("inner.zip", CLEAN_DOCUMENT.read_bytes())
            else:
                with zipfile.ZipFile(CLEAN_DOCUMENT) as inner:
                    for name in inner.namelist():
                        out.writestr("inner/" + name, inner.read(name))
        return buf.getvalue()

    def z11(data):
        return [f.where.member for f in check_bytes(data, "delivery.zip").findings
                if f.rule.id == "Z11"]

    assert z11(carrying(unpacked=False)) == ["inner.zip"], "the premise"
    assert z11(carrying(unpacked=True)) == ["inner/"], "the same container unpacked went unremarked"
