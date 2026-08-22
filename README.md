# vdi2770-validate

Point it at a VDI 2770 container and it tells you, offline, whether the archive is
one — and if something is wrong, what to do about it.

VDI 2770 is how manufacturers hand over technical documentation in the process
industry: PDFs bundled into ZIP "document containers" with an XML metadata file,
those bundled into a "documentation container". Plant operators require it in
purchase orders. Getting a container rejected on intake is expensive, and until now
there was no way to check one from a command line or a CI job.

**Unofficial.** Not affiliated with VDI, the Digital Data Chain Consortium, or IDTA.
Names are used descriptively.

```
$ vdi2770-validate check manuals.zip
manuals.zip
  error  Z7  The documentation container has no VDI2770_Main.pdf
         at manuals.zip
         -> Add the main document as VDI2770_Main.pdf at the root of the
            documentation container, next to VDI2770_Main.xml.
  warn   M3  The German class name does not belong to this class id
         at manuals.zip!/pump-4711.zip!/VDI2770_Metadata.xml:13:1
         'Technical INVALID specification' for class 02-01; published name is
         'Technische Spezifikation'
  info   P4  The PDF claims a PDF/A level; this tool did not verify the claim
         at manuals.zip!/pump-4711.zip!/datasheet.pdf
         claims PDF/A-3a — this tool cannot verify PDF/A conformance

  1 error(s), 1 warning(s), 1 note(s)
```

## What it will not tell you

**Whether a PDF really is PDF/A.** That needs a full PDF/A validator such as
veraPDF. This tool reports what a file *claims*, which catches the common failure:
files that never claimed at all. It says so on every line where it matters, and the
JSON output carries `"pdfaVerified": false` on every path. The rest of the refusals
are in [docs/scope.md](docs/scope.md).

## How it is built

- **Offline by design.** No network at runtime, proven by a test that makes sockets
  raise. Nothing is extracted to disk; a supplier archive does not get to pick a
  path on your filesystem or expand an XML entity.
- **Rules are data.** [`rules.json`](src/vdi2770_validate/data/rules.json) — each
  rule carries where its requirement comes from, what the reference implementation
  calls it, and a remedy sentence.
- **Every rule has a violating example and a conforming one**, and a rule that never
  fires anywhere fails the build.
- **Rules cannot reach the parser.** A test walks the import graph and fails if a
  rule module imports `zipfile` or an XML library, so a rule cannot accidentally
  check how a document was spelled instead of what it says.

## The classification table, and a disagreement

VDI 2770 defines twelve document classes. Two sources publish that table for free —
IDTA 02004 v2.0 Table 1, and the MIT reference implementation. **They agree on all
twelve German names and disagree on five English ones** (02-03, 02-04, 03-01, 03-04,
04-01). So matching here is keyed on the class id and the German name, and an
English name never fails a document — it produces a note that shows both renderings.

```
$ vdi2770-validate classes
02-03  Bauteile    Assemblies   [sources disagree]
      IDTA 02004: 'Assemblies'   reference impl: 'Components'
```

Details in [docs/divergences.md](docs/divergences.md).

## Licensing

Apache-2.0. The VDI 2770 guideline text is sold by DIN Media and was **not** read,
quoted, or paraphrased — every rule traces to the schema VDI publishes free, to a
freely published table, or to container mechanics, and `rules.json` says which.
See [docs/licensing.md](docs/licensing.md) and [NOTICE](NOTICE).

Contributions take a `Signed-off-by` line (DCO).

## Related

[iirds-validate](https://github.com/dev365code/iirds-validate) — the same idea for
iiRDS. [standards-watch](https://github.com/dev365code/standards-watch) — a daily
watch on these standards.
