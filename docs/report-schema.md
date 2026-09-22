# The JSON report

`vdi2770-validate check --json` writes a JSON **array** to stdout — one element
per path on the command line, each carrying the path it is about. This page is
what is in an element and what `schemaVersion` promises about it.

An element for a path that could not be read at all is a different, shorter
shape: the provenance fields plus `unreadable`, saying why. There are no
findings in it, because nothing was judged.

A command-line usage error — an unknown option, a missing argument, an unknown
subcommand — exits `64` (`EX_USAGE`) having read nothing, so it writes no
report. Exit `2` means nothing could be read; `3` means the installation
disagrees with itself and no verdict was reached. Neither is a verdict on a
container.

`--quiet` hides notes. It is not a silencer for the whole report: the object is
still written, and what it drops is the `info` findings, from the JSON as well
as from the text.

```json
{
  "path": "handover.zip",
  "schemaVersion": 1,
  "toolVersion": "0.10.0",
  "vdiSchema": { "...": "which VDI schema this run validated against" },
  "target": "handover.zip",
  "tool": "vdi2770-validate",
  "pdfaVerified": false,
  "pdfaNote": "This tool reports PDF/A claims. It does not verify them.",
  "summary": { "error": 1, "warning": 0, "info": 2 },
  "read": {
    "archives":      { "opened": 3, "found": 3 },
    "metadataFiles": { "read": 3, "found": 3 },
    "complete": true,
    "note": "Counted over the names the archives this read opened list, ..."
  },
  "notListed": [ { "rule": "F2", "container": "handover.zip", "count": 4 } ],
  "findings": [
    {
      "rule": "M13",
      "severity": "warning",
      "layer": "metadata",
      "obligation": "ours",
      "about": "container",
      "message": "One identifier is called both a type and an individual",
      "detail": "'ABC1223' is declared as Individual, Type in this delivery ...",
      "remedy": "Decide which the identifier names and say the same thing ...",
      "refCodes": [],
      "refKeys": [],
      "where": {
        "container": "handover.zip",
        "member": "VDI2770_Main.xml",
        "line": 19, "column": 2,
        "xpath": null,
        "subject": "ABC1223"
      }
    }
  ]
}
```

The whole of this document, for one committed container, is stored as
[`docs/golden-report.json`](golden-report.json) and compared on every run of the
gate. The promises below are what this page says; that file is what the tool
actually said, so a value that changes without anyone deciding to change it is a
line in a diff rather than a discovery a consumer makes in production.

## What `schemaVersion` promises

`schemaVersion` is **1**. While it stays 1:

- **Fields are added, never renamed and never removed.** A reader that ignores
  unknown keys keeps working across releases.
- **`severity` is one of `error`, `warning`, `info`**, and a rule's severity
  does not change quietly — a change is named in the CHANGELOG entry for the
  release that makes it.
- **`rule` is a stable identifier.** `M13` means the same thing in every
  release that has it. Rules are added; an id is not reused for something else.
- **`findings` is ordered** by the tool's own sort, not by discovery order, so
  two runs over the same container produce the same bytes.

It does **not** promise that the same container draws the same findings
forever. Rules are added and verdicts move; that is what a minor release is,
and `toolVersion` is what tells you which rule set judged this run.

## The fields

| field | meaning |
|---|---|
| `schemaVersion` | this contract. `1`. |
| `toolVersion` | the release that judged this run. The rules ship with the engine, so this names the rule set too. |
| `vdiSchema` | the version the bundled schema stamps on itself — a property of this build, **not** a claim that the schema check ran. It can fail to run, which is what `X0` and `X4` report; `null` when there is no schema to read. |
| `path` | the path this element is about, as given on the command line. |
| `target` | the same path as the report itself recorded it. |
| `tool` | always `vdi2770-validate`. |
| `pdfaVerified` | always `false`. This tool reports PDF/A claims and does not verify them; `pdfaNote` says so in the report itself so a reader who only has the JSON is not misled. |
| `summary` | a count per severity. |
| `read` | how much was actually opened — see below. |
| `notListed` | findings collapsed to a count, with the rule and container they belong to, when one rule fired more times than a report should carry. |
| `findings` | one object per finding, `info` included unless `--quiet` was given. |

### `read` — how much of the delivery this verdict covers

`complete` is `true` only when three things hold: every archive the run found
was opened, every metadata file those archives list was read, and nothing was
declined. The third is the one the four numbers above cannot say — a container
whose metadata this tool read and could not model has every count full — so it
is read from the findings instead: any rule that is `about: tool` is this tool
saying it stopped, and one of those is enough to make `complete` false.

When it is `false`, the verdict covers less than the whole delivery, and the
numbers say how much less. A delivery whose documents are in folders rather than
nested archives reads `complete: false` — folders are not opened, which the tool
says with `Z13`.

This block exists because a report that says "0 errors" over a container it
could not open is the most expensive sentence this tool could print.

### `where`

Every field may be `null`. `container` and `member` name the archive and the
file inside it; `line` and `column` point into the metadata; `subject` is the
value the finding is about, which is what a sender searches their XML for.

## What is not in here

Nothing about *how* a verdict was reached beyond `rule`, `obligation` and the
reference keys the rule cites. `obligation` says whose claim a finding is —
`schema`, `table`, `container`, `reference` or `ours` — and `docs/rules.md`
carries the sentence behind each rule id.
