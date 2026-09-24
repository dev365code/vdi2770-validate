"""A file cut short is not read as an archive it happened to hold.

The archive library finds an archive by its end record, searching back from the
end of the file, and counts whatever comes before that archive as a prefix to
skip -- the way a self-extracting archive is read. A container that stores a
document container without compressing it, as the sample corpus's documentation
container does, ends in that document container when it is cut short at the
right length, and it was read, and passed, as that document container: a clean
verdict on a file nobody delivered. Bytes put in
front of a whole archive were skipped the same way.
"""
import pytest
from vdi2770_validate.runner import check_file

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION


def _fired(tmp_path, data):
    path = tmp_path / "delivery.zip"
    path.write_bytes(data)
    return {f.rule.id for f in check_file(str(path)).findings}


@pytest.mark.parametrize("length", [108_266, 150_084, 173_802])
def test_a_documentation_container_cut_short_is_not_the_container_it_holds(tmp_path, length):
    data = CLEAN_DOCUMENTATION.read_bytes()
    assert length < len(data), "the premise: this is a cut, not the whole file"
    assert "Z1" in _fired(tmp_path, data[:length])


def test_bytes_in_front_of_an_archive_are_not_skipped(tmp_path):
    assert "Z1" in _fired(tmp_path, b"not part of any archive. " * 8 + CLEAN_DOCUMENT.read_bytes())


def test_bytes_in_front_of_an_archive_with_nothing_in_it_are_not_skipped(tmp_path):
    """No entry to say where the archive starts: the file has to begin with a
    ZIP record of its own."""
    empty = b"PK\x05\x06" + b"\x00" * 18
    assert "Z1" in _fired(tmp_path, b"not part of any archive. " + empty)


def test_the_whole_containers_are_read_as_they_were(tmp_path):
    for clean in (CLEAN_DOCUMENT, CLEAN_DOCUMENTATION):
        assert "Z1" not in _fired(tmp_path, clean.read_bytes()), clean.name
