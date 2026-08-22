# Where this tool and the reference implementation disagree

The reference implementation (`DigitalDataChainConsortium/vdi2770`, MIT) is
useful evidence, not an authority. It has been unmaintained since January 2024,
it has one contributor, and it has measured defects. So it is treated the way a
second opinion should be treated: compared against, per verdict, with every
disagreement written down rather than averaged away.

Nothing here says the reference is wrong about the standard. Neither of us can
check that — the normative text is paywalled.

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

## 2. PDF/A conformance level policy is not implemented

**Reference**: `REP_038` — outside the certificate class `02-04`, only PDF/A-*a*
levels are accepted; a PDF/A-*b* file is an error in strict mode.
**Here**: not implemented. `corpus/examples/container/document-invalid-pdfa-b.zip`
gets one error from the reference and none from this tool.

Why: the rule as implemented there depends on a policy reading we cannot trace to
the free schema or to a freely published table. `P4` reports the claimed level, so
the information is in the report; the judgement is not.

Status: **unresolved**. It may become a rule with an explicit `ours` obligation.

## 3. Defects in the reference that this tool does not reproduce

Found while building against it, reproduced with tests, reported upstream:

- `DV_013` fires on `numberOfPages < 0`, though its message in all three languages
  says "greater than zero" — so `0` passes there. This tool has no numberOfPages
  rule yet; when it gets one it will use the message's meaning.
- `MainDocument.validate` throws `IndexOutOfBoundsException` on an empty version
  list, discarding the `MD_001` it had just recorded.
- `MainDocument` overrides only the two-argument `validate`, so main-document rules
  are skipped entirely when it is validated through the three-argument entry point.

## 4. Codes are ambiguous, so we key on message keys

Thirteen of the reference's displayed codes are emitted from more than one message
key with different meanings — `PV_001` is both "Cannot find PDF file" and "PDF file
is valid". Any comparison keyed on the code string is unsound for those rows and
silently so. `rules.json` therefore carries `refKeys` (`module:key`, unambiguous)
alongside `refCodes` (display only).

## 5. What the reference reports that we do not

The reference's message catalogue is largely a log, not a finding stream: of 185
coded messages, 78 are model validation rules and the rest are exceptions and
progress lines (`REP_009 "DocumentId: {0}"`). We do not emit progress. A comparison
that treats those as missing findings is comparing our verdicts against its
`printf`s.
