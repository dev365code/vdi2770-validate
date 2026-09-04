"""The command line — the whole product, for most people who use it.

Three subcommands and one rule between them: a surprise is reported and the
sweep continues. A CI job pointed at a supplier drop folder must come back with
a verdict on every container it was given, not a traceback about the first one.

Exit codes: 0 no error, which is not the same as nothing wrong -- a warning
does not move the number, so a container can come back 0 with findings in the
report; 1 at least one error or unreadable path; 2 nothing could be read at all. A run whose reader goes away -- `| head` -- ends by
`SIGPIPE` where the platform has one and 141 where it does not, because it did
not finish: any of 0, 1 or 2 would be a claim about containers nobody looked at.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import sys

from . import __version__ as VERSION  # one place, not three
from . import report as rendering
from .catalog import document_classes, rules
from .model import Severity
from .runner import check_file


def _cmd_check(args) -> int:
    worst = 0
    unreadable = 0
    # `--json` is one document for the whole run. Printing one object per path
    # with no separator was neither JSON nor NDJSON, so the interface advertised
    # as machine-readable could not be read by a machine the moment a CI job
    # passed it a second container.
    documents = []
    for path in args.paths:
        try:
            rep = check_file(path)
        except Exception as e:              # noqa: BLE001
            # One bad path must not stop the rest: a CI job sweeping a supplier
            # drop folder would silently skip everything after the first dud.
            # Anything unexpected is this tool's failure to read that file, not
            # a verdict on it.
            #
            # `getattr`, not `e.strerror`: that attribute is on OSError and
            # nowhere else, so every other kind of surprise raised an
            # AttributeError out of the handler and stopped the sweep — which is
            # the one thing the handler exists to prevent. Keep it for the
            # OSError case, though; "No such file or directory" beats a repr.
            print(f"{path}: cannot read it — {getattr(e, 'strerror', None) or e}",
                  file=sys.stderr)
            unreadable += 1
            # And it appears in the JSON. Skipping it gave a consumer N-1
            # documents for N paths, with the difference explained only in prose
            # on another stream.
            documents.append({"path": path, "unreadable": str(e)})
            continue
        if args.json:
            documents.append({"path": path, **json.loads(rendering.as_json(rep, not args.quiet))})
        else:
            print(rendering.as_text(rep, not args.quiet))
        if rep.count(Severity.ERROR):
            worst = 1
    if args.json:
        print(_json_this_console_can_carry(documents))
    if unreadable:
        return 2 if unreadable == len(args.paths) else max(worst, 1)
    return worst


def _cmd_rules(_args) -> int:
    # Natural order, not lexical: sorting the ids as strings printed
    # Z1, Z10, Z11, Z12, Z2 to anybody running `rules`.
    def in_order(r):
        letters = r.id.rstrip("0123456789")
        return (r.layer, letters, int(r.id[len(letters):] or 0))

    for r in sorted(rules().values(), key=in_order):
        print(f"{r.id:4} {r.severity.value:7} {r.layer:10} {r.title}")
        print(f"     obligation={r.obligation.value}"
              + (f" refs={','.join(r.ref_codes)}" if r.ref_codes else ""))
    print(f"\n{len(rules())} rules")
    return 0


def _cmd_classes(_args) -> int:
    for cid, c in sorted(document_classes().items()):
        en, de = c["nameEn"], c["nameDe"]
        agree = "" if en["agree"] else "   [sources disagree]"
        print(f"{cid}  {de['idta02004']:42} {en['idta02004']}{agree}")
        if not en["agree"]:
            print(f"      English — IDTA 02004: {en['idta02004']!r}"
                  f"   reference impl: {en['ddcReference']!r}")
        if not de["agree"]:
            print(f"      German  — IDTA 02004: {de['idta02004']!r}"
                  f"   reference impl: {de['ddcReference']!r}")
    print("\nMatching is keyed on the class id and the German name; both sources agree on all "
          "twelve of those.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="vdi2770-validate",
        description="Check a VDI 2770 container, offline. Every finding comes with a remedy.")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="check one or more containers")
    c.add_argument("paths", nargs="+")
    c.add_argument("--json", action="store_true", help="machine-readable output")
    c.add_argument("--quiet", action="store_true", help="hide notes")
    c.set_defaults(func=_cmd_check)

    r = sub.add_parser("rules", help="list the rules this tool applies")
    r.set_defaults(func=_cmd_rules)

    k = sub.add_parser("classes", help="list the VDI 2770 document classes as this tool knows them")
    k.set_defaults(func=_cmd_classes)

    args = p.parse_args(argv)
    return args.func(args)


def _json_this_console_can_carry(payload) -> str:
    """JSON that stays JSON on a console that cannot encode it.

    `_survive_the_console` puts `errors="backslashreplace"` on stdout, so a
    character the console has no byte for is written `\\xNN`. The text report
    wants that -- it says something was there and says what. JSON has no such
    escape, and a member named `Prüfbericht.pdf` on a `cp932` or `cp949` or
    plain-ASCII console came out as

        "member": "Pr\\xfcfbericht.pdf"

    which stops `json.load` at *Invalid \\escape* -- with exit 0, so a sweep read
    as clean and its payload could not be opened. Only U+0080-U+00FF does this;
    anything above gets `\\uXXXX` from the same handler, which JSON accepts, so
    the accented Western European names this tool is most often pointed at were
    the ones that broke.

    Asked first whether the console can carry the text, because `ü` on a UTF-8
    or `cp1252` terminal is worth more to whoever is reading it than `\\u00fc`.
    When it cannot, `ensure_ascii` writes the same characters as escapes JSON
    does have -- including surrogate pairs above the BMP, which is why this
    re-renders rather than patching the string it already has.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        text = json.dumps(payload, ensure_ascii=True, indent=2)
    return text


def _survive_the_console() -> None:
    """Two ways the terminal, rather than the container, ended a run.

    A console that cannot encode the output. Every remedy in this tool contains
    an em dash and four class names contain umlauts, so on `cp850` or `cp437` --
    the OEM defaults of Windows `cmd.exe` -- `print` raised `UnicodeEncodeError`
    from outside the handler that exists so a CI job "must come back with a
    verdict on every container it was given, not a traceback about the first
    one". A conformant container came back as a traceback and exit 1, this
    tool's code for *at least one error*, and the sweep died on the first path.
    `backslashreplace` rather than `replace`: `\u2014` says something was there
    and says what, where `?` does not.

    And a reader that stops reading. `| head` closes the pipe, and `print` then
    raised `BrokenPipeError` from the same place -- two tracebacks on the way
    down, exit 120 with text output and exit **1** with `--json`, for four
    hundred containers that had nothing wrong. Restoring the default disposition
    hands that back to the operating system, which is what every other tool in
    the pipeline does.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):   # not a text file
                reconfigure(errors="backslashreplace")
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def _run(argv=None) -> int:
    """`main` with the console handled. The entry points call this."""
    _survive_the_console()
    try:
        return main(argv)
    except BrokenPipeError:
        # Only where there is no `SIGPIPE` to restore. Send the rest of our
        # output somewhere harmless so the interpreter's shutdown flush does not
        # print a second complaint about the pipe that has already gone.
        # Closed after the duplicate is made. `dup2` does not close its source,
        # so the descriptor stayed open -- harmless in a process about to exit,
        # and the kind of thing that stops being harmless the moment this is
        # called from somewhere that does not exit.
        spare = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(spare, sys.stdout.fileno())
        finally:
            os.close(spare)
        return 141


if __name__ == "__main__":
    sys.exit(_run())
