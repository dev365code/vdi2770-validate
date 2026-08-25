"""Watch for a socket at the interpreter's own boundary, not at a name.

The guard this replaces monkeypatched three names on the `socket` module. A
caller that binds the constructor before the patch — `from socket import socket
as _sock`, at import time — reaches a different object, and connecting to a
literal IP never consults `getaddrinfo` either. Proved: a `connect()` to
192.0.2.1 inside `check_bytes` left the whole suite green while `sys.addaudithook`
recorded `socket.__new__` and `socket.connect`.

This is the same lesson `nodisk.py` records for `io.open`, and the disk promise
moved to the audit boundary while the network promise stayed at the name.

`sys.addaudithook` sees the event whichever name reached it. A hook cannot be
uninstalled once added, so this one is installed once and gated on a flag; off,
it costs one boolean per event.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import List, Tuple

_REACHES: List[Tuple[str, str]] = []
_WATCHING = False
_INSTALLED = False

#: Every audited event that means the process reached for a network. Creating a
#: socket counts: a tool that opens one and falls back quietly on failure has
#: still gone looking, which is the distinction SECURITY.md draws.
_NETWORK = ("socket.__new__", "socket.connect", "socket.bind", "socket.getaddrinfo",
            "socket.gethostbyname", "socket.sendto",
            "http.client.connect", "http.client.send",
            "ftplib.connect", "smtplib.connect")

#: `urllib.Request` is deliberately not in that list. It fires for `file://`
#: too, and the bundled schema validator builds one per meta-schema it loads
#: from disk — ten on an ordinary run. Anything that actually leaves the machine
#: opens a socket, so the socket events catch it without the false alarm.


def _hook(event: str, args) -> None:
    if _WATCHING and event in _NETWORK:
        _REACHES.append((event, repr(args)[:200]))


@contextmanager
def no_network():
    """Fail if anything inside reaches for a network in any way the interpreter
    reports."""
    global _WATCHING, _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True
    _REACHES.clear()
    _WATCHING = True
    try:
        yield _REACHES
    finally:
        _WATCHING = False
    assert not _REACHES, ("reached for the network:\n  "
                          + "\n  ".join(f"{e}: {d}" for e, d in _REACHES))


def hook_is_working() -> bool:
    """The canary. A guard nobody has seen fire is a guard nobody should trust."""
    import socket as _socket
    global _WATCHING, _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True
    _REACHES.clear()
    _WATCHING = True
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.close()
        seen = list(_REACHES)
    finally:
        _WATCHING = False
        _REACHES.clear()
    return any(e == "socket.__new__" for e, _ in seen)
