# vdi2770

Read a VDI 2770 handover-documentation container and get back a typed model —
without extracting anything to disk, without opening a socket, and without any
dependencies.

```bash
pip install vdi2770
```

```python
import vdi2770

box = vdi2770.read_container_file("handover.zip")
for c in box.walk():
    if c.metadata_bytes is None:
        continue
    doc = vdi2770.build_document(vdi2770.parse_xml(c.metadata_bytes), c.where)
    print(c.path, [(i.domain_id, i.id) for i in doc.identifiers],
          [k.class_id for k in doc.classifications])
```

```
handover.zip [('SUPPLIER', 'DOC-2024-0001')] ['03-01']
handover.zip!/pumps.zip [('SUPPLIER', 'DOC-2024-0002')] ['02-04']
```

## It decides nothing

There is no `is_valid()` here, on purpose. Whether a container is *correct* is a
question about VDI 2770, and the answer depends on which supplement your customer
sent you. This library tells you what is in the file and where it is written; the
opinion is yours to supply.

If you want an opinion supplied for you, [`vdi2770-validate`](https://pypi.org/project/vdi2770-validate/)
is this library plus a rule set, as a command-line tool.

## Three properties, each tested rather than promised

**Nothing is extracted to disk.** Members are decompressed into memory under a
budget and dropped. There is no temporary directory to clean up and no path
traversal to get wrong, because no path is ever joined.

**Nothing is fetched.** No socket is opened for any input, ever — including XML
that asks for one. An entity declaration is refused outright rather than
resolved-but-locally, so there is no parser setting to get wrong later.

**A refusal is reported, not raised.** A member that blows a budget becomes a
`Defect` on the container and the read continues, so one hostile file inside a
supplier archive does not cost you the other four hundred.

## What comes back

`read_container(data, name)` returns a `Container`:

| | |
|---|---|
| `path` | `handover.zip!/pumps.zip` — the JAR convention, so it stays greppable |
| `kind` | `DOCUMENTATION`, `DOCUMENT`, `UNKNOWN`, or `UNREADABLE` |
| `members`, `file_names` | what the reader can open — the budget filter and the readability sweep have both run |
| `present` | every file name the archive declares, including members that were refused. Whether a name is there is a fact about the directory; being unable to inflate the bytes behind it does not unsay it |
| `metadata_bytes`, `metadata_name` | the metadata that was found, if any |
| `children`, `walk()` | inner containers, opened to three levels |
| `defects` | what the reader could not do, and why |
| `rejected` | members present in the archive but refused, and why |
| `near_misses` | reserved name → `(kind, the member name that nearly matched, as the archive spells it)`, kind being `in-a-subfolder`, `path-prefixed`, `case-differs` or `case-differs-elsewhere`. `vdi2770_metadata.xml` in an archive with no metadata is worth saying; how to say it is yours, not ours |
| `duplicate_names` | a ZIP may carry the same name twice; readers disagree about which one wins |

`build_document(node, where)` returns a `Document` whose every node carries a
`Location` with the line and column it was written at, which is the reason this
package parses XML itself instead of handing you an `ElementTree`.

`read_pdf(data)` returns four facts and no verdict: `is_pdf`, `header`,
`encrypted`, and `pdfa_claim` — the last being what the file's own metadata
*claims*, such as `"2b"`. Nothing here verifies that claim. Verifying PDF/A takes
a PDF/A validator, and this is not one.

### Defect kinds

`not-a-zip`, `too-many-members`, `unsafe-member-name`, `member-too-large`,
`suspicious-compression`, `archive-too-large`, `metadata-too-large`,
`metadata-unreadable`, `member-unreadable`, `nesting-too-deep`,
`container-budget-exhausted`, `decompression-budget-exhausted`,
`member-budget-exhausted`, `ambiguous-name`, `nameless-member`.

These strings are part of the public surface; a test in this package fails if the
code grows a kind that this list does not name.

`vdi2770.REFUSAL_KINDS` is the subset of those that can name a member in
`Container.rejected` — what a caller needs a sentence for. Working that subset
out by reading this module's source is how two of them came to be missed.

The last three are the budgets that span the whole read rather than one archive: a
documentation container may legitimately hold hundreds of inner containers, and
their metadata is held for as long as you walk the tree. Ten thousand of them,
each with sixteen megabytes of metadata, is a permitted input under every
per-archive limit and about 156 GiB of memory — and the same tree can ask the
readability sweep to inflate terabytes while no single member is over its cap.
`MAX_CONTAINERS` and `MAX_TOTAL_METADATA_BYTES` bound the first,
`MAX_TOTAL_DECOMPRESSED` the second. `MAX_TOTAL_MEMBERS` bounds a third thing
the other two do not: this package keeps one record per entry named anywhere
in the tree, and ten thousand entries in each of a thousand archives is ten
million of them whatever their bytes weigh. Hitting any of them is reported
rather than silently truncating the tree.

## Supported

Python 3.9 and up. The budgets are module constants in `vdi2770.zipread` — per
archive: `MAX_MEMBERS`, `MAX_MEMBER_BYTES`, `MAX_TOTAL_BYTES`, `MAX_RATIO` with
its `MIN_SUSPICIOUS_BYTES` floor, `MAX_METADATA_BYTES`, `MAX_CONTAINER_LEVELS`;
across one read: `MAX_CONTAINERS`, `MAX_TOTAL_METADATA_BYTES`,
`MAX_TOTAL_DECOMPRESSED`, `MAX_TOTAL_MEMBERS`. `vdi2770.xmlread` adds
`MAX_ELEMENTS`, `MAX_TEXT_PIECES`, `MAX_ATTRIBUTES_PER_ELEMENT` and
`MAX_ATTRIBUTES`. The first bounds the tree built out of one metadata file — the
bytes were bounded and that tree was not, and the expansion between them is the
sender's to choose. The second bounds the text hung off it, which the element
count does not see: a document of three elements whose text is 450,000 character
references — a 4.1 KiB archive — held 48 MB before this bound existed and holds
23 MB now. The last two bound the
attributes hung off it, which neither of the others sees: attributes are cheap
to write and the schema check downstream is quadratic in how many sit on one
element, so 12,000 of them in a 27 KiB archive cost 13.6 seconds. `vdi2770.pdfread` has nine of its own for the PDF scan:
`MAX_STREAMS`, `MAX_STREAM_SCAN`, `MAX_INFLATED_PER_STREAM`,
`MAX_INFLATED_TOTAL`, `MAX_XMP_PACKETS`, `MAX_PDFA_PREFIXES`,
`MAX_TRAILER_SCAN` with `MAX_TRAILER_BYTES` and the `MAX_TRAILERS` the second is
derived from — one bounds how much of a single trailer dictionary is read and
the other how much all of them together may cost. Every trailer in the file is
a candidate, newest first, because a bound on *how many* to read is a bound on
where to look, and whoever appends to a file can push the real trailer past
one. A test fails if
either module grows one this list does not name. You can read them all, and they
are deliberately not arguments, so a caller cannot turn them off by accident.

## Unofficial

Not affiliated with, endorsed by, or connected to VDI, the Digital Data Chain
Consortium, or IDTA. VDI 2770 is a guideline published by the Verein Deutscher
Ingenieure; this is an independent reader for the container format it describes,
written without access to the guideline text, which is sold rather than
published. What that means for what this library can and cannot claim is spelled
out in the [validator's scope note](https://github.com/dev365code/vdi2770-validate/blob/main/docs/scope.md).

Apache-2.0.
