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
| Amplification **after** a member is accepted | The archive caps do not bound what an accepted member costs to process. Inflating PDF streams is bounded per stream, in total, and by stream count; metadata larger than this tool will parse is refused rather than expanded into a tree and then validated; and an accepted member read out of the archive a second time, to hand it to the checks, is taken in the same one-megabyte steps as the first read, whatever size it claims; a member compressed with a method this reader does not inflate -- anything other than stored or deflate, which the library would decode whole -- is refused rather than decompressed. | `tests/test_amplification.py`, `packages/vdi2770/tests/test_the_budget_covers_every_read.py` |
| Deeply nested archives | Three container levels are opened — the deepest seen in real containers — and anything below is reported, not opened. | fixture `z6-nesting-too-deep.zip` |
| XXE / entity expansion | The XML parser refuses every entity declaration — internal, external and parameter — before the entity can be referenced. An external DTD subset on its own is not fetched either. | fixture `x3-entity-expansion.zip`; `tests/test_defences.py` |
| Remote schema fetch | The schema is bundled. `xsi:schemaLocation` in the document is never dereferenced. | `tests/test_offline.py` |
| Any network access at all | No socket is opened. A test counts attempts rather than waiting for one to fail, because a tool that reaches out and falls back quietly on error would satisfy the weaker check. | `tests/test_promises.py::test_nothing_reaches_for_the_network` — which watches `sys.addaudithook`, because patching names on the `socket` module misses a caller that bound the constructor before the patch; `tests/test_offline.py` for the verdict being the same either way |
| The GitHub Action's install | The action this repository publishes installs the released checker from PyPI unless you hand it a file with `pyz:`; `pip` checks what the index serves against the hashes that index publishes. That install is the action's, not the tool's: the checker still opens no socket for any input. A runner that may not reach an index carries the single file and passes `pyz:`, which removes the step entirely, and `sha256:` holds that carried file to a hash. | `action.yml`, `tests/test_the_action_behaves_the_way_its_names_claim.py` |

## Reporting a vulnerability

Open a GitHub security advisory on this repository, or a normal issue if the
problem is not sensitive. There is no bug bounty. A reproduction archive helps
enormously — if it cannot be shared, a description of the structure will do.

Please do not report findings that amount to "a malformed container produces a
confusing message". Those are welcome, but as ordinary issues.

## Advisories

A security fix that shipped in a release has a GitHub security advisory on
this repository, naming the versions it reaches and the release that fixes it.

- [GHSA-h676-59p4-6632](https://github.com/dev365code/vdi2770-validate/security/advisories/GHSA-h676-59p4-6632):
  a file cut short on the way, or with bytes in front of it, could be read as
  an archive it held and pass: a documentation container stores its document
  containers without compressing them, and cut short at the right length it
  was read as one of them, with no error and exit 0.
  `vdi2770-validate` and `vdi2770` from 0.1.0, up to 0.9.6;
  fixed in 0.9.7.

- [GHSA-62p8-4642-mwfp](https://github.com/dev365code/vdi2770-validate/security/advisories/GHSA-62p8-4642-mwfp):
  the heading of the text report, a detail line, and the line on stderr
  saying a path could not be read began with a value the sender wrote --
  the name of the file itself, the type a relationship names -- and a CI
  runner reads a line that begins in its own command syntax as an
  instruction rather than as text; the exit code and the JSON were not
  affected. `vdi2770-validate` from 0.1.0 and `vdi2770` from 0.8.0, up to
  0.9.5; fixed in 0.9.6.

- [GHSA-3pfq-57fx-w4q5](https://github.com/dev365code/vdi2770-validate/security/advisories/GHSA-3pfq-57fx-w4q5):
  a value the sender wrote -- a class id, a language, the identifier a
  relationship names, or the name of the file itself -- could start a line of
  its own in the text report and put a summary and a verdict this tool did not
  write above the real ones; the exit code and the JSON were not affected.
  0.9.5 kept every value to its line, and a file named with two spaces and
  the counts was still the summary line. `vdi2770-validate` from 0.1.0 and
  `vdi2770` from 0.8.0, up to 0.9.5; fixed in 0.9.6.

- [GHSA-6hqr-phm3-chpf](https://github.com/dev365code/vdi2770-validate/security/advisories/GHSA-6hqr-phm3-chpf):
  every finding printed the path of the container it was in, a container
  holding others repeats its name in every one of their paths, and the listing
  was bounded by how many findings it held and not by their size, so a 156 KB
  archive made a report of 136 MB in each of its two shapes. 0.9.3 bounded each
  rule's listing by the characters its findings stored, and a name made of
  characters the report spells out still printed six to thirteen times that;
  0.9.4 counted what it printed as UTF-8, and a console that cannot print
  UTF-8 received up to three times the budget. `vdi2770-validate` from 0.1.0
  and `vdi2770` from 0.8.0, up to 0.9.4; fixed in 0.9.5.

- [GHSA-f9xw-89gp-x52p](https://github.com/dev365code/vdi2770-validate/security/advisories/GHSA-f9xw-89gp-x52p):
  asking whether any document other than this one declares an identifier built
  one set of the whole delivery's identifiers for every document that asked and
  kept them all, so memory grew with the product of the two and a 963 KB
  archive made one run hold 1.6 GB. `vdi2770` and `vdi2770-validate` from 0.8.0
  up to 0.9.1; fixed in 0.9.2.

- [GHSA-xp97-jcmj-h45f](https://github.com/dev365code/vdi2770-validate/security/advisories/GHSA-xp97-jcmj-h45f):
  a container member that lied about its size, or used a compression method
  the reader could not bound, could make the reader allocate far more memory
  than the archive's own size. Every release of `vdi2770` and
  `vdi2770-validate` up to 0.8.0; fixed in 0.8.1.
