# Licensing discipline

VDI 2770 is a paid standard. This project is built without reading it.

## What we did not do

**VDI 2770 Blatt 1:2020-04 is sold by DIN Media. It was not opened, quoted, or
paraphrased.** No rule message, title or remedy in this project derives from the
guideline text. There is no field in `rules.json` in which guideline prose could be
stored without lying about what it is.

## What every rule traces to

`rules.json` gives each rule an `obligation`:

| Value | Meaning | Source |
|---|---|---|
| `schema` | the published XSD says so | `data/VDI2770_Schema_2019-08-23.xsd`, published free by VDI |
| `table` | a freely published table says so | IDTA 02004 v2.0.1 Table 1 |
| `container` | ZIP and XML mechanics | true without knowing VDI 2770 |
| `reference` | observed in the MIT reference implementation | not verified against the guideline; the rule names the message keys |
| `ours` | our own judgement | carries `whyOurs`, always |

`obligation` and `refKeys` are independent. A rule may cite a message key from
the reference implementation while its obligation is `ours`, and five do: the
key records that the other project checks something in the same area, and the
obligation records whose claim ours is. `P3` is the clearest case — the reference
asserts the file carries no PDF/A identification; we assert only that a bounded
scan did not find one, which is the smaller claim and the one we can stand
behind. Reading a cited key as "so this is what VDI 2770 requires" is exactly the
mistake the vocabulary exists to prevent.

## The bundled third-party material

Full table, licence texts and modification statements are in
[THIRD_PARTY.md](../THIRD_PARTY.md); the summary here is for orientation only.

1. **The XML schema.** VDI publishes it free of charge on the VDI 2770 guideline
   programme page. Redistributed verbatim and unmodified. The download page states
   no terms of its own, but the publisher is not silent about the site: it reserves
   its rights and asks that reproduction be agreed first. So we treat the file as
   VDI's work, change nothing about it, and read a free publication of an interface
   definition as meant to be implementable — against that reservation rather than
   into a silence. An explicit statement from VDI is not a nicety here; it is the
   thing this rests on. [THIRD_PARTY.md](../THIRD_PARTY.md) quotes the reservation
   and says what happens if VDI would rather we stopped.

2. **The document class table.** Transcribed from IDTA 02004 "Handover
   Documentation" v2.0.1 (November 2025) Table 1, published by the Industrial
   Digital Twin Association in `admin-shell-io/submodel-templates` under
   **CC BY 4.0**. The twelve rows were extracted and reformatted as JSON — a
   modification, and stated as one. Full attribution in
   [THIRD_PARTY.md](../THIRD_PARTY.md).

3. **The conformance corpus.** Copied from the MIT-licensed reference
   implementation `DigitalDataChainConsortium/vdi2770`, Copyright (C) 2021
   Johannes Schmidt. Verbatim, hash-pinned, attributed in `corpus/NOTICE`.

## The reader package carries none of this

`vdi2770`, the reader library in `packages/`, bundles no third-party material at
all — no schema, no table, no vendored corpus. It is Apache-2.0 and that is the
whole story, which is one more reason the split was worth doing: the package most
likely to be embedded in someone else's product is the one with nothing attached
to it. The schema and the IDTA-derived table stay here, with the notices.

## The remedy-text gate

The reference implementation's message strings are MIT and may be reused with
attribution — but reusing them would make this tool a translation of someone
else's reading rather than an independent one. So `tests/test_catalogue.py`
asserts mechanically that no remedy string in `rules.json` is copied from, or
embeds, any message in the reference's catalogue. That is a check, not a promise.
