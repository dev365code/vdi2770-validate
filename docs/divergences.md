# Where this tool and the reference implementation disagree

The reference implementation (`DigitalDataChainConsortium/vdi2770`, MIT) is
useful evidence, not an authority. Its most recent commit at the time of writing
is `e47c13c` (January 2024), and reading it closely turned up defects we reported
back. So it is treated the way a second opinion should be treated: compared
against, per verdict, with every disagreement written down rather than averaged
away. It is generous work, and this project would have been much harder without
it.

Nothing here says the reference is wrong about the standard. Neither of us can
check that — the normative text is paywalled.

## How much of this was measured

It is measured now. Every container in `corpus/` and `tests/fixtures/` — 46 of
them, two of which postdate the run and carry our half only — was put through the reference implementation at its pinned commit
`e47c13c`, with the locale forced to `en_US`, and the result is checked in at
[`docs/oracle-sweep.json`](oracle-sweep.json). `tools/capture_oracle.py --check`
re-runs it and fails if either side has moved. `tools/oracle/README.md` says what
you need to repeat it, including the two things that will bite you.

What the sweep settled:

- **Every message key this catalogue cites exists in that project, and agrees
  with the code it is paired with.** Twenty-eight citations across the rules, nothing
  missing, nothing mismatched. (Read from the reference's own source at the pinned
  commit, and **not checkable from a clone**: `oracle-sweep.json` records the codes
  a run emitted, never the keys, and the vendored message file carries values with
  no keys at all. The count of citations is derived and gated; their existence and
  agreement are not — the same limitation §4 discloses, and it applies here too.) The `refKeys`/`refCodes` split earns its keep:
  thirteen of the reference's displayed codes are emitted from more than one key
  with different meanings, so a comparison keyed on the code alone is unsound.
- **Six containers where it reports an error and we do not**, and **seven where we
  do and it does not**. Neither list is a surprise — they are the severity
  policies in §1 and §2 below, and our own budget rules — but they were assumed
  before and are counted now.
- **It throws rather than reports on two of our fixtures.** More on that in §3.

The remaining "read from its source" claims in this document are marked where
they appear.

## 1. English class names decide nothing here

**Reference**: `DC_004` is an ERROR when an English `ClassName` is not in its own
list of twelve.
**Here**: `M4` is an `info` note that names both published renderings.

Why: the two freely published sources give different English names for five of
twelve classes (02-03, 02-04, 03-01, 03-04, 04-01). An English name therefore
cannot decide conformance without picking a winner between two publications, and
we are not in a position to pick. Matching is keyed on `ClassId` and the German
name, which both sources agree on for all twelve.

This will be revisited if IDTA states which rendering is normative.

## 1a. Why neither English rendering is trusted

The German names are the yardstick here, and they can be: both published sources
give the same twelve. Measured against them, each English rendering departs on
two of the four rows where they differ by wording. (The fifth, 04-01, differs only in case — see the defect register — so it has no German yardstick to lose against and is left out of the table below.)

| ClassId | German (both agree) | IDTA 02004 Table 1 | reference implementation | closer to the German |
|---|---|---|---|---|
| 02-03 | Bauteile | Assemblies | Components | reference (*Bauteile* are parts; assemblies are *Baugruppen*) |
| 02-04 | Zeugnisse, Zertifikate, Bescheinigungen | Certificates, declarations | Certificates | IDTA (the German names three things) |
| 03-01 | Montage, Demontage | Commissioning, decommissioning | Assembly, disassembly | reference (commissioning is *Inbetriebnahme*) |
| 03-04 | Inspektion, Wartung, Prüfung | Inspection, maintenance, testing | Inspection, maintenance | IDTA (*Prüfung* is dropped) |

Two each. That is why matching is keyed on the class id and the German name, and
why an English name produces a note here rather than a verdict: we have no basis
for preferring either, and the one source that would settle it — the English
edition of the guideline — is behind the same paywall as everything else.

What is known about provenance, and it is not much: the reference
implementation's `Constants.java` describes its English names as "defined in VDI
2770 guideline", and its author wrote it to support the VDI standardisation
working group. IDTA has used its own rendering consistently since 02004 v1.2
(2023-03), through v2.0.1 (2025-11), and in 02035-2 (2026-02). Both look
deliberate. A question has been put to IDTA; this section changes if it is
answered.

## 1b. Class names are matched to their class id, not to the whole table

**Reference**: `DC_003`/`DC_004` ask whether the name is *one of the twelve*, in
any position — `Constants.isCategoryName` tests membership of the values
collection and ignores the `ClassId` entirely. Outside strict mode it also
lowercases both sides.

**Here**: `M3` asks whether the name is *the one published for this class id*,
and compares exactly.

So this tool is stricter in two ways. `ClassId 02-01` labelled `Bauteile` (the
correct German name — of a different class) is `M3` here, and
`technische spezifikation` is `M3` here; both were run. That the reference
accepts them is **read from its source**, not measured — see the note below.

We think matching the pair is the more useful check — a name that belongs to
another class is exactly the mistake worth catching — but it is a divergence,
not an implementation of `DC_003`, and `refKeys` should be read as "this is the
neighbouring check", not "this is the same check".

Status: **deliberate**. Revisit if it produces false positives on real
containers; it produces none on the reference project's own examples.

## 2. PDF/A conformance level policy is not implemented

**Reference**: `REP_038` — outside the certificate class `02-04`, only PDF/A-*a*
levels are accepted; a PDF/A-*b* file is an error in strict mode. That is read
from its source and from its own test, which asserts exactly one error on
`document-invalid-pdfa-b.zip`; we have not run it ourselves on that file.
**Here**: not implemented — that container produces no error, which we did run.

Why: the rule as implemented there depends on a policy reading we cannot trace to
the free schema or to a freely published table. `P4` reports the claimed level, so
the information is in the report; the judgement is not.

Status: **unresolved**. It may become a rule with an explicit `ours` obligation.

## 3. Defects in the reference that this tool does not reproduce

Read from the source at `e47c13c`, reproduced by building that project and
running tests against it, and reported upstream as
[issue #38](https://github.com/DigitalDataChainConsortium/vdi2770/issues/38).
Those reproductions live with that project, not here — this repository has no
Java toolchain — so the summaries below are not checkable from a clone:

- `DV_013` fires on `numberOfPages < 0`, though its message says "greater than
  zero" — so `0` passes there. (Checked in the English, German and Chinese
  bundles; only the English one is vendored here.) This tool has no numberOfPages
  rule yet; when it gets one it will use the message's meaning.
- `MainDocument.validate` throws `IndexOutOfBoundsException` on an empty version
  list, discarding the `MD_001` it had just recorded.
- `MainDocument` overrides only the two-argument `validate`, so main-document rules
  are skipped entirely when it is validated through the three-argument entry point.

Two more, this time observed in the sweep rather than read:

- **A path-traversal member ends the run with an unhandled `ProcessorException`,
  so the container gets no report at all.** This is *not* a vulnerability: the
  refusal comes from zip4j (`illegal file name that breaks out of the target
  directory`), which does its job. It is a robustness gap — the other three
  members of that archive are never looked at, and the caller sees a stack trace
  instead of a finding. Our `Z4` reports it and carries on.
- **A member with a broken CRC does the same.** Same shape: the failure is real,
  the handling turns one bad member into no answer. Our `Z12` reports it.

One structural difference, not a defect on either side: the reference extracts
every container to a temporary folder on disk before validating
(`ZipUtils.unzipToTemperaryFolder`). This tool never writes to disk, which is
asserted by a test rather than promised.

## 4. Codes are ambiguous, so we key on message keys

Some of the reference's displayed codes are emitted from more than one message key
with different meanings — `PV_001` is both "Cannot find PDF file" and "PDF file is
valid". (Counted in that project, not here: this repository vendors the message
strings but not the key-to-code mapping, so the figure is not checkable from a
clone.) Any comparison keyed on the code string is unsound for those rows and
silently so. `rules.json` therefore carries `refKeys` (`module:key`, unambiguous)
alongside `refCodes` (display only).

## 5. What the reference reports that we do not

The reference's message catalogue is largely a log, not a finding stream: most of
its messages are exceptions and progress lines (`REP_009 "DocumentId: {0}"`, both
in the vendored list) rather than verdicts. We do not emit progress. A comparison
that treats those as missing findings is comparing our verdicts against its
`printf`s.
