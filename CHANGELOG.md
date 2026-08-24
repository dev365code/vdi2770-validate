# Changelog

## 0.2.0 — 2026-08-24

The readers moved out into their own package. `vdi2770` is now a dependency-free
library that reads a container and hands you a typed model; `vdi2770-validate` is
that library plus a rule set. Nothing about the verdicts changed — the same 207
tests pass on both sides of the move, and the reference corpus produces byte-identical
output.

Why bother: a rule set is an opinion, and opinions should be replaceable. Anyone
who wants to check a container against *their* customer's supplement, or feed the
parsed model into an AAS submodel builder, should not have to take our 33 rules
with them to do it.

- New package `vdi2770` (Apache-2.0, no dependencies) — `read_container`,
  `parse_xml`, `build_document`, `read_pdf`, and the value types.
- `vdi2770-validate` now depends on `vdi2770~=0.1.0`. The CLI, the rules and the
  output are unchanged.
- Moved, not copied: there is one implementation of each reader, in the SDK.
- Fixed: the 0.1.0 changelog said "32 rules" in a bullet and "33 rules" a
  paragraph above it. The catalogue had 33. A test now holds that number so the
  two cannot drift again.

**If you import from `vdi2770_validate.readers` or `vdi2770_validate.domain`,**
those paths are gone; import from `vdi2770` instead. The CLI is unaffected.

## 0.1.0 — 2026-08-24

First release. It reads a VDI 2770 container and tells you what is wrong with
it, offline, with a remedy on every finding.

What 0.1.0 means here: the 33 rules it has are gated — each was killed in turn to
confirm the suite notices, 22 have a minimal violating/conforming fixture pair,
and the rest are exercised by the reference project's own examples, which no
structural rule is allowed to fire on. What it does *not* mean is broad coverage
of VDI 2770. The scope is small and written down in docs/scope.md, and the
refusals there are the honest part.

- Reads VDI 2770 document and documentation containers without extracting them.
- 33 rules across five layers — container shape, schema conformance, declared
  files versus actual members, metadata model, and PDF claims — each with a
  remedy sentence and each traceable to the schema VDI publishes free, to a
  freely published table, to container mechanics, or to a stated judgement of
  our own.
- Document classification matched on class id and German name. The two freely
  published sources disagree on five of twelve English names, so an English name
  never decides a verdict here; it produces a note showing both renderings.
- Reports what a PDF *claims* about PDF/A. Does not verify the claim, and says so
  on every line where it matters.
- Gates: fixture pairs, firing coverage, import layering, offline, determinism,
  CI/local parity, the declared Python floor, licence notices, remedy text not
  copied from the reference, no structural rule firing on an upstream example,
  and the README sample being output the tool really produces.
