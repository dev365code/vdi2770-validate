# The rules

Generated from [`rules.json`](../packages/vdi2770/src/vdi2770/validate/data/rules.json) by
`tools/rules_doc.py`, which also reads reason-specific remedies from the rule modules.
Edit those sources, not this page — `make check` compares them.

`obligation` says where a requirement comes from, and the vocabulary is deliberately
not MUST/SHOULD: this project has not read VDI 2770, so it never claims to quote
it. `about` separates a statement about the container from a statement about this
tool, because both are errors on purpose and severity cannot carry the difference.

- **`schema`** (1) — the XSD VDI publishes free says so, mechanically
- **`table`** (2) — a freely published table says so (IDTA 02004)
- **`container`** (4) — mechanics of ZIP and XML — true without VDI 2770
- **`reference`** (14) — observed in the MIT reference implementation, **not** verified against the guideline, which is paywalled
- **`ours`** (23) — our own judgement, and it carries a reason

44 rules.

Where each layer stands:

| layer | `schema` | `table` | `container` | `reference` | `ours` | total |
|---|---|---|---|---|---|---|
| `container` | 0 | 0 | 3 | 3 | 8 | 14 |
| `files` | 0 | 0 | 0 | 3 | 1 | 4 |
| `metadata` | 0 | 2 | 0 | 7 | 4 | 13 |
| `pdf` | 0 | 0 | 0 | 1 | 5 | 6 |
| `schema` | 1 | 0 | 1 | 0 | 4 | 6 |
| `tool` | 0 | 0 | 0 | 0 | 1 | 1 |
| **total** | **1** | **2** | **4** | **14** | **23** | **44** |

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

A finding these lines do not name takes the remedy above.

- When the finding says the tree names more members than this read will hold: Split the delivery. This tool holds a record for every file named across the whole tree of containers, and this one names more than it will hold.
- When the finding says `<count> entries, limit is <limit>`: Split the delivery: this archive lists more members than this tool will open in one container.
- When the finding says `the archive says <size> bytes, over the` limit, or a folder's members exceed it: The archive declares that member larger than this tool will read — nothing here inflated it to check. Send it on its own, or check it with something that has no such limit — the rest of the container was read normally.
- When the finding says `the archive says it expands` past this tool's ratio limit: That member expands far more than its stored size suggests, which is the shape of an archive built to exhaust whoever opens it. If it is a genuine uncompressed scan, send it separately: this tool will not inflate it.
- When the finding says `the sizes this archive declares add up to` more than this tool will read: Split the delivery into several containers. This one holds more than this tool will read in a single archive.
- When the finding says `<size> bytes; this tool parses at most <limit>`: The metadata file is larger than this tool will parse. Split the documents across several containers so each one's metadata is smaller.
- When the finding says this read has opened its limit of containers, or reading metadata would pass its byte limit: Split the delivery, or run this tool on the inner containers separately. It opens a bounded number of containers in one pass, and the ones named here were not opened at all.
- When the finding says `this read has inflated` its allowance: Split the delivery, or run this tool on the inner containers separately. Past its inflation ceiling the remaining members are still listed, but nothing has checked that they can be read.
- When the finding says `this read spent its <limit> GiB budget for inflating PDF streams`: Split the delivery into several containers, or re-export PDFs with smaller compressed structures. The PDF/A claim search stops once it finds a claim, but page-tree reading may also need inflation. The header, indirect-object probe and encryption check still ran; P6 names any page-count comparison this budget prevented.

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

Why this is ours: This rule cites no reference message key and rests on no line of the guideline. A documentation container whose only content is its own main document delivers nothing, which is worth saying out loud. The judgement is this tool's own, which is why it is a warning and not an error.

**Remedy.** Add the document containers this handover is supposed to deliver. A documentation container with only a main document delivers no documents.

### `Z9` — The archive stores files in folders

*warning* · obligation `reference`

Reference implementation: `processor:ZU_MESSAGE_001` (displayed as `ZU_001`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Store the members at the root of the archive. This tool resolves a metadata name that carries its folder path, so the file-set rules can stay quiet — but the reference implementation warns about the folders anyway, and it is the recipient's tooling that has to accept the container.

A finding these lines do not name takes the remedy above.

- When a folder it names is one the `Z13` beside it reports: Store the members at the root of the archive. This tool resolves a metadata name that carries its folder path, so the file-set rules can stay quiet — but the reference implementation warns about the folders anyway, and it is the recipient's tooling that has to accept the container. Not by hand for `<member>`: the finding beside this one says that folder is a container this tool did not open, and zipping it into a .zip member is what removes the folder without flattening what is inside it.
- When a folder it names holds a reserved name: Store the members at the root of the archive. This tool resolves a metadata name that carries its folder path, so the file-set rules can stay quiet — but the reference implementation warns about the folders anyway, and it is the recipient's tooling that has to accept the container. Not by hand for `<member>`: it holds `<reserved-name>`, which makes it a container delivered unzipped, and zipping it into a .zip member is what removes the folder without flattening what is inside it.

### `Z10` — Two members of the archive have the same name

*error* · obligation `ours`

Why this is ours: ZIP allows it and readers disagree about which one wins, so the container can show one thing to this tool and another to whoever unpacks it. Nothing good is ever delivered this way. Four relations reach this rule and each gets the sentence that is true of it: two entries that extract to one path, two spellings of one name, names that come to one once both are settled, and names that are one file wherever case is not kept apart — macOS as it ships, and every Windows filesystem. The last is the only one the archive itself keeps apart, which is why the sentence names the condition instead of calling them the same name.

**Remedy.** Rebuild the archive with one entry per name, and with no two entries sharing a name once case is folded. If two files genuinely differ, give them names that differ by more than case, and declare both.

A finding these lines do not name takes the remedy above.

- When the finding says `<count> entries in this archive carry this name`: Rebuild the archive with one entry per name. More than one entry shares this one, so nothing here can say which bytes you meant and none was read — a reader that guessed would show you one file and your unpacker another.
- When the finding says `Two members of the archive extract to the same path`: Store the file once, at one path. Which of them a recipient ends up with is their unzip tool's business, and nothing here can say which one you meant.
- When the finding says `Two members of the archive come to one name`: Store the file once, under one spelling and one path. On a filesystem that composes names — macOS, Windows — these are one file and the later member wins; on one that does not, they are two. Nothing here can say which your recipient has.
- When the finding says two spellings print alike: Store one spelling. A reader asking for the name as you wrote it may get either member, and nothing here can say which one you meant.
- When the finding says two names become one when case is folded: Rebuild the archive with one entry per name once case is folded, and name each DigitalFile after the entry you kept. Rename as you write the archive rather than on disk: a filesystem that folds case cannot hold both of these side by side, so there is nothing there to rename.

### `Z11` — A document container carries another container inside it

*error* · obligation `ours`

Why this is ours: Document containers hold a document's files. A container inside one is either a mistake or a way to carry something past a check that only looks at declared files.

**Remedy.** Move the inner container up into the documentation container, where containers belong. If it is payload rather than a container, it takes two things: declare it in this document container's metadata as a DigitalFile with FileFormat application/zip, and make sure its root does not hold VDI2770_Metadata.xml or VDI2770_Main.xml — a reserved name at the root is what makes an archive a container, and a declaration saying otherwise is a disagreement this tool reports rather than resolves.

A finding these lines do not name takes the remedy above.

- When the finding says a declared file is a container whose root holds a reserved name: Move it up into the documentation container if it is a container, or — if it is genuinely payload — rename the reserved file inside it, which is what makes it one.
- When the finding says a folder holds `VDI2770_Metadata.xml` or `VDI2770_Main.xml`, which makes it a container delivered unzipped: Move it up into the documentation container, zipped or as it is, where containers belong. If what it holds are this document's own files, rename the reserved file in it, which is what makes the folder a container.

### `Z12` — An entry in the container was refused

*error* · obligation `container`

**Remedy.** Re-create the archive and send it again. A member with a broken CRC is usually a truncated transfer; a member that needs a password has not been handed over, because the recipient cannot open it.

A finding these lines do not name takes the remedy above.

- When the finding says the entry needs a password: Remove the password from this member before handing the container over. A recipient who cannot open a file has not been given it, and nothing here can check what it cannot read.
- When the finding says an Info-ZIP Unicode Path field names another file, or occurs more than once: Give the entry one name. An Info-ZIP Unicode Path field (APPNOTE 4.6.9) holds the UTF-8 version of the name its header already carries; this entry's says something else, or there is more than one, and readers then differ on which file it is -- zipping the same files again writes the same fields. Store the name once, in UTF-8 with general purpose bit 11 set (APPNOTE 4.4.4), or leave the field out.
- When the finding says `its local header, at byte …` or `its data runs to byte …`, about where the entry lies: Rebuild the archive with a standard ZIP tool. No ordinary writer lays an entry out this way -- its bytes are read as another entry's too, or reach into or past the central directory (APPNOTE 4.3.6) -- so sending this file again draws the same finding; the files themselves may be fine.
- When the finding says `member compressed with <method>`: Recompress this member with deflate, or store it, and send the container again. It is compressed with `<method>`, and this tool expands stored and deflate members and no other method, so zipping it again the same way draws the same finding; the file itself may be fine.

### `Z13` — A folder holds a container this tool did not open

*error* · obligation `ours` · **about: this tool**

Why this is ours: A folder holding VDI2770_Metadata.xml or VDI2770_Main.xml is a container that was not zipped, and this tool reads it as the container it is, as the reference implementation does. This one it did not open — its metadata could not be read, or a limit this tool puts on one read was reached: how deep, how large, how many containers — so everything inside is unchecked, and a report that said nothing would be telling the reader it passed. The limit is ours rather than a fault of the delivery.

**Remedy.** Nothing here is necessarily wrong with the container. The finding beside this one says why the folder was not opened; once that is put right the folder is checked like any other container.

### `Z14` — A declared file is an archive whose contents are not judged as VDI 2770

*info* · obligation `ours`

Why this is ours: A file the metadata declares is part of a document's content, not of the container's structure, so what is inside it is its own business, the way what is inside a PDF is: nothing in it is judged as VDI 2770, not a container and not a metadata file. The reference implementation reports nothing about what is inside one either. For one this reader opens, how the archive stores its entries is still reported -- a name that climbs out, an entry that cannot be read, a name stored twice -- because that is true of any archive handed over, whatever it holds; one the depth limit keeps closed is reported as not opened, and nothing in it is read. Saying so every time keeps a reader from taking the archive's contents as checked.

**Remedy.** Nothing to change if the archive is the document's content. If it holds documents meant to be checked as VDI 2770 containers, put them in the documentation container as containers of their own rather than inside a document's file.

## files

### `F1` — A file named in the metadata is not in the container

*error* · obligation `reference`

Reference implementation: `processor:REP_MESSAGE_007` (displayed as `REP_007`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add the missing file to the container, or remove its DigitalFile entry from the metadata. The two must agree.

A finding these lines do not name takes the remedy above.

- When the finding says `A file named in the metadata matches more than one member of the container`, with names that print alike: Store one spelling. The names below are different bytes that print the same, so nothing can say which of them this declaration meant — and a reader asking for the name you wrote may get either.
- When the finding says `A file named in the metadata matches more than one member of the container`, with names that extract to the same path: Store the file once, at one path. The names below are different bytes that extract to the same place, so nothing can say which of them this declaration meant — and which one a recipient ends up with is their unzip tool's business.
- When the finding says `A file named in the metadata is in the container more than once`: Remove the repeats. The name denotes more than one member, and which one a reader extracts is its own business — so this tool will not say which of them you declared.
- When the finding says `A file named in the metadata is in the container under a name read as IBM Code Page 437`: The member '`<member>`' stores this name as UTF-8 bytes without general purpose bit 11 (APPNOTE 4.4.4), so it reads as IBM Code Page 437 (APPENDIX D). Set bit 11 on that entry -- or write the archive with a tool that sets it -- for the name to read as UTF-8.
- When the finding says `A file named in the metadata is in the container and this tool declined to read it`: Nothing here is necessarily wrong with the file: it is inside a limit this tool sets for untrusted input, and the finding beside this one says which. Send it separately, or check it with something that will read it.
- When the finding says `A file named in the metadata has a name that would escape the extraction directory`: Rename the member and the DigitalFile that names it, to a plain relative path inside the container. This tool never read those bytes: the name is what it refused, and the finding beside this one says why. Re-creating the archive from the same tree writes the same name.
- When the finding says `A file named in the metadata is in the container and needs a password`: Remove the password from this member before handing the container over. A recipient who cannot open a file has not been given it, and nothing here can check what it cannot read.
- When the finding says `A file named in the metadata is in the container under an entry that names itself more than once`: Give the entry one name. An Info-ZIP Unicode Path field (APPNOTE 4.6.9) holds the UTF-8 version of the name its header already carries; this entry's says something else, or there is more than one, and readers then differ on which file it is -- zipping the same files again writes the same fields. Store the name once, in UTF-8 with general purpose bit 11 set (APPNOTE 4.4.4), or leave the field out.
- When the finding says `A file named in the metadata is in the container under an entry laid out where no ordinary writer puts one` (`its local header, at byte` or `its data runs to byte`): Rebuild the archive with a standard ZIP tool. No ordinary writer lays an entry out this way -- its bytes are read as another entry's too, or reach into or past the central directory (APPNOTE 4.3.6) -- so sending this file again draws the same finding; the files themselves may be fine.
- When the finding says `A file named in the metadata is in the container, compressed with a method this tool does not expand`: Recompress this member with deflate, or store it, and send the container again. It is compressed with `<method>`, and this tool expands stored and deflate members and no other method, so zipping it again the same way draws the same finding; the file itself may be fine.
- When the finding says `A file named in the metadata is in the container but could not be read`: Re-create the archive and send it again. The file is listed, so the metadata is right; the bytes behind the name are not readable.
- When the finding says `A file named in the metadata is in the container under a name no declaration can reach`: Rename the member to the name you declared. Writing the space into the metadata does not help: it is read back without it, which is what lets an ordinary indented declaration work at all.

### `F2` — A file in the container is not named in the metadata

*warning* · obligation `reference`

Reference implementation: `processor:REP_MESSAGE_006` (displayed as `REP_006`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Declare the file as a DigitalFile in the metadata, or remove it from the container. An undeclared file is invisible to the recipient's system.

A finding these lines do not name takes the remedy above.

- When the finding says the other kind's classifying name is present at the root: Remove or rename the classifying name you did not mean. An archive that answers to both kinds is a different delivery depending on who opens it, and declaring this file would only make that silent.
- When the name it reports has whitespace at its edge: Rename the member: whitespace at the edge of a name cannot be declared, because the metadata's text is read with it removed. Or remove the member from the container.

### `F3` — The declared file format disagrees with the file name

*warning* · obligation `ours`

Reference implementation: `core:DigitalFile_VAL2`, `core:DigitalFile_VAL3` (displayed as `DF_002`, `DF_003`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

Why this is ours: The reference implementation was observed refusing one media-type-and-name disagreement, and that is the whole of what was observed: across the swept corpus its DF_002 fires once and DF_003 never. Which other media types have an extension that is not a matter of taste is this project's judgement. The table names fifteen and leaves out text/plain, which is honestly carried by .txt, .log, .md and .csv -- a rule that guessed there would report a correct delivery. So a finding here is our reading, and the cited keys are evidence for the question rather than for the answer.

**Remedy.** Make FileFormat and the file name agree. This rule knows the extensions for a fixed list of media types and says nothing about the rest, so a finding here means the declared type has one customary extension and this file does not carry it.

### `F4` — A declared file has no name

*error* · obligation `reference`

Reference implementation: `core:DigitalFile_VAL4` (displayed as `DF_004`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Give the DigitalFile element the file's name as its text, or remove the element. An empty name means the metadata promises a document and names nothing.

## metadata

### `M1` — The document carries no VDI 2770 classification

*error* · obligation `reference`

Reference implementation: `core:Document_VAL2` (displayed as `D_002`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add a DocumentClassification whose ClassificationSystem is VDI2770:2018 and whose ClassId is one of the twelve published classes.

A finding these lines do not name takes the remedy above.

- When the finding says `this metadata's names are in` another namespace, or `in no namespace at all`: Declare the VDI 2770 namespace on the root element — xmlns="http://www.vdi.de/schemas/vdi2770" — or put the prefix that binds it on every element and not only on the root. The schema declares its elements qualified, so a file in another namespace, or in none, holds no VDI 2770 names at all, and nothing else in this report could look at the metadata's content.

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

A finding these lines do not name takes the remedy above.

- When the finding says `The English class name is not the published one`: Use the published English name, or drop the English name: matching here is keyed on the class id and the German name, which both sources give the same for all twelve.

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

### `M11` — The main document refers to a document this delivery does not carry

*error* · obligation `reference`

Reference implementation: `core:Document_VAL4` (displayed as `D_004`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add the document container holding the document this relationship names, or remove the DocumentRelationship. A main document is the list a recipient reads to find out what arrived, so a reference into nothing sends them looking for a document that is not there.

### `M12` — A document refers to a document this delivery does not carry

*error* · obligation `reference`

Reference implementation: `core:Document_VAL4` (displayed as `D_004`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Add the document this relationship names, or remove the relationship. The container this points from promises a document the handover does not deliver, and a recipient reading the metadata has no way to tell the difference between a document that is missing and one that was never meant to travel.

### `M13` — One identifier is called both a type and an individual

*warning* · obligation `ours`

Why this is ours: Nobody told us this. ObjectType distinguishes a product model from the one machine carrying that serial, and a delivery that files the same identifier under both has contradicted itself -- which holds without reading the guideline, because no reading makes a number a model and an instance of it at once. The guideline is paid and unread here, so we do not claim it says so. The observation is one: ABC1223 in objectreferences.zip, a Type in one document container and an Individual in its sibling. The broader question -- whether a documentation container must share an object with the documents it bundles -- is not asked by any rule here, because a plant-level bundle carrying sub-component documents may differ for good reasons and we cannot cite anything that forbids it.

**Remedy.** Decide which the identifier names and say the same thing in both places: ObjectType="Type" for a product model, ObjectType="Individual" for one manufactured item. If the two documents really are about different things, give them different identifiers.

## pdf

### `P1` — A file that should be a PDF is not one

*error* · obligation `reference`

Reference implementation: `processor:PV_EXCEPTION_010` (displayed as `PV_010`). Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Replace the file with a real PDF, or correct the declared FileFormat if the file was never meant to be one. For VDI2770_Main.pdf there is no second option: the name is reserved and the recipient's system will open it as a PDF.

A finding these lines do not name takes the remedy above.

- When the finding says the reserved main document has no indirect object within this scan: If this is a real PDF, re-export it: a file that fills its own beginning with `obj` before its first indirect object is not something a producer writes, and whatever wrote this is worth looking at. If it is not a PDF, the name is reserved and the recipient's system will open it as one, so put the main document here. If you believe this is a conforming file this tool cannot read, please report it with the file.

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

A finding these lines do not name takes the remedy above.

- When the finding says a PDF/A part 1, 2 or 3 claim has no conformance level: Parts 1, 2 and 3 of PDF/A each require a conformance level beside the part. Re-export with a producer that writes one into the XMP metadata, then run a PDF/A validator such as veraPDF if you need the claim itself verified.

### `P5` — A declared PDF could not be confirmed to be a PDF document

*error* · obligation `ours` · **about: this tool**

Why this is ours: The scan for an indirect object is bounded, and a file can end that scan without answering it -- a comment is legal between any two tokens, so a conforming file may in principle reach the bound. Reporting that as "not a PDF" would be a fact about our budget dressed as a fact about the file, and reporting nothing let a budget pass for a verdict: the sole declared rendition of a document could be a file nobody could confirm and the container came back clean. An error because that is this project's one policy for every limit it declines to spend -- if we did not look, exit 0 tells somebody we did -- and because every declared rendition owes something: `M6` says other formats may accompany a PDF and cannot replace it. The reserved main document draws `P1` instead, where the recipient's system will open the file as a PDF whatever we could confirm.

**Remedy.** If this is a real PDF, re-export it and look at whatever wrote it: a file that fills its own beginning with `obj` before its first indirect object is not something a producer writes. If it is not a PDF, correct the declared FileFormat or replace the file. If you believe this is a conforming file this tool cannot read, please report it with the file.

### `P6` — The metadata and the PDF's page tree declare different page counts

*warning* · obligation `ours`

Source: `ISO 32000-1:2008 §7.7.3.2 Table 29`.

Why this is ours: This compares two declarations to surface a wrongly attached file, a revision mismatch, or a template placeholder. The public XSD gives NumberOfPages a positiveInteger type but does not establish this comparison as a VDI obligation. The PDF root Count is the file's declaration, not a count of rendered leaves, so this project's comparison is a warning.

**Remedy.** Correct NumberOfPages if the metadata is wrong; otherwise check that this is the intended PDF revision and verify its page tree's Count. This compares declarations, not rendered pages.

A finding these lines do not name takes the remedy above.

- When the finding says `The PDF's page tree could not be read`: Check that this is the intended PDF and verify its xref and page tree. Re-export it if appropriate; this bounded reader does not recover damaged xref data or evaluate structures beyond its limits. No page-count comparison was made.

## schema

### `X0` — The schema check could not run

*error* · obligation `ours` · **about: this tool**

Why this is ours: This is about us, not about the container. It is an error because a report that silently skipped the schema check would be worse than no report — but the container may be perfectly fine, and the remedy is ours to carry out, not the reader's.

**Remedy.** Check the installation: this tool needs its `xmlschema` dependency and the schema file bundled beside it. Re-install with `pip install vdi2770-validate`, and open an issue if it persists — nothing is wrong with your container that this message can tell you about.

### `X1` — The metadata file is not well-formed XML

*error* · obligation `container`

Reference implementation: `core:XmlReader_EX3`. Citing a key records that the other project checks something in the same area; it does not borrow its claim.

**Remedy.** Open the file in an XML editor and fix the reported position. Nothing else can be checked until the file parses.

A finding these lines do not name takes the remedy above.

- When the finding says `the document is in <encoding>, as its first bytes say, and this reader does not read <encoding>`: Save the metadata as UTF-8 (or UTF-16) and send it again.

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

A finding these lines do not name takes the remedy above.

- When the finding says the schema violation listing reached its limit: Correct the violations this report does list and run it again; the ones past the limit are reported once there is room for them. They are your document's, not this tool's — only the stopping is ours.

### `X6` — This tool did not build a model of the metadata

*error* · obligation `ours` · **about: this tool**

Why this is ours: The file is well-formed XML; we declined to turn it into objects. Two ways that happens, and the detail says which: this document alone has more elements than the reader will build, or this read has already been charged its budget of them across the whole container tree — charged from the markup before the parse, because refusing a document is the expensive path and counting the tree that came back charged nothing for it. Both are the same arithmetic — the bytes were bounded and the tree built out of them was not, and the expansion between the two is the sender's to choose. 7.98 MB of nested elements compresses to a 115 KB archive, and forty containers of them to a 12 KB one. Reporting either as malformed would blame the sender for our limit, and reporting nothing would say the metadata passed checks that never ran. It is an error because nothing downstream of the model was checked.

**Remedy.** Nothing here is necessarily wrong with the metadata. The reported reason says which limit stopped us. If it is the elements in this document, that one file is larger than this tool models — check it with a validator that has no such limit. If it is the elements this read had left, the delivery as a whole is; split it and the same containers go through. Either way the limit belongs to this tool, not to VDI 2770.

## tool

### `X5` — A check in this tool raised an error and did not finish

*error* · obligation `ours` · **about: this tool**

Why this is ours: A rule that crashes has checked nothing, and a report that omits it in silence would be telling the reader the container passed that check. This is about us, not the container. It cannot say which other checks went quiet with it: rules that decline their case to another layer decline it whether that layer failed or was never asked.

**Remedy.** Nothing in the container needs changing for this one. Please report it with the container if you can share it. Every finding in this report still stands — but what did not run is the named check together with anything in this tool that leaves its case to it, so read the report as incomplete rather than as a verdict.
