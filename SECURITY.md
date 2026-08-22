# Security

## Why this file is not boilerplate

This tool exists to open archives that arrived from outside. A supplier's
handover package is exactly the kind of file people are told not to open, and
this tool is often the first thing to look inside one — frequently on a plant
network where the machine has no business reaching the internet. Hostile input
is the working assumption, not an edge case.

## What is defended, and where the proof is

| Attack | What we do | Test |
|---|---|---|
| Path traversal (`../`, absolute paths, backslashes) | Refused as a finding. **Nothing is ever extracted to disk** — members are read into memory. | fixture `z4-path-traversal.zip` |
| Zip bomb | Per-member size, total size, member count and compression-ratio caps. A member over the line becomes a finding and is never decompressed — including when the metadata declares it a PDF, which is how it got past the caps once. | fixtures `z5-compression-ratio.zip`, `z5b-declared-bomb.zip`; `tests/test_readers.py::test_a_rejected_member_cannot_be_read_by_a_later_layer` |
| Deeply nested archives | Recursion is bounded and archives below the bound are reported, not opened. | fixture `z6-nesting-too-deep.zip` |
| XXE / entity expansion | The XML parser refuses entity declarations and external references outright. | fixture `x3-entity-expansion.zip` |
| Remote schema fetch | The schema is bundled. `xsi:schemaLocation` in the document is never dereferenced. | `tests/test_offline.py` |
| Any network access at all | Sockets are monkeypatched to raise during validation. | `tests/test_offline.py` |

## Reporting a vulnerability

Open a GitHub security advisory on this repository, or a normal issue if the
problem is not sensitive. There is no bug bounty. A reproduction archive helps
enormously — if it cannot be shared, a description of the structure will do.

Please do not report findings that amount to "a malformed container produces a
confusing message". Those are welcome, but as ordinary issues.
