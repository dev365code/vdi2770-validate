# Changelog

## Unreleased

First working version. Nothing has been released yet.

- Reads VDI 2770 document and documentation containers without extracting them.
- 30 rules across five layers — container shape, schema conformance, declared
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
