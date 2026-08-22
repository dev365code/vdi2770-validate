"""Zero network, by design and by proof.

A validator that runs inside a plant network must never let a supplier archive
decide which host this machine reaches.
"""
import socket

import pytest

from conftest import CLEAN_DOCUMENTATION, FIXTURES
from vdi2770_validate.runner import check_file


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the tool tried to open a socket")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def test_validating_touches_no_socket(no_network):
    rep = check_file(str(CLEAN_DOCUMENTATION))
    assert rep is not None


def test_schema_location_is_not_dereferenced(no_network):
    """The corpus metadata carries xsi:schemaLocation. We validate against the
    bundled schema and must never fetch what the document points at."""
    rep = check_file(str(CLEAN_DOCUMENTATION))
    assert rep.target.endswith(".zip")


def test_entity_expansion_is_refused_not_fetched(no_network):
    rep = check_file(str(FIXTURES / "x3-entity-expansion.zip"))
    assert "X3" in {f.rule.id for f in rep.findings}
