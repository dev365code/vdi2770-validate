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
| **More than a thousand containers, 64 MiB of metadata, or 4 GiB inflated, in one read** | Same answer: reported, not opened. Every other limit bounds one archive; these three bound the tree, because a few hundred kilobytes of nested containers could otherwise ask for more memory — or more CPU — than the machine has. The third was missing until it was measured: a 6.4 MB file inflated two terabytes and returned a clean verdict. It is two ceilings, not one, because two layers inflate: the archive reader expands members, and the PDF scan then expands the streams *inside* a member it was handed. The second was charged per file and not per read, so 150 declared PDFs in a 5.7 MB archive inflated 4.47 GiB — past a ceiling that was only ever watching the other door — and returned exit 0. Each layer stops at 4 GiB. The PDF scan then keeps reading what costs no inflation — whether the file is a PDF at all, and whether it is encrypted — and gives up only on the search for a PDF/A claim, naming the files it gave up on. An ordinary delivery of a few hundred documents can reach that ceiling, because the scan stops early only on files that carry a claim. |

## Known limits of what *is* in scope

- **A rule is listed at most a hundred times per container**: one rule fires once
  per element, so a crafted file can make one rule true nearly a hundred thousand
  times — the element budget for one metadata file is what stops it going further.
  Past a hundred the finding is counted but not printed, and the report says how
  many it withheld (`notListed` in JSON). **The counts and the exit code are not
  capped** — a bounded listing must never become a quieter verdict. Reading past
  the hundredth identical finding tells a user nothing the count does not.

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
  would be wrong to say, that the file makes none. Which prefix is bound to the
  PDF/A namespace no longer matters for the first four a packet declares, which
  used to be a second way to miss a claim; a packet that binds more than four
  gets four tries and then this scan stops looking. It cannot
  be *faked* by writing the words outside an XMP packet; that was possible once and
  is tested against now.
- **Every byte is read**: to say a member is deliverable we decompress it, the
  way `unzip -t` does. That is one pass of zlib over the member, so the rate is
  your machine's, and its content's: measured here at **0.5 GB/s** of
  decompressed output — one member read the way this tool reads it (a chunked
  loop that discards what it reads, not a whole-member `read()`), on real PDF
  content that barely compresses (ratio 1.20), CPython 3.9 on an arm64 laptop.
  Two content mixes at 0.54 GB and 1.2 GB gave 0.45–0.53 GB/s of CPU and
  0.36–0.47 GB/s end to end; a third mix on the same machine reached 0.73. The
  figure below is the low end of that, so the seconds it gives are the slow
  answer rather than the flattering one. At 0.5 GB/s a container reaching the
  2 GiB ceiling costs about **4 seconds** and either whole-read ceiling of 4 GiB
  about **9** — so a read that spends both stops at roughly twice that. Both figures are that division and nothing else, so a machine half
  this speed takes twice as long. The figure once published here, 1.1 GB/s, was
  above what zlib does on this content, and the 0.6 GB/s that replaced it was
  still above what this machine does. Nothing is held: the bytes are discarded as
  they are read. Past that ceiling members are still listed but no longer checked
  for readability, and the report says so rather than going quiet.
- **The guideline text**: VDI 2770 Blatt 1:2020-04 is sold by DIN Media. It was not
  read. Every rule here names its source in `rules.json`: the free schema, a freely
  published table, ZIP and XML mechanics, the MIT reference implementation, or a
  judgement of our own.

## What was rewritten, and what was not

Some commit messages in this repository once described how a change came to be
found. A published artifact carries the verdict and not the method, so on
2026-08-26 the **messages** of the commits and tags were rewritten to say what
changed rather than how it was noticed.

Only the messages. Every tree, author and date is unchanged, so each published
version still corresponds byte-for-byte to the tag it was built from — checked
against a bundle of the history taken beforehand. Nothing on an index moved, and
nothing that was verifiable before stopped being so.

What that rewrite did **not** do is remove anything. A force-push unlinks commits;
it does not delete them. Commits this repository rewrote earlier are still served
by name until the host collects them, and the host's public event feed records
the pushes regardless. The honest description is that the rewrite changed what a
visitor is shown, not what exists.

Where the trade runs the other way it is recorded as such: a log file carrying
absolute paths from a build machine was left in history rather than rewritten
over, because there the cost of rewriting exceeded what it would have bought.

## What the report says about itself

`0 error(s)` is a statement about findings. It is not a statement about reach,
and a file this tool cannot open at all used to print the same shape as a
container with one small thing wrong. So every report carries two sentences that
are about this tool rather than about the container.

The first is a count of what was read:

```
  read 1 of 1 archives, 1 of 3 metadata files
```

Both halves are over names the archive's own directory lists, refusals included.
That is the property worth having: giving up cannot improve the pair, and you
can check it against a listing of the archive — of each archive, where
containers are nested, because these count the tree and a listing shows one
level. A figure counted over this tool's own machinery would have the opposite
sign; a file that is not a ZIP calls for one check, that check runs and answers
no, and the worst input this tool ever sees would score full marks.

`--json` carries the same numbers under `read`, with a `complete` flag that is
deliberately more than the integers beside it: it is false when anything was
declined, so a container whose metadata this tool would not model does not read
as one it finished.

The second is the refusal this page leads with, said once per run:

```
This tool does not verify PDF/A conformance. It reports the claim a file makes
about itself where it finds one; only a PDF/A validator can say whether that
claim is true.
```

Neither is a finding. Both survive `--quiet` and the listing cap, and neither
moves a count or the exit code. That is deliberate: this refusal used to be
carried by a note, and `--quiet` — the flag a CI log reaches for — deleted every
mention of it. A statement about ourselves that a flag can delete is a statement
we do not really make.

Not every sentence in this page belongs in every report. What a rule means when
it fires travels with the rule — `M4`, for instance, reports which English
renderings exist and never fails a document on that basis, which matters when
`M4` fires and not otherwise. What goes in the run's own voice is what is true
of every run.

## Why the refusals are written down

Some of them are the honest edge of a free tool. If you need a PDF/A claim
verified, use veraPDF — that is the whole answer, and a better tool for that job
than this one could be.
