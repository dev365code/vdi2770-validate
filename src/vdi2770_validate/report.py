"""Rendering. Every finding prints what to do about it — a validator that only
says 'invalid' has done half the job."""
from __future__ import annotations

import json
from typing import Dict, List

from .model import Report, Severity

MARK = {Severity.ERROR: "error", Severity.WARNING: "warn ", Severity.INFO: "info "}


def as_text(report: Report, show_info: bool = True) -> str:
    lines: List[str] = [f"{report.target}"]
    findings = [f for f in report.sorted() if show_info or f.severity is not Severity.INFO]
    if not findings:
        # "no findings" over a summary line reading "1 note(s)" is the report
        # contradicting itself, and a test pinned both halves of it.
        # count(), not len(findings): the listing is capped, the count is not,
        # and printing the capped number over an uncapped summary contradicts it.
        hidden = report.count(Severity.INFO)
        lines.append(f"  no errors or warnings ({hidden} note(s) not shown)" if hidden
                     else "  no findings")
    for f in findings:
        lines.append(f"  {MARK[f.severity]}  {f.rule.id}  {f.message}")
        lines.append(f"         at {f.where}")
        if f.detail:
            lines.append(f"         {f.detail}")
        # Every finding carries its remedy. Printing it once per rule saved a few
        # lines and quietly broke the promise the docs make.
        lines.append(f"         -> {f.remedy}")
    for rid, container, n in report.not_listed(show_info):
        lines.append(f"  ... {n} more {rid} finding{'' if n == 1 else 's'} in "
                     f"{container}, counted below but not listed")
    counts = {s: report.count(s) for s in Severity}
    lines.append("")
    lines.append(f"  {counts[Severity.ERROR]} error(s), {counts[Severity.WARNING]} warning(s), "
                 f"{counts[Severity.INFO]} note(s)")
    return "\n".join(lines)


def as_json(report: Report) -> str:
    payload: Dict = {
        "target": report.target,
        "tool": "vdi2770-validate",
        "pdfaVerified": False,
        "pdfaNote": "This tool reports PDF/A claims. It does not verify them.",
        "summary": {s.value: report.count(s) for s in Severity},
        # Counted in the summary above, and deliberately not listed below: one
        # rule can fire once per element, and four hundred thousand identical
        # findings serve nobody.
        "notListed": [{"rule": rid, "container": container, "count": n}
                      for rid, container, n in report.not_listed()],
        "findings": [
            {
                "rule": f.rule.id,
                "severity": f.severity.value,
                "layer": f.rule.layer,
                "obligation": f.rule.obligation.value,
                # Whether this is about the archive or about the validator
                # stopping. A CI consumer had no way to tell them apart.
                "about": f.about.value,
                "message": f.message,
                "detail": f.detail,
                "remedy": f.remedy,
                "refCodes": list(f.rule.ref_codes),
                "refKeys": list(f.rule.ref_keys),
                "where": {
                    "container": f.where.container,
                    "member": f.where.member,
                    "line": f.where.line,
                    "column": f.where.column,
                    "xpath": f.where.xpath,
                    "subject": f.where.subject,
                },
            }
            for f in report.sorted()
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
