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
        lines.append("  no findings")
    last_rule = None
    for f in findings:
        lines.append(f"  {MARK[f.severity]}  {f.rule.id}  {f.message}")
        lines.append(f"         at {f.where}")
        if f.detail:
            lines.append(f"         {f.detail}")
        if f.rule.id != last_rule:
            lines.append(f"         -> {f.remedy}")
            last_rule = f.rule.id
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
        "findings": [
            {
                "rule": f.rule.id,
                "severity": f.severity.value,
                "layer": f.rule.layer,
                "obligation": f.rule.obligation.value,
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
