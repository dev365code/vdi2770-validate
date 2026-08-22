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
| `table` | a freely published table says so | IDTA 02004 v2.0 Table 1 |
| `container` | container mechanics anyone can check | observable from the archive |
| `ours` | our own judgement | carries `whyOurs`, always |

## The three third-party artifacts

1. **The XML schema.** VDI publishes it free of charge on the VDI 2770 guideline
   programme page. Redistributed verbatim and unmodified. The download page states
   no licence or terms of use — we treat the file as VDI's work and change nothing
   about it. A request for an explicit licence statement is worth making.

2. **The document class table.** Transcribed from IDTA 02004 "Handover
   Documentation" v2.0 (June 2025) Table 1, published free by the Industrial Digital
   Twin Association; the same submodel template is published under CC-BY-4.0 in
   `admin-shell-io/submodel-templates`. Attributed in NOTICE.

3. **The conformance corpus.** Copied from the MIT-licensed reference
   implementation `DigitalDataChainConsortium/vdi2770`, Copyright (C) 2021
   Johannes Schmidt. Verbatim, hash-pinned, attributed in `corpus/NOTICE`.

## The remedy-text gate

The reference implementation's message strings are MIT and may be reused with
attribution — but reusing them would make this tool a translation of someone
else's reading rather than an independent one. So `tests/test_catalogue.py`
asserts mechanically that no remedy string in `rules.json` is copied from, or
embeds, any message in the reference's catalogue. That is a check, not a promise.
