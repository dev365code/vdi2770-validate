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
    ZIP record of its own, whether or not the archive counts what comes first."""
    empty = b"PK\x05\x06" + b"\x00" * 18
    front = b"not part of any archive. "
    assert "Z1" in _fired(tmp_path, front + empty)
    assert "Z1" in _fired(tmp_path, _owning(front, empty))


def _owning(front, archive):
    """`archive` with `front` before it and every offset it records moved past
    `front`, so the archive counts those bytes as its own -- the way `zip -s`
    writes a split archive that fits in one file, and `zip -A` a stub."""
    import struct

    data = bytearray(front + archive)
    end = data.rindex(b"PK\x05\x06")
    count, _size, offset = struct.unpack("<HII", data[end + 10:end + 20])
    struct.pack_into("<I", data, end + 16, offset + len(front))
    at = offset + len(front)
    for _ in range(count):
        assert data[at:at + 4] == b"PK\x01\x02"
        (header,) = struct.unpack("<I", data[at + 42:at + 46])
        struct.pack_into("<I", data, at + 42, header + len(front))
        name, extra, comment = struct.unpack("<HHH", data[at + 28:at + 34])
        at += 46 + name + extra + comment
    return bytes(data)


@pytest.mark.parametrize("marker", [b"PK\x07\x08", b"PK00"])
def test_a_split_archive_small_enough_to_be_one_file_is_read_as_it_is(tmp_path, marker):
    """A split archive that fits in one file begins with a marker before its
    first entry (APPNOTE 8.5.3 and 8.5.4), and `zip -s` writes one: the
    offsets it records count those four bytes, which are the archive's own."""
    whole = _fired(tmp_path, CLEAN_DOCUMENT.read_bytes())
    assert _fired(tmp_path, _owning(marker, CLEAN_DOCUMENT.read_bytes())) == whole


@pytest.mark.parametrize("marker", [b"PK\x07\x08", b"PK00"])
def test_a_split_marker_put_in_front_of_an_archive_is_not_its_own(tmp_path, marker):
    """The same four bytes in front of an archive that does not count them are
    bytes in front of it, like any others."""
    assert "Z1" in _fired(tmp_path, marker + CLEAN_DOCUMENT.read_bytes())


def test_an_archive_after_another_that_it_counts_as_its_own_is_not_the_file(tmp_path):
    """A file that begins with one archive and ends with another, which counts
    the first as its own: what is read is the second, and the file does not
    begin with its first entry."""
    first = CLEAN_DOCUMENT.read_bytes()
    assert "Z1" in _fired(tmp_path, _owning(first, CLEAN_DOCUMENT.read_bytes()))


def test_an_archive_that_counts_a_stub_in_front_as_its_own_is_not_a_zip(tmp_path):
    """A self-extracting stub, even one the archive's offsets count: the file
    does not begin with the archive, and what is delivered is not a ZIP."""
    stub = b"#!/bin/sh\nexit 0\n" * 4
    assert "Z1" in _fired(tmp_path, _owning(stub, CLEAN_DOCUMENT.read_bytes()))


def test_an_empty_archive_may_begin_with_its_zip64_record(tmp_path):
    """An archive with nothing in it can be written as zip64, which begins with
    that end record. It has no document to check, and it says so; it is not
    a file that fails to begin with a ZIP record."""
    import struct

    record = struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0, 0, 0, 0, 0)
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, 0, 1)
    end = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF,
                      0xFFFFFFFF, 0xFFFFFFFF, 0)
    assert "Z1" not in _fired(tmp_path, record + locator + end)


def test_the_whole_containers_are_read_as_they_were(tmp_path):
    for clean in (CLEAN_DOCUMENT, CLEAN_DOCUMENTATION):
        assert "Z1" not in _fired(tmp_path, clean.read_bytes()), clean.name
