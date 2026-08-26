# The rules

Generated from [`rules.json`](../src/vdi2770_validate/data/rules.json) by
`tools/rules_doc.py`. Edit the data, not this page — `make check` compares them.

`obligation` says where a requirement comes from, and the vocabulary is deliberately
not MUST/SHOULD: this project has not read VDI 2770, so it never claims to quote
it. `about` separates a statement about the container from a statement about this
tool, because both are errors on purpose and severity cannot carry the difference.

- **`schema`** (1) — the XSD VDI publishes free says so, mechanically
- **`table`** (2) — a freely published table says so (IDTA 02004)
- **`container`** (4) — mechanics of ZIP and XML — true without VDI 2770
- **`reference`** (13) — observed in the MIT reference implementation, **not** verified against the guideline, which is paywalled
- **`ours`** (18) — our own judgement, and it carries a reason

38 rules.

## container

### `Z1` — The file is not a readable ZIP archive

*error* · obligation `container`

Reference implementation: `processor:ZU_MESSAGE_002`, `processor:ZU_MESSAGE_003` (displayed as `ZU_002`, `ZU_003`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** A VDI 2770 container is a ZIP archive. Rebuild it with a standard ZIP tool and check the file was not truncated in transfer.

### `Z2` — The archive is empty

*error* · obligation `container`

Reference implementation: `processor:REP_MESSAGE_002` (displayed as `REP_002`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add the metadata file and the documents. An empty archive cannot be classified as either container kind.

### `Z3` — The archive is neither a document container nor a documentation container

*error* · obligation `reference`

Reference implementation: `processor:REP_EXCEPTION_004`, `processor:REP_MESSAGE_035` (displayed as `REP_004`, `REP_035`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Put VDI2770_Metadata.xml at the root of a document container, or VDI2770_Main.xml at the root of a documentation container. Both names are case-sensitive and must not sit inside a folder.

### `Z4` — A member name would escape the extraction directory

*error* · obligation `ours`

Why this is ours: The reference implementation extracts to a temporary directory. We never extract, so we can refuse hostile names outright instead of inheriting the risk.

**Remedy.** Rebuild the archive with plain relative names. Absolute paths, parent-directory segments and backslash separators are not acceptable in a container that will be unpacked by the recipient.

### `Z5` — The archive exceeds this tool's limits for untrusted input

*error* · obligation `ours` · **about: this tool**

Reference implementation: `processor:ZU_EXCEPTION_004` (displayed as `ZU_004`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

Why this is ours: Supplier archives arrive from outside. A validator must not be a way to exhaust the machine that runs it.

**Remedy.** Split the delivery into several containers, or report the archive to whoever produced it if the size looks unintentional.

### `Z6` — Containers are nested deeper than this tool will open

*error* · obligation `ours` · **about: this tool**

Why this is ours: A budget for untrusted input, not a claim about the standard — three container levels occur in the reference project's own examples, so we open three and report the fourth. It is an error for the reason X0 and X4 give: we did not look, and a report that passes what it did not look at is worse than no report. Raise the level if your deliveries are deeper; do not read exit 0 as 'checked'.

**Remedy.** Check the delivery is what you meant to send. If the nesting is genuine, unpack the outer archive and check the inner containers separately.

### `Z7` — The documentation container has no VDI2770_Main.pdf

*error* · obligation `reference`

Reference implementation: `processor:REP_MESSAGE_025` (displayed as `REP_025`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add the main document as VDI2770_Main.pdf at the root of the documentation container, next to VDI2770_Main.xml.

### `Z8` — The documentation container holds no document containers

*warning* · obligation `ours`

Why this is ours: The reference implementation has no rule for this. A documentation container whose only content is its own main document delivers nothing, which is worth saying out loud even though nobody else says it — hence a warning, not an error.

**Remedy.** Add the document containers this handover is supposed to deliver. A documentation container with only a main document delivers no documents.

### `Z9` — The archive stores files in folders

*warning* · obligation `reference`

Reference implementation: `processor:ZU_MESSAGE_001` (displayed as `ZU_001`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Store the members at the root of the archive. This tool resolves a metadata name that carries its folder path, so the file-set rules can stay quiet — but the reference implementation warns about the folders anyway, and it is the recipient's tooling that has to accept the container.

### `Z10` — Two members of the archive have the same name

*error* · obligation `ours`

Why this is ours: ZIP allows it and readers disagree about which one wins, so the container can show one thing to this tool and another to whoever unpacks it. Nothing good is ever delivered this way.

**Remedy.** Rebuild the archive with one entry per name. If two files genuinely differ, give them different names and declare both.

### `Z11` — A document container carries another container inside it

*error* · obligation `ours`

Why this is ours: Document containers hold a document's files. A container inside one is either a mistake or a way to carry something past a check that only looks at declared files.

**Remedy.** Move the inner container up into the documentation container, where containers belong — or, if it is payload rather than a container, declare it in this document container's metadata as a DigitalFile with FileFormat application/zip. This tool opens every .zip because the reader has no metadata to know better; a declaration is what tells it which of the two you meant.

### `Z12` — A file in the container could not be read

*error* · obligation `container`

**Remedy.** Re-create the archive and send it again. A member with a broken CRC is usually a truncated transfer; a member that needs a password has not been handed over, because the recipient cannot open it.

### `Z13` — Documents are delivered as folders, which this tool does not open

*error* · obligation `ours` · **about: this tool**

Why this is ours: A folder holding VDI2770_Metadata.xml is a document container that was not zipped. This tool opens .zip members and nothing else, so everything inside was unchecked — and a report that said nothing would be telling the reader it passed. The reference implementation does read them, so this is a limit of ours rather than a fault of the delivery.

**Remedy.** Nothing here is necessarily wrong with the container. Zip each document folder into its own .zip member if you want this tool to check it, or check those folders with something that reads them.

## files

### `F1` — A file named in the metadata is not in the container

*error* · obligation `reference`

Reference implementation: `processor:REP_MESSAGE_007` (displayed as `REP_007`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add the missing file to the container, or remove its DigitalFile entry from the metadata. The two must agree.

### `F2` — A file in the container is not named in the metadata

*warning* · obligation `reference`

Reference implementation: `processor:REP_MESSAGE_006` (displayed as `REP_006`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Declare the file as a DigitalFile in the metadata, or remove it from the container. An undeclared file is invisible to the recipient's system.

### `F3` — The declared file format disagrees with the file name

*warning* · obligation `reference`

Reference implementation: `core:DigitalFile_VAL2`, `core:DigitalFile_VAL3` (displayed as `DF_002`, `DF_003`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Make FileFormat and the file extension agree — application/pdf with .pdf, application/zip with .zip.

### `F4` — A declared file has no name

*error* · obligation `reference`

Reference implementation: `core:DigitalFile_VAL4` (displayed as `DF_004`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Give the DigitalFile element the file's name as its text, or remove the element. An empty name means the metadata promises a document and names nothing.

## metadata

### `M1` — The document carries no VDI 2770 classification

*error* · obligation `reference`

Reference implementation: `core:Document_VAL2` (displayed as `D_002`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add a DocumentClassification whose ClassificationSystem is VDI2770:2018 and whose ClassId is one of the twelve published classes.

### `M2` — The class id is not one of the published VDI 2770 classes

*error* · obligation `table`

Source: `IDTA 02004 v2.0.1 Table 1`.

Reference implementation: `core:DocumentClassification_VAL2` (displayed as `DC_002`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Use one of: 01-01, 02-01, 02-02, 02-03, 02-04, 03-01, 03-02, 03-03, 03-04, 03-05, 03-06, 04-01.

### `M3` — The German class name does not belong to this class id

*warning* · obligation `table`

Source: `IDTA 02004 v2.0.1 Table 1`.

Reference implementation: `core:DocumentClassification_VAL3` (displayed as `DC_003`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Use the German name published for this class id, or correct the class id if the name is the one you meant.

### `M4` — The English class name matches neither published rendering

*info* · obligation `ours`

Reference implementation: `core:DocumentClassification_VAL4` (displayed as `DC_004`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

Why this is ours: The two freely published sources give different English names for five of the twelve classes, so an English name alone cannot decide conformance. We report which renderings exist and never fail a document on this basis.

**Remedy.** Either published spelling is defensible until the disagreement is resolved. Prefer the IDTA 02004 spelling if the container is destined for an Asset Administration Shell.

### `M5` — The language code is not an ISO 639 code

*error* · obligation `reference`

Reference implementation: `core:DocumentVersion_VAL7`, `core:DocumentDescription_VAL2` (displayed as `DV_007`, `DD_002`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Write the language as a two-letter ISO 639-1 code, or a three-letter ISO 639-2 code where no two-letter code exists. Regional forms such as de-DE do not belong here.

### `M6` — The document version declares no PDF file

*error* · obligation `reference`

Reference implementation: `core:DocumentVersion_VAL3` (displayed as `DV_003`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add the document as a PDF and declare it with FileFormat application/pdf. Other formats may accompany it but cannot replace it.

### `M7` — The main document is not released

*error* · obligation `reference`

Reference implementation: `core:MainDocument_VAL9` (displayed as `MD_009`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Set the main document's LifeCycleStatus to Released before handing the container over. A main document under review is not a delivery.

### `M8` — A class name carries no language this tool can check

*warning* · obligation `ours`

Why this is ours: We check German and English class names against the published table. A name tagged with neither — or with nothing at all — is not wrong, but it is unchecked, and silently unchecked is how an empty attribute turns the check off.

**Remedy.** Tag the class name with the language it is written in — de or en if you want it checked against the published table.

### `M9` — The document declares the same identifier twice in one domain

*warning* · obligation `ours`

Why this is ours: The reference implementation checks that exactly one identifier is primary; it does not check for repeats. Two identifiers that agree on both domain and value are a copy-paste or a merge that went wrong, and the recipient's system will store one and lose the other.

**Remedy.** Remove the repeated DocumentId, or correct it if two different identifiers were intended. Two DocumentIds carrying the same text under different DomainIds are fine — that is two registrations of one document, not a repeat.

### `M10` — A document identifier is empty

*error* · obligation `reference`

Reference implementation: `core:DocumentId_VAL2` (displayed as `DI_002`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Give the DocumentId element the identifier as its text. An empty identifier names nothing, and the recipient has no way to refer to this document.

## pdf

### `P1` — A file that should be a PDF is not one

*error* · obligation `reference`

Reference implementation: `processor:PV_EXCEPTION_010` (displayed as `PV_010`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Replace the file with a real PDF, or correct the declared FileFormat if the file was never meant to be one. For VDI2770_Main.pdf there is no second option: the name is reserved and the recipient's system will open it as a PDF.

### `P2` — The PDF appears to be encrypted

*warning* · obligation `ours`

Reference implementation: `processor:REP_MESSAGE_040` (displayed as `REP_040`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

Why this is ours: We look for the indirect reference the trailer is required to use, which is a strong signal — but it is a byte pattern, not a parse of the document structure, so it can be wrong in either direction. A signal that can be wrong should not fail someone's build on its own.

**Remedy.** Open the file. If it really is encrypted or password-protected, remove the protection — a document the recipient cannot open has not been handed over. If it opens fine, this is our false positive and worth an issue.

### `P3` — This scan found no PDF/A claim in the file

*warning* · obligation `ours`

Reference implementation: `processor:PV_EXCEPTION_004` (displayed as `PV_004`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

Why this is ours: The reference implementation asserts that the file carries no PDF/A identification. We assert less: that a bounded scan of the bytes did not find one. The two are different propositions and only the smaller one is ours to make, so the reference's key is cited without its claim being borrowed.

**Remedy.** Produce the file as PDF/A and make sure the exporter writes the pdfaid identification into the XMP metadata. If the file does carry one, our scan did not reach it — see docs/scope.md for what it does and does not read.

### `P4` — The PDF claims a PDF/A level; this tool did not verify the claim

*info* · obligation `ours`

Reference implementation: `processor:REP_MESSAGE_015` (displayed as `REP_015`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

Why this is ours: Verifying PDF/A conformance needs a full PDF/A validator. Reporting a claim as a verdict would be a lie, so we report it as a claim and say so every time.

**Remedy.** Run a PDF/A validator such as veraPDF if you need the claim verified. This tool only confirms that a claim is present and well-formed.

## schema

### `X0` — The schema check could not run

*error* · obligation `ours` · **about: this tool**

Why this is ours: This is about us, not about the container. It is an error because a report that silently skipped the schema check would be worse than no report — but the container may be perfectly fine, and the remedy is ours to carry out, not the reader's.

**Remedy.** Check the installation: this tool needs its `xmlschema` dependency and the schema file bundled beside it. Re-install with `pip install vdi2770-validate`, and open an issue if it persists — nothing is wrong with your container that this message can tell you about.

### `X1` — The metadata file is not well-formed XML

*error* · obligation `container`

Reference implementation: `core:XmlReader_EX3`. Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Open the file in an XML editor and fix the reported position. Nothing else can be checked until the file parses.

### `X2` — The metadata file does not conform to the published VDI 2770 schema

*error* · obligation `schema`

Source: `VDI2770_Schema_2019-08-23.xsd`.

Reference implementation: `processor:REP_MESSAGE_023` (displayed as `REP_023`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Correct the element or value at the reported line so it matches the schema VDI publishes for VDI 2770. The schema is bundled with this tool.

### `X3` — The metadata file tries to expand an entity

*error* · obligation `ours`

Why this is ours: A metadata file is data. Entity expansion lets it read local files or reach a host, which no handover document has any reason to do.

**Remedy.** Remove the DOCTYPE and entity declarations. Write the values directly.

### `X4` — The schema check could not finish on this metadata

*error* · obligation `ours` · **about: this tool**

Why this is ours: The document did something the schema checker would not follow to the end — nesting past its depth limit, for instance. We cannot say the metadata conforms and we cannot say it does not, so we say what happened instead. It is an error because a report that quietly skipped the check would be worse than no report.

**Remedy.** Simplify the metadata so the checker can reach the end of it — the reported reason says what stopped it. If the file is genuinely this shape, check it against the schema with a validator of your own: the limit that gave up belongs to this tool, not to VDI 2770.

### `X6` — This tool did not build a model of the metadata

*error* · obligation `ours` · **about: this tool**

Why this is ours: The file is well-formed XML; we declined to turn it into objects. Two ways that happens, and the detail says which: this document alone has more elements than the reader will build, or this read has already been charged its budget of them across the whole container tree — charged from the markup before the parse, because refusing a document is the expensive path and counting the tree that came back charged nothing for it. Both are the same arithmetic — the bytes were bounded and the tree built out of them was not, and the expansion between the two is the sender's to choose. 7.98 MB of nested elements compresses to a 115 KB archive, and forty containers of them to a 12 KB one. Reporting either as malformed would blame the sender for our limit, and reporting nothing would say the metadata passed checks that never ran. It is an error because nothing downstream of the model was checked.

**Remedy.** Nothing here is necessarily wrong with the metadata. The reported reason says which limit stopped us. If it is the elements in this document, that one file is larger than this tool models — check it with a validator that has no such limit. If it is the elements this read had left, the delivery as a whole is; split it and the same containers go through. Either way the limit belongs to this tool, not to VDI 2770.

## tool

### `X5` — A check in this tool raised an error and did not finish

*error* · obligation `ours` · **about: this tool**

Why this is ours: A rule that crashes has checked nothing, and a report that omits it in silence would be telling the reader the container passed that check. This is about us, not the container.

**Remedy.** Nothing in the container needs changing for this one. Please report it with the container if you can share it. Every other finding in this report still stands; only the named check did not run.
