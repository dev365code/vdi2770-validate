"""Rendering. Every finding prints what to do about it — a validator that only
says 'invalid' has done half the job."""
from __future__ import annotations

import json
from typing import Dict, List

from .model import About, Report, Severity
from .names import as_written

MARK = {Severity.ERROR: "error", Severity.WARNING: "warn ", Severity.INFO: "info "}


def _where(location) -> str:
    """The location, with a member name that cannot forge lines of this report.

    `Location.__str__` interpolates the name the archive stored, and a member
    called `notes.txt\\n\\n  0 error(s)…\\n\\nsupplier-delivery.zip\\n  no findings`
    put a summary and a second container's clean verdict inside a finding. A
    supplier chose what a CI log appeared to say about somebody else's delivery.
    `as_json` was never affected; this is the page people read.

    `as_written`, not `escaped`: a newline draws nothing and gets spelled out,
    and an ordinary name -- decomposed Korean included -- is left exactly as the
    archive spells it, which is what a reader needs to find it in their listing.
    Running this line through `escaped` would hex every filename in every report
    from a delivery written on a Mac.
    """
    if location.member is None and not location.container:
        return str(location)
    shown = location.child(container=as_written(location.container),
                           member=None if location.member is None
                           else as_written(location.member))
    return str(shown)


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
        lines.append(f"         at {_where(f.where)}")
        if f.detail:
            lines.append(f"         {f.detail}")
        # Every finding carries its remedy. Printing it once per rule saved a few
        # lines and quietly broke the promise the docs make.
        lines.append(f"         -> {f.remedy}")
    for rid, container, n in report.not_listed(show_info):
        # `as_written`, like the `at` line above: this string is an archive's
        # own name and an inner container called `a\n\n  0 error(s)…` put a
        # forged summary on the page through this door after the other one was
        # closed.
        lines.append(f"  ... {n} more {rid} finding{'' if n == 1 else 's'} in "
                     f"{as_written(container)}, counted below but not listed")
    counts = {s: report.count(s) for s in Severity}
    lines.append("")
    # And how many of the errors are this tool declining to look rather than
    # anything the sender packed. Seven rules are `about: tool` and all seven are
    # errors, so that exit 0 can never mean "checked" -- every one of their
    # titles says so, and the count did not. A supplier read `1 error(s)` under a
    # remedy opening "Nothing here is necessarily wrong with the container", and
    # the axis that reconciles the two lived only in the JSON.
    # `count_about`, not a walk over `findings`: the listing is capped and the
    # count is not, so counting the axis over what was printed said "100 of the
    # errors" under "150 error(s)" and handed a supplier fifty that were not
    # theirs. The comment three lines above `count()` is about exactly this.
    ours = report.count_about(Severity.ERROR, About.TOOL)
    said = (f"  {counts[Severity.ERROR]} error(s), {counts[Severity.WARNING]} warning(s), "
            f"{counts[Severity.INFO]} note(s)")
    if ours:
        said += (f" — {ours} of the errors "
                 f"{'is' if ours == 1 else 'are'} this tool declining to look, "
                 f"not the container")
    lines.append(said)
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
