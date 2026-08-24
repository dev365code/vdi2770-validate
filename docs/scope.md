# What this tool does, and what it refuses to do

The refusals matter more than the features. A tool that quietly does a job badly
is worse than one that says it will not do that job.

## The one sentence

**This tool cannot tell you whether a PDF is PDF/A.** Only a full PDF/A validator
such as veraPDF can. It tells you what the file *claims*, which catches the common
failure — files that never claimed at all.

## In scope

- ZIP containers only, read in memory, never extracted to disk.
- Telling a document container from a documentation container, and saying why an
  archive is neither.
- Checking the metadata against the XML schema VDI publishes free of charge.
- Checking that files named in the metadata are in the archive, and the reverse,
  and that what is in the archive can actually be decompressed.
- Checking document classification against the twelve published classes.
- Reading, but never verifying, a PDF's PDF/A claim; reporting encryption.
- One remedy sentence per finding, in both the text and the JSON output. A
  finding without an action is half a job.

## Out of scope, deliberately

| Not done | Why |
|---|---|
| **Verifying PDF/A conformance** | Needs a full PDF/A validator. Reporting a claim as a verdict would be a lie. |
| **Building containers** | This is a referee, not an authoring tool. |
| **Fixing anything** | A validator that edits your data is a validator you stop trusting. |
| **Validating an unpacked directory** | ZIP only, for now. Halves the reader's surface. |
| **English class names as a pass/fail criterion** | The two published sources disagree for five of twelve classes (see `divergences.md`). We report the disagreement; we do not adjudicate it. |
| **IEC 61355 classification** | Needs a code list we do not have and may not be free to bundle. |
| **IEC 61406 identification links** | A self-contained URL-grammar problem with its own corpus needs. Named for a later milestone, not forgotten. |
| **Rendering PDF reports** | Not a validator's job. |
| **Container nesting beyond three levels** | Reported rather than opened. Three levels occur in real containers; deeper is a budget, not a verdict. |
| **More than a thousand containers, or 64 MiB of metadata, in one read** | Same answer: reported, not opened. Every other limit bounds one archive; these two bound the tree, because a few hundred kilobytes of nested containers could otherwise ask for more memory than the machine has. |

## Known limits of what *is* in scope

- **ISO 639**: we accept every ISO 639-1 two-letter code and any three-letter
  alphabetic code. We do not carry the full ISO 639-2 register, so a plausible-looking
  but non-existent three-letter code passes. Stated here rather than hidden.
- **Media types**: extension agreement is checked for `application/pdf` and
  `application/zip` only. We do not sniff file contents to confirm a declared type,
  except for PDFs.
- **Encryption is detected by pattern, not by parsing**: `P2` looks for the indirect
  reference the format requires the trailer to use (`/Encrypt 12 0 R`). That does not
  fire on the word appearing in a comment or a content stream, but it is still a
  pattern match rather than a parse of the trailer, so a very unusual file could
  fool it either way.
- **A PDF/A claim can be missed**: the claim is read from XMP packets found by
  scanning bytes and inflating a bounded stretch after each stream marker. A claim
  stored beyond what that scan reaches produces `P3`, whose title says exactly what
  happened — *this scan found no PDF/A claim in the file* — rather than the thing it
  would be wrong to say, that the file makes none. The prefix bound to the PDF/A
  namespace no longer matters, which used to be a second way to miss one. It cannot
  be *faked* by writing the words outside an XMP packet; that was possible once and
  is tested against now.
- **Every byte is read**: to say a member is deliverable we decompress it, the
  way `unzip -t` does. Measured at about 1.1 GB/s on real PDF content, so a
  container at the 2 GiB ceiling costs roughly two seconds. Nothing is held: the
  bytes are discarded as they are read.
- **The guideline text**: VDI 2770 Blatt 1:2020-04 is sold by DIN Media. It was not
  read. Every rule here names its source in `rules.json`: the free schema, a freely
  published table, ZIP and XML mechanics, the MIT reference implementation, or a
  judgement of our own.

## Why the refusals are written down

Some of them are the honest edge of a free tool. If you need a PDF/A claim
verified, use veraPDF — that is the whole answer, and a better tool for that job
than this one could be.
