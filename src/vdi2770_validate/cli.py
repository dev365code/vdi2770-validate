from __future__ import annotations

import argparse
import sys

from . import report as rendering
from .catalog import document_classes, rules
from .model import Severity
from .runner import check_file

VERSION = "0.1.0.dev0"


def _cmd_check(args) -> int:
    worst = 0
    for path in args.paths:
        rep = check_file(path)
        print(rendering.as_json(rep) if args.json else rendering.as_text(rep, not args.quiet))
        if rep.count(Severity.ERROR):
            worst = 1
    return worst


def _cmd_rules(_args) -> int:
    for r in sorted(rules().values(), key=lambda r: (r.layer, r.id)):
        print(f"{r.id:4} {r.severity.value:7} {r.layer:10} {r.title}")
        print(f"     basis={r.obligation.value}"
              + (f" refs={','.join(r.ref_codes)}" if r.ref_codes else ""))
    print(f"\n{len(rules())} rules")
    return 0


def _cmd_classes(_args) -> int:
    for cid, c in sorted(document_classes().items()):
        en = c["nameEn"]
        agree = "" if en["agree"] else "   [sources disagree]"
        print(f"{cid}  {c['nameDe']:42} {en['idta02004']}{agree}")
        if not en["agree"]:
            print(f"      IDTA 02004: {en['idta02004']!r}   reference impl: {en['ddcReference']!r}")
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
