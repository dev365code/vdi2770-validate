# Changelog

## 0.5.0 — 2026-08-24

Released promptly rather than batched: the first item is a way to make the tool
run for hours on a small file, and it is in 0.4.0.

- **A malformed PDF could hang the tool.** The XMP packet scan was
  `START.*?END` with `re.S`; with the closer absent, every opener rescanned to
  the end of the buffer. 128 KiB of `<?xpacket begin` took 2.6 seconds and the
  cost squared with size, so a member sized just under the compression-ratio
  floor — which the reader accepts without a single defect — would have run for
  hours on a file small enough to email. None of the budgets caught it: they
  bound inflation, and this is the pass over the raw bytes. Packets are found by
  scanning now; the same input takes 16 milliseconds.
- **The tree budget did not cover the runner.** `MAX_CONTAINERS` and
  `MAX_TOTAL_METADATA_BYTES` bound what the *reader* holds, and the runner then
  kept every container's decompressed bytes in a dictionary keyed by path and
  never dropped one. Measured: a 2 MB input with two hundred inner containers
  reached 2,199 MB. It keeps one buffer per nesting level now — the walk is
  pre-order, so the parent's bytes are the only ones a container needs — and the
  same input reaches 582 MB, which is the reader's own peak. That is the third
  half-fix of the day: the budget was right about the thing it measured.
- **A container knows which member it came from.** `Container.member_name`
  replaces splitting the path on the JAR separator, which got the wrong answer
  for a member whose own name contains one — and silently, since both lookups
  simply missed and the PDF rules were skipped without a word.
- **A reserved name is only reserved where it is reserved.** The structural
  exemption that keeps `F2` quiet about `VDI2770_Main.xml`, `VDI2770_Metadata.xml`
  and `VDI2770_Main.pdf` named all three in every container, so a stray
  `VDI2770_Main.pdf` inside a *document* container — a name that means nothing
  there — was never reported as undeclared. The exemption now follows the
  container's kind.
- **The reader package carries a NOTICE.** Apache-2.0 asks for it to travel with
  the distribution; the validator shipped one from its first release and
  `vdi2770` shipped only a LICENSE, because its `license-files` named only that.
  Its NOTICE says what is true of it and not of its sibling: nothing third-party
  is bundled here at all. (`vdi2770` 0.3.1.)
- **The differential-oracle evidence is accounted for.** `docs/oracle-sweep.json`
  is derived from running someone else's MIT-licensed software, and was in
  neither NOTICE nor THIRD_PARTY.md. It is in both now, and a test asserts every
  string in it is an identifier rather than their message text — which is the
  property that keeps the attribution small and true.
- **Both spellings of a filename, in both directions.** Yesterday's NFD/NFC
  reconciliation normalised `present` and `declared` and missed the `F1` lookup
  itself, so a container whose *metadata* was decomposed and whose *archive* was
  composed had its file reported as declared-but-missing while `F2` stayed quiet
  about it — absent and accounted for at the same time. Only one of the two
  directions had a test. Both do now.


## 0.4.0 — 2026-08-24

All seven defects the audits left open, fixed one at a time. Verdicts on the 43
recorded corpus and fixture containers are unchanged throughout — checked at the
level of finding counts, not just which rules fired, because several of these
changes are the kind a set comparison cannot see.

- **A declared `application/zip` payload is no longer judged as a container.**
  The reader opens every member ending in `.zip` because it has no metadata and
  cannot know better; the rules do have the metadata and now use it. A parts list
  attached as `teileliste.zip` used to earn `Z3` — "neither a document container
  nor a documentation container" — which it had never claimed to be, while `F3`'s
  own remedy blesses `application/zip` with `.zip` in the same breath. Inside a
  document container it also earned `Z11`, whose own argument excuses it: that
  rule exists because an undeclared container is "a way to carry something past a
  check that only looks at declared files", and a declared one is not past that
  check. An **undeclared** inner `.zip` still fires both, and a declared payload
  that turns out to be a real container is still validated as one.
- **An identifier is `(domain, value)`, not a bare string.** The schema makes
  `DomainId` required — an id belongs to whoever runs that domain — and `M9`
  compared the text alone, so the same drawing number registered by an OEM and by
  its supplier read as a repeat. The remedy said "remove the repeated DocumentId",
  which would have destroyed a real registration; a warning whose advice is
  harmful is worse than silence. The reader now carries `Document.identifiers`
  (`vdi2770.DocumentId`, with the domain and the source position); `Document.ids`
  stays as a view of the values alone. Findings point at the repeated element
  rather than at the top of the document.
- **The main document is looked at.** `VDI2770_Main.pdf` is the file a
  documentation container is built around, and three rules each handed it to the
  next: `Z7` is satisfied by the name, `F2` exempts it as structural, and the P
  rules only looked at files the metadata declares. Declaring some other PDF is
  schema-legal, so an eighteen-byte text file called `VDI2770_Main.pdf` passed
  with exit 0. The reserved name is now a declaration in its own right, in a
  documentation container only — inside a document container it is just a file
  with a confusing name, and inventing a requirement there would be worse than
  the gap.
- **An empty value no longer switches a check off.** `M5` fired on an empty
  `<Language/>` element and stayed silent on an empty `Language=""` attribute —
  the guard was `if d.language`, which is the shape `M8`'s own `whyOurs` warns
  about. The reader now distinguishes an absent attribute (`None`) from a present
  empty one (`""`), so the absent case stays with the schema layer where it
  belongs and the empty one is reported.
- **A namespace prefix is arbitrary.** A PDF/A identification is identified by
  its URI; `pa:part` bound to `http://www.aiim.org/pdfa/ns/id/` says exactly what
  `pdfaid:part` says. The scan matched the literal token, so a file from a
  conforming exporter read as having no claim and `P3` told its author to fix
  something that was already right. The prefix now comes from the packet's own
  declaration — and a prefix bound to some other URI is still not a claim.
- **A refusal to look is no longer reported as an absence.** `Z8` said a
  documentation container held no document containers while `Z6`, one line above,
  named the one it had found inside it. `Z8` tested for absent children, and the
  reader stops populating them at three levels, at the tree's container budget,
  and for a `.zip` member it could not decompress. It stays quiet in those three
  cases, where `Z6` and `Z12` already say what happened, and a container that
  genuinely holds nothing is still reported.
- **A folder is a folder whether or not the ZIP says so.** `Z9` tested
  `ZipInfo.is_dir()`, which is a trailing slash on a member name, and directory
  entries are optional in the format — so whether the rule fired depended on
  which library wrote the archive rather than on the archive's shape. A container
  that put every file in `docs/` passed clean; adding one empty `anhang/` entry
  to the same layout did not. It now reports the folders the member paths imply,
  and names them.
- **One note per file, not per declaration.** A metadata file naming the same PDF
  in three document versions printed three identical `P4` lines about one file.
- **A decomposed filename is scanned, not silently skipped.** Reconciling NFD and
  NFC in the F rules alone turned out to be worse than not doing it: `F1` stopped
  reporting the file as missing while the P rules went on failing to find it, so
  a Mac-zipped delivery with an umlaut in a filename had its PDFs checked by
  nobody. Both layers resolve names the same way now.
- A test now checks that the reader version in this repository satisfies the
  range the validator declares for it. Getting that wrong sends `pip` to PyPI for
  a package that only exists in the working tree — it happened once while writing
  the change above, and only running the install caught it.


## 0.3.1 — 2026-08-24

**A small file could exhaust the machine.** Found while drawing the architecture
to check it, which is the argument for drawing it.

Every limit in the reader bounded one archive or one member. None bounded the
container *tree*, and a documentation container may hold thousands of inner
containers whose metadata is held for as long as the caller walks it. Measured:
a **274 KB** input produced **265 MB** resident, and no per-archive cap came near
engaging — the outer archive's uncompressed total was 254 KB against a 2 GiB
limit. The only binding constraint was the ten-thousand-member cap, so ten
thousand inner containers each carrying sixteen megabytes of metadata was a
permitted input: roughly **156 GiB**, from a file small enough to email.

Two budgets now span the whole read — `MAX_CONTAINERS` (1,000) and
`MAX_TOTAL_METADATA_BYTES` (64 MiB) — and exhausting either is reported as a
`container-budget-exhausted` defect rather than silently truncating the tree.
The same 274 KB input now peaks at 95 MB. Ordinary nested containers are
untouched.

The gap was structural rather than an oversight in any one cap: each limit was
correct about the thing it measured, and nothing measured the total. The
amplification test that existed checked a single archive.


## 0.3.0 — 2026-08-24

Two independent audits — one of what every rule *claims*, one trying to make the
tool give a wrong answer — found thirteen defects. Six are fixed here. The three
that mattered most were containers this tool passed with exit 0 that `unzip -t`
refuses, and legitimate deliveries it failed.

**It said nothing about archives that are broken**

- **New rule `Z12`** — a member listed in the directory that cannot be
  decompressed. A truncated transfer (broken CRC) and a member with a password
  both produced "no findings", exit 0: the bytes came back empty and every later
  layer read that as "not declared". These are the commonest defects a handover
  archive has, and this tool certified them clean.

**It failed deliveries that were fine**

- `Z5` no longer treats a high compression ratio as hostile below 8 MiB. An
  uncompressed TIFF scan of a line drawing expands ~220× and lands at one
  megabyte; a 104 KB archive was refused with "exceeds this tool's limits for
  untrusted input" and the unactionable remedy "split the delivery".
- `Z4` no longer calls `5:1.pdf` an absolute path. The drive-letter test looked
  only for a colon in the second position; a gear ratio is not a drive.
- `F1`/`F2` compare filenames under Unicode NFC. macOS writes decomposed names
  into a ZIP while metadata authored elsewhere is composed, so the report used to
  say the same visible name was both missing and undeclared.
- `Z2` no longer says "the archive is empty" when the archive has members we
  refused to read, and no longer swallows `Z3` when it does.
- `M2` no longer tells you to pick a valid class id when the `ClassId` element is
  absent. There is nothing to correct; `X2` reports the missing element.

**Seven rules were wearing the wrong provenance**

`container` means "true without knowing VDI 2770 at all" — the strongest thing
this project claims about a rule. It had become the default for anything not
obviously schema or table. `Z3`, `F1`, `F2`, `F3`, `F4` and `P1` all rest on VDI
reserved filenames or the VDI metadata model, and are now `reference`; `X1` was
`schema`, but well-formedness is XML 1.0 and the schema cannot speak until it
holds, so it is now `container`. A test lists the three remaining `container`
rules with a written reason each, and fails if a fourth appears unexplained.

The count moves in the honest direction: fourteen rules now rest on behaviour
read out of someone else's Java and never checked against the guideline, where
the release notes for 0.1.0 implied none did.

**Measured, at last**

`docs/divergences.md` said "comparing all nineteen corpus containers against
captured output is on the board and not done". It is done: 42 containers through
the reference implementation at its pinned commit, and `tools/oracle/` carries
what is needed to repeat it. Every reference message key the catalogue cites
exists in that project and agrees with the code it is paired with — 0 defects on
30 citations. Two things the sweep found: the reference **crashes** on a
path-traversal archive rather than reporting it (zip4j blocks the traversal, so
this is a robustness gap and not a vulnerability), and it extracts every
container to a temporary folder on disk before validating, which this tool
never does.

**Still open**, recorded rather than quietly dropped: seven verified defects,
listed in the defect register — a declared `application/zip` payload is judged as
if it were a container, `Z9` misses subdirectories that carry no explicit folder
entry, `M9` treats one id string in two `DomainId`s as a repeat, an undeclared
`VDI2770_Main.pdf` is never content-checked, `Z8` contradicts `Z6` at four levels
of nesting, `M5` skips an empty `Language` attribute, and `P3` misses a PDF/A
claim bound to a prefix other than `pdfaid`.


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
  our own. *(Corrected in 0.3.0: this list left out `reference` — behaviour read
  out of the reference implementation and never checked against the guideline —
  which eight of those rules carried, and fourteen carry now.)*
- Document classification matched on class id and German name. The two freely
  published sources disagree on five of twelve English names, so an English name
  never decides a verdict here; it produces a note showing both renderings.
- Reports what a PDF *claims* about PDF/A. Does not verify the claim, and says so
  on every line where it matters.
- Gates: fixture pairs, firing coverage, import layering, offline, determinism,
  CI/local parity, the declared Python floor, licence notices, remedy text not
  copied from the reference, no structural rule firing on an upstream example,
  and the README sample being output the tool really produces.
