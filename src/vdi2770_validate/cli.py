from __future__ import annotations

import argparse
import sys

from . import __version__ as VERSION  # one place, not three
from . import report as rendering
from .catalog import document_classes, rules
from .model import Severity
from .runner import check_file


def _cmd_check(args) -> int:
    worst = 0
    unreadable = 0
    for path in args.paths:
        try:
            rep = check_file(path)
        except OSError as e:
            # One bad path must not stop the rest: a CI job sweeping a supplier
            # drop folder would silently skip everything after the first dud.
            print(f"{path}: cannot read it — {e.strerror or e}", file=sys.stderr)
            unreadable += 1
            continue
        print(rendering.as_json(rep) if args.json else rendering.as_text(rep, not args.quiet))
        if rep.count(Severity.ERROR):
            worst = 1
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
        print(f"     basis={r.obligation.value}"
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


if __name__ == "__main__":
    sys.exit(main())
