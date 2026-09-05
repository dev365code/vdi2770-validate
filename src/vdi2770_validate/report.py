"""Rendering. Every finding prints what to do about it — a validator that only
says 'invalid' has done half the job."""
from __future__ import annotations

import json
from typing import Dict, List

from . import __version__
from .model import About, Report, Severity
from .names import as_written
from .resources import schema_stamp

MARK = {Severity.ERROR: "error", Severity.WARNING: "warn ", Severity.INFO: "info "}

#: The version of this report format. A consumer keys off it, so it moves when a
#: field changes meaning or leaves — adding one does not move it.
SCHEMA_VERSION = 1


def provenance() -> Dict:
    """What produced this document.

    It belongs on every document in a run, including the ones for paths that
    could not be read — those never reach a report, and a run where some
    documents can be version-checked and some cannot is worse for a consumer
    than one where none can.

    The rules are not versioned separately: `rules.json` ships inside the wheel
    and cannot be swapped without changing the install, so `toolVersion` is also
    the answer to "which rules judged this".
    """
    return {
        "schemaVersion": SCHEMA_VERSION,
        "toolVersion": __version__,
        "vdiSchema": schema_stamp(),
    }


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
    # anything the sender packed. Eight rules are `about: tool` and all eight are
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
    # And what this read opened, beside what the archive said was there. Both
    # halves come from the sender's own directory listing, so the pair says
    # something a reader can check and this tool cannot flatter. It is not a
    # finding: `--quiet` filters notes and the listing cap bounds what is
    # printed, and a statement about how much of the tool ran must survive both.
    r = report.read
    parts = [f"{r.archives_opened} of {r.archives_found} archives"]
    # Printed at zero too. Leaving it off when nothing was found made an archive
    # holding two members of one name -- the reader reads neither -- read the
    # same as one that lists no metadata file at all.
    if r.archives_opened:
        parts.append(f"{r.metadata_read} of {r.metadata_found} metadata files")
    lines.append("  read " + ", ".join(parts))
    return "\n".join(lines)


def as_json(report: Report, show_info: bool = True) -> str:
    """`show_info` is `--quiet`, which said "hide notes" and was read by one of
    the two shapes. A flag a machine-readable output ignores is a flag that
    means different things to the two readers of one run."""
    payload: Dict = {
        **provenance(),
        "target": report.target,
        "tool": "vdi2770-validate",
        "pdfaVerified": False,
        "pdfaNote": "This tool reports PDF/A claims. It does not verify them.",
        "summary": {s.value: report.count(s) for s in Severity},
        # What was opened, beside what the archive's own directory said was
        # there. `show_info` does not reach it: this is a statement about how
        # much of the tool ran, and a flag that hides notes must not change it.
        "read": {
            "archives": {"opened": report.read.archives_opened,
                         "found": report.read.archives_found},
            "metadataFiles": {"read": report.read.metadata_read,
                              "found": report.read.metadata_found},
            # And whether anything was declined, which the four numbers above
            # cannot say: a container whose metadata this tool read and could
            # not model has every number full, and printed beside a clean
            # container's line it said the same thing about two very different
            # reads. Every rule that is `about: tool` is this tool saying it
            # stopped, so one of them is the fact the flag is missing.
            "complete": (report.read.archives_opened == report.read.archives_found
                         and report.read.metadata_read == report.read.metadata_found
                         and not any(report.count_about(s, About.TOOL)
                                     for s in Severity)),
            "note": "Counted over the names the archives this read opened list, "
                    "refusals included; a metadata file inside an archive that "
                    "was not opened is not among them, and the archive count "
                    "says so. `complete` is false if anything was declined.",
        },
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
            if show_info or f.severity is not Severity.INFO
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
