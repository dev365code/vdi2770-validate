"""Zero network, by design and by proof.

A validator that runs inside a plant network must never let a supplier archive
decide which host this machine reaches.
"""
import socket

# At module scope, and deliberately. Patching `socket.socket` to a function and
# *then* importing this breaks `class SSLSocket(socket)` inside the standard
# library, which made this file fail whenever it was run on its own -- the whole
# suite only passed because some earlier test had already imported ssl. A test
# whose result depends on what ran before it is not a test.
import urllib.request  # noqa: F401

import pytest

from conftest import CLEAN_DOCUMENTATION, FIXTURES
from vdi2770_validate.runner import check_file


class ReachedForTheNetwork(BaseException):
    """Not an `Exception`, deliberately.

    Both the tool's schema loader and its rule runner wrap work in
    `except Exception` and turn what they catch into a finding -- which is right
    for hostile input and fatal for a test whose subject is "this must never
    happen": an `AssertionError` raised inside the guard was caught, converted
    to `X0`, and the run finished clean on both sides of the comparison. The
    guard has to raise something the code under test cannot swallow.
    """


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise ReachedForTheNetwork("the tool tried to open a socket")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def test_the_guard_is_live(no_network):
    """`assert rep is not None` was the whole of the test below. If the fixture
    ever stops patching, that assertion still passes and the offline promise is
    unguarded, so the fixture is checked before it is relied on."""
    with pytest.raises(ReachedForTheNetwork, match="tried to open a socket"):
        socket.socket()


def test_validating_touches_no_socket(no_network):
    """The fixture is function-scoped, so it is active for the whole test.

    The version before this one ran `check_file` twice inside it and compared
    the results, with the second variable named `monkeypatch_free` — both runs
    were under the same patch, so it compared a run to itself and could not fail
    on the axis its name described. The real comparison has to leave the fixture
    behind, so it happens in the test below."""
    guarded = [f.rule.id for f in check_file(str(CLEAN_DOCUMENTATION)).sorted()]
    assert guarded, "expected findings to compare, not merely a report object"


def test_the_verdict_is_the_same_with_and_without_a_network():
    """No fixture here on purpose: one run with sockets forbidden, one with them
    as they are. A tool that quietly reaches the network would differ."""
    import socket as real_socket

    def refuse(*a, **k):
        raise AssertionError("the tool tried to open a socket")

    saved = {n: getattr(real_socket, n) for n in ("socket", "create_connection", "getaddrinfo")}
    try:
        for n, f in ((n, refuse) for n in saved):
            setattr(real_socket, n, f)
        guarded = [f.rule.id for f in check_file(str(CLEAN_DOCUMENTATION)).sorted()]
    finally:
        for n, f in saved.items():
            setattr(real_socket, n, f)
    free = [f.rule.id for f in check_file(str(CLEAN_DOCUMENTATION)).sorted()]
    assert guarded and guarded == free, "the verdict changes when the network is unavailable"


def test_schema_location_is_not_dereferenced(monkeypatch, no_network):
    """The corpus metadata carries xsi:schemaLocation. We validate against the
    bundled schema and must never fetch what the document points at — and the
    verdict must be the same whether or not the network exists, which is the
    part the old version of this test forgot to check."""
    def refuse(*a, **k):
        raise ReachedForTheNetwork("the tool tried to open a URL")

    # Cleared *inside* the guard, because the schema is compiled once and held:
    # in a full-suite run whichever test touched it first did the compiling, and
    # this test -- whose whole subject is what happens during that compile --
    # was measuring a cache hit. `make standalone` still exercised it, so the
    # coverage was not lost, only silently order-dependent.
    from vdi2770_validate import xsdvalidate

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    xsdvalidate._schema.cache_clear()
    guarded = [f.rule.id for f in check_file(str(CLEAN_DOCUMENTATION)).sorted()]
    monkeypatch.undo()
    free = [f.rule.id for f in check_file(str(CLEAN_DOCUMENTATION)).sorted()]
    assert guarded == free, "the verdict changes when the network is unavailable"
    assert guarded, "expected at least one finding to compare"


def test_entity_expansion_is_refused_not_fetched(no_network):
    rep = check_file(str(FIXTURES / "x3-entity-expansion.zip"))
    assert "X3" in {f.rule.id for f in rep.findings}
