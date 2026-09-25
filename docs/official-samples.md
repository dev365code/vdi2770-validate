# The published samples, and what this tool says about them

The reference repository publishes sample files beside its code. They are
copied here unmodified: from `DigitalDataChainConsortium/vdi2770`
at commit `e47c13c1925abc3ed4698cb5ed9e73b5eb544353`, path `examples/`,
under the licence it carries (MIT, Copyright (C) 2021 Johannes Schmidt).
`corpus/MANIFEST.json` holds the SHA-256 of each. This page is this tool's
verdict on every one of them, and where each rule that fired takes its
requirement from. `tools/official_samples.py` writes it from the tool itself,
and the build fails when the two differ.

| Sample | Exit | Errors | Warnings | Notes | Rules that fired |
|---|---|---|---|---|---|
| `InvalidXMLName.zip` | 1 | 1 | 1 | 2 | M13 ×1 (ours), P4 ×2 (ours), Z3 ×1 (reference) |
| `container/certificate-pdfa-a.zip` | 0 | 0 | 1 | 2 | M13 ×1 (ours), P4 ×2 (ours) |
| `container/certificate-pdfa-b.zip` | 0 | 0 | 1 | 2 | M13 ×1 (ours), P4 ×2 (ours) |
| `container/document-invalid-pdfa-b.zip` | 0 | 0 | 1 | 2 | M13 ×1 (ours), P4 ×2 (ours) |
| `container/documentationcontainer.zip` | 0 | 0 | 0 | 2 | P4 ×2 (ours) |
| `container/documentcontainer-invalid.zip` | 0 | 0 | 1 | 1 | F3 ×1 (ours), P4 ×1 (ours) |
| `container/documentcontainer.zip` | 0 | 0 | 0 | 1 | P4 ×1 (ours) |
| `container/missingdocuments.zip` | 1 | 2 | 1 | 1 | M11 ×2 (reference), P4 ×1 (ours), Z8 ×1 (ours) |
| `container/morethanonepdfcontainer.zip` | 0 | 0 | 1 | 2 | P3 ×1 (ours), P4 ×2 (ours) |
| `container/objectreferences.zip` | 0 | 0 | 1 | 3 | M13 ×1 (ours), P4 ×3 (ours) |
| `container/vdi2770_demo.zip` | 0 | 0 | 1 | 3 | M13 ×1 (ours), P4 ×3 (ours) |
| `container/vdi2770_excel.zip` | 0 | 0 | 0 | 7 | P4 ×7 (ours) |
| `demo_invalid_doc_type_names.zip` | 0 | 0 | 2 | 4 | M13 ×1 (ours), M3 ×1 (table), M4 ×1 (ours), P4 ×3 (ours) |
| `demo_vdi.zip` | 0 | 0 | 1 | 3 | M13 ×1 (ours), P4 ×3 (ours) |
| `empty.zip` | 1 | 1 | 0 | 0 | Z2 ×1 (container) |
| `issues/issue16container.zip` | 0 | 0 | 0 | 1 | P4 ×1 (ours) |
| `missing_Maindocument.zip` | 1 | 1 | 1 | 2 | M13 ×1 (ours), P4 ×2 (ours), Z3 ×1 (reference) |
| `missing_Metadata.zip` | 1 | 2 | 1 | 2 | M11 ×1 (reference), M13 ×1 (ours), P4 ×2 (ours), Z3 ×1 (reference) |
| `missingdocuments/folders.zip` | 1 | 4 | 1 | 0 | F1 ×1 (reference), Z13 ×2 (ours), Z7 ×1 (reference), Z9 ×1 (reference) |

Where a requirement comes from: **schema**, the XSD VDI publishes free; **table**,
a table published free (IDTA 02004); **container**, the mechanics of ZIP and XML,
true without VDI 2770; **reference**, observed in the reference implementation
and not verified against the guideline, which is not published free; **ours**,
this tool's own judgement, with its reason. Each rule, its source and its remedy
are in [docs/rules.md](rules.md).

Exit `1` is at least one error, `0` none -- warnings and notes do not move it
unless `--fail-on warning` says they should.

Not containers, and not judged here: `.gitignore`, `Invalid1.pdf`, `Invalid2.pdf`, `InvalidName.xml`, `PDFA1b_File.pdf`, `PDFA2b_File.pdf`, `PDFA3b_File.pdf`, `VDI2770_Main.xml`, `Valid.pdf`, `folders/456-29201/VDI2770_Metadata.xml`, `folders/456-29201/demo.pdf`, `folders/456-29201/demo.xlsx`, `folders/AB393/VDI2770_Metadata.xml`, `folders/AB393/demo.docx`, `folders/AB393/demo.pdf`, `folders/VDI2770_Main.pdf`, `folders/VDI2770_Main.xml`, `missingdocuments/VDI2770_Main.pdf`, `missingdocuments/VDI2770_Main.xml`, `pdf/encrypted.pdf`, `pdf/password.pdf`, `pdf/scan.pdf`, `statistics.csv`, `xml/Datasheet.xml`, `xml/Invalid1.xml`, `xml/Invalid2.xml`, `xml/InvalidEmpty.xml`, `xml/Maindocument.xml`, `xml/MissingXmlNs.xml`, `xml/validation.xml`.
