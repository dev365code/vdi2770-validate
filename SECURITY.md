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
| Path traversal (`../`, absolute paths, backslashes) | Refused as a finding. **Nothing is ever extracted to disk** — members are read into memory. | fixture `z4-path-traversal.zip` for the refusal; `tests/test_promises.py::test_nothing_is_written_to_disk` for the disk claim, which watches `sys.addaudithook` rather than trusting that no call site opens a file |
| Zip bomb | Per-member size, total size, member count and compression-ratio caps. A member over the line becomes a finding and is never decompressed — including when the metadata declares it a PDF, which is how it got past the caps once. | fixtures `z5-compression-ratio.zip`, `z5b-declared-bomb.zip`; `packages/vdi2770/tests/test_the_public_api.py::test_a_member_the_reader_refused_cannot_be_read_by_a_later_layer`; `packages/vdi2770/tests/test_a_refused_member_is_never_read.py` |
| Amplification **after** a member is accepted | The archive caps do not bound what an accepted member costs to process. Inflating PDF streams is bounded per stream, in total, and by stream count; metadata larger than this tool will parse is refused rather than expanded into a tree and then validated. | `tests/test_amplification.py` |
| Deeply nested archives | Three container levels are opened — the deepest seen in real containers — and anything below is reported, not opened. | fixture `z6-nesting-too-deep.zip` |
| XXE / entity expansion | The XML parser refuses every entity declaration — internal, external and parameter — before the entity can be referenced. An external DTD subset on its own is not fetched either. | fixture `x3-entity-expansion.zip`; `tests/test_defences.py` |
| Remote schema fetch | The schema is bundled. `xsi:schemaLocation` in the document is never dereferenced. | `tests/test_offline.py` |
| Any network access at all | No socket is opened. A test counts attempts rather than waiting for one to fail, because a tool that reaches out and falls back quietly on error would satisfy the weaker check. | `tests/test_promises.py::test_nothing_reaches_for_the_network` — which watches `sys.addaudithook`, because patching names on the `socket` module misses a caller that bound the constructor before the patch; `tests/test_offline.py` for the verdict being the same either way |

## Reporting a vulnerability

Open a GitHub security advisory on this repository, or a normal issue if the
problem is not sensitive. There is no bug bounty. A reproduction archive helps
enormously — if it cannot be shared, a description of the structure will do.

Please do not report findings that amount to "a malformed container produces a
confusing message". Those are welcome, but as ordinary issues.
