# Third-party material and provenance

Everything bundled here, where it came from, what you may do with it, and
whether we changed it.

| Component | Origin | Licence | Modified? |
|---|---|---|---|
| `src/vdi2770_validate/data/VDI2770_Schema_2019-08-23.xsd` | VDI, from the [VDI 2770 guideline programme page](https://www.vdi.de/richtlinien/programme-zu-vdi-richtlinien/vdi-2770) | **No licence stated by the publisher** — see below | **No — byte-for-byte verbatim** |
| `src/vdi2770_validate/data/document-classes.json` | Table 1 of IDTA 02004 "Handover Documentation" v2.0.1, as published in [admin-shell-io/submodel-templates](https://github.com/admin-shell-io/submodel-templates); the `ddcReference` names beside them from `Constants.java` of the reference implementation | **CC BY 4.0** © Industrial Digital Twin Association (IDTA names, IRDIs) **and MIT** © 2021 Johannes Schmidt (`ddcReference` names) | **Yes** — extracted and reformatted as JSON; no wording changed |
| `corpus/examples/` (49 files) | [DigitalDataChainConsortium/vdi2770](https://github.com/DigitalDataChainConsortium/vdi2770) @ `e47c13c`, `examples/` | **MIT**, © 2021 Johannes Schmidt | **No — byte-for-byte verbatim, SHA-256 per file in `corpus/MANIFEST.json`** |
| `tests/data/oracle-messages.json` | English message bundles of the same project | **MIT**, © 2021 Johannes Schmidt | **Yes** — the message strings were extracted into a JSON list; no wording changed |
| `src/vdi2770_validate/data/rules.json` | this project | Apache-2.0 | n/a — titles and remedies are ours, checked against the reference's messages by `tests/test_catalogue.py::test_no_remedy_is_copied_from_the_reference_implementation`; its codes appear only in `refCodes`/`refKeys` as cross-references |
| `docs/oracle-sweep.json` | produced by running the reference implementation over our containers | **derived from MIT** work, © 2021 Johannes Schmidt | **Yes** — it records message *codes* (`REP_038`) and nothing else. A test asserts no string in it is longer than a code, so their message text cannot drift into it |
| `tools/oracle/Sweep.java` | this project | Apache-2.0 | n/a — our code, compiled against their MIT classes, containing none of their source. It is in this repository's sdist and in neither wheel |
| Everything else | this project | Apache-2.0 | n/a |
| `xmlschema` (runtime dependency, not bundled) | [sissaschool/xmlschema](https://github.com/sissaschool/xmlschema) | MIT | No |

The corpus and the message list are **test material** and are not in the wheel —
`pyproject.toml` ships only `src/vdi2770_validate`. The MIT-derived English and
German class names inside `document-classes.json` **are** in the wheel, which is
why that row names two licences.

---

## The VDI schema, and the one thing we are relying on

VDI publishes this XSD free of charge on the VDI 2770 guideline programme page,
alongside the same declaration in plain text. It is the machine-readable model
of the metadata file, and publishing it free is what makes independent
implementations possible at all.

**The download page states no licence and no terms of use.** So this
redistribution rests on the evident purpose of a free publication of an
interface definition, not on an explicit grant. We therefore:

- ship the file **completely unmodified**. The copy here has SHA-256
  `f7a704fe4bba095eaa4e95be0b9853205412301ad09c4bcffb4c5f0f666cb805`; a test pins
  that, which proves the file has not drifted since it was vendored — not that it
  is VDI's. To confirm the origin, download from the URL in NOTICE (published as
  `VDI_2770_1_de_Deklaration_des_XML-Schemas_-_Declaration_of_the_XML_model.xsd`)
  and compare;
- never present it as our work, and never relicense it — Apache-2.0 covers this
  project's own code, not this file;
- reproduce no part of the VDI 2770 guideline text, which is a separate,
  **paid** document sold by DIN Media and was not consulted (see
  [docs/licensing.md](docs/licensing.md)).

If VDI would rather this file were not redistributed, open an issue. What can
actually be done, stated honestly rather than generously:

- the file is removed from this repository the same day, and from every release
  published after that;
- releases already on a package index are yanked, which hides them from
  resolvers but **does not delete them** — a pinned version still installs, and
  mirrors may already hold copies. Published bytes cannot be recalled by anyone,
  including us;
- the tool then needs the schema supplied by path, which costs its users their
  offline installation and costs nobody their rights.

That third point is why a release is a heavier commitment than a repository, and
why this is written down before the first one rather than after.

---

## IDTA 02004 — attribution under CC BY 4.0

`document-classes.json` contains the twelve VDI 2770 document classes with their
German and English names and ECLASS semantic identifiers, taken from:

> **IDTA 02004 "Handover Documentation", Version 2.0.1 (November 2025), Table 1**,
> Industrial Digital Twin Association e.V.,
> https://github.com/admin-shell-io/submodel-templates —
> licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

**Changes made:** the table's twelve rows were extracted and reformatted as
JSON, with the English names of the corresponding rows of the reference
implementation stored beside them for comparison. No wording was altered.

This project is not endorsed by, affiliated with, or certified by the IDTA.

---

## MIT License — corpus and message list

The following applies to `corpus/examples/` and `tests/data/oracle-messages.json`,
both taken from `DigitalDataChainConsortium/vdi2770`:

```
MIT License

Copyright (C) 2021 Johannes Schmidt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

`corpus/examples/.gitignore` is part of that verbatim copy; it is theirs, not
ours.

---

## Names

"VDI 2770" names the standard this tool checks against, and "IDTA", "ECLASS"
and the names of the projects above identify their owners' work. They are used
descriptively. This project is unofficial and not affiliated with, endorsed by,
or certified by VDI, the Digital Data Chain Consortium, the IDTA, or the authors
of the reference implementation.
