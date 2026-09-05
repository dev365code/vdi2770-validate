# vdi2770-validate

Point it at a VDI 2770 container and it tells you, offline, whether the archive is
one — and if something is wrong, what to do about it.

VDI 2770 is how manufacturers hand over technical documentation in the process
industry: PDFs bundled into ZIP "document containers" with an XML metadata file,
those bundled into a "documentation container". Operators in the process industry
increasingly ask for it in purchase orders, and a container rejected on intake holds
up a delivery. The reference implementation is a Java library and web service; this
is a small offline CLI you can drop into a CI job.

**Unofficial.** Not affiliated with VDI, the Digital Data Chain Consortium, or IDTA.
Names are used descriptively.

```bash
pip install vdi2770-validate
vdi2770-validate check YOUR-CONTAINER.zip
```

It exits `0` when it found no error, `1` when it found at least one or could not
read a path you gave it, and `2` when it could read none of them. A warning does
not move the number, so `0` means *no error*, not *nothing to look at* — the
report says what it found either way. An intake gate that wants none of the
warnings either can say `--fail-on warning`; the default is `error`, because a
warning here is a warning on purpose.

The rest of this page runs on containers that ship here, so to follow along:

```bash
git clone https://github.com/dev365code/vdi2770-validate
cd vdi2770-validate
```

```
$ vdi2770-validate check corpus/examples/missingdocuments/folders.zip
folders.zip
  error  F1  A file named in the metadata is not in the container
         at folders.zip!/VDI2770_Main.xml:56:2
         'VDI2770_Main.pdf' is declared but not in the archive
         -> Add the missing file to the container, or remove its DigitalFile entry from the metadata. The two must agree.
  error  Z7  The documentation container has no VDI2770_Main.pdf
         at folders.zip
         -> Add the main document as VDI2770_Main.pdf at the root of the documentation container, next to VDI2770_Main.xml.
  error  Z13  Documents are delivered as folders, which this tool does not open
         at folders.zip
         2 folders hold VDI2770_Metadata.xml: 456-29201/, AB393/
         -> Nothing here is necessarily wrong with the container. Zip each document folder into its own .zip member if you want this tool to check it, or check those folders with something that reads them.

  … 1 more Z9 warning

  3 error(s), 1 warning(s), 0 note(s) — 1 of the errors is this tool declining to look, not the container
  read 1 of 1 archives, 1 of 3 metadata files

This tool does not verify PDF/A conformance. It reports the claim a file makes
about itself where it finds one; only a PDF/A validator can say whether that
claim is true.
```

The last line is there on every report. `0 error(s)` says what was found; that
line says how much of the container was reached, counted over the names the
archive itself lists — so a delivery whose documents are in folders this tool
does not open cannot come back looking like one it read end to end.

That is real output, not a hand-written sample: a test in this repository runs the command and compares.

## What it will not tell you

**Whether a PDF really is PDF/A.** That needs a full PDF/A validator such as
veraPDF. This tool reports what a file *claims*, which catches the common failure:
files that never claimed at all. It says so on every line where it matters, and the
JSON output is one document for the run — a list with an entry per path you gave,
each carrying that `path`. An entry for a container that was checked also carries
`"pdfaVerified": false`; a path that could not be opened at all carries
`"unreadable"` and no verdict — no `pdfaVerified`, no counts, no findings —
because there is nothing to report about a file nobody read. It carries the
three fields that say what produced the run, like every other entry: a run where
some entries can be version-checked and some cannot is worse for a consumer than
one where none can. The rest of the refusals
are in [docs/scope.md](https://github.com/dev365code/vdi2770-validate/blob/main/docs/scope.md).

## How it is built

- **Offline by design.** No network at runtime, proven by a test that counts socket
  attempts rather than waiting for one to fail — a tool that reaches out and falls
  back quietly on error would satisfy the weaker check. Nothing is extracted to disk; a supplier archive does not get to pick a
  path on your filesystem or expand an XML entity.
- **Rules are data.** [`rules.json`](https://github.com/dev365code/vdi2770-validate/blob/main/src/vdi2770_validate/data/rules.json), rendered as [docs/rules.md](https://github.com/dev365code/vdi2770-validate/blob/main/docs/rules.md) — each
  rule carries where its requirement comes from, a remedy sentence, and — where the
  reference implementation checks the same thing — the message keys it uses.
- **25 of 38 rules have a minimal fixture pair** — a container that violates the rule
  and a conforming one differing in as little as a single member. A 26th has a violating
  fixture and no counterpart, because there is no conforming version of *this file is not
  a ZIP*. The rest are exercised by the vendored corpus. A rule that fires nowhere fails
  the build.
- **Rules cannot reach the parser.** A test fails if a rule module imports `zipfile`
  or an XML library, so a rule cannot accidentally check how a document was spelled
  instead of what it says. Rules may read the readers' constants — the reserved file names, the container kinds — but not call a parser.

## Two packages

The reader lives in [`vdi2770`](https://pypi.org/project/vdi2770/), a separate
package with no dependencies: it opens a container, refuses what it should refuse,
and hands back a typed model with a line number on every node. It decides nothing.

This package is that library plus a rule set. The split is not cosmetic — a test
fails if the reader can so much as import the rules — and it exists because a rule
set is an opinion. If your customer's supplement disagrees with ours, or you want
the parsed model for something other than a verdict, take the reader and leave the
opinion behind:

```bash
pip install vdi2770
```

## The classification table, and a disagreement

VDI 2770 defines twelve document classes. Two sources publish that table for free —
IDTA 02004 v2.0.1 Table 1, and the MIT reference implementation. Both renderings of
every name are stored, so you can check rather than trust: **they agree on all twelve
German names and disagree on five English ones** (02-03, 02-04, 03-01, 03-04,
04-01). So matching here is keyed on the class id and the German name, and an
English name never fails a document — it produces a note that shows both renderings.

```
$ vdi2770-validate classes
02-03  Bauteile                                   Assemblies   [sources disagree]
      English — IDTA 02004: 'Assemblies'   reference impl: 'Components'
```

Details in [docs/divergences.md](https://github.com/dev365code/vdi2770-validate/blob/main/docs/divergences.md).

## Licensing

Apache-2.0. The VDI 2770 guideline text is sold by DIN Media and was **not** read,
quoted, or paraphrased. Every rule names its source in `rules.json` instead: the schema
VDI publishes free, a freely published table, ZIP and XML mechanics, the MIT reference
implementation (observed there, not verified against the standard), or a judgement of
our own that has to explain itself.
See [docs/licensing.md](https://github.com/dev365code/vdi2770-validate/blob/main/docs/licensing.md) and [NOTICE](https://github.com/dev365code/vdi2770-validate/blob/main/NOTICE).

Contributions take a `Signed-off-by` line (DCO).

## Related

[iirds-validate](https://github.com/dev365code/iirds-validate) — the same idea for
iiRDS. [standards-watch](https://github.com/dev365code/standards-watch) — a daily
watch on these standards.
