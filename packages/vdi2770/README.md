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
    print(c.path, doc.ids, [k.class_id for k in doc.classifications])
```

```
handover.zip ('DOC-2024-0001',) ['03-01']
handover.zip!/pumps.zip ('DOC-2024-0002',) ['02-04']
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
| `members`, `file_names` | what is in the archive, after the budget filter |
| `metadata_bytes`, `metadata_name` | the metadata that was found, if any |
| `children`, `walk()` | inner containers, opened to three levels |
| `defects` | what the reader could not do, and why |
| `rejected` | members present in the archive but refused, and why |
| `near_misses` | `vdi2770_metadata.xml` in an archive that has no metadata — the name is case-sensitive, and silence about that is unkind |
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
`container-budget-exhausted`.

These strings are part of the public surface; a test in this package fails if the
code grows a kind that this list does not name.

The last one is the only budget that spans the whole read rather than one
archive: a documentation container may legitimately hold hundreds of inner
containers, and their metadata is held for as long as you walk the tree. Ten
thousand of them, each with sixteen megabytes of metadata, is a permitted input
under every per-archive limit and about 156 GiB of memory. `MAX_CONTAINERS` and
`MAX_TOTAL_METADATA_BYTES` bound that; hitting either is reported rather than
silently truncating the tree.

## Supported

Python 3.9 and up. The budgets — member count, member size, total size,
compression ratio, metadata size, nesting depth — are module constants in
`vdi2770.zipread`, so you can read them, and they are deliberately not
arguments, so a caller cannot turn them off by accident.

## Unofficial

Not affiliated with, endorsed by, or connected to VDI, the Digital Data Chain
Consortium, or IDTA. VDI 2770 is a guideline published by the Verein Deutscher
Ingenieure; this is an independent reader for the container format it describes,
written without access to the guideline text, which is sold rather than
published. What that means for what this library can and cannot claim is spelled
out in the [validator's scope note](https://github.com/dev365code/vdi2770-validate/blob/main/docs/scope.md).

Apache-2.0.
