| Axis | Now | 1.0 condition |
|---|---|---|
| Coverage | 28 of 42 rules have a fixture pair | 39 of 42, every rule that can have one |
| Explanation | what is wrong, evidence, remedy, source | + the line, for every metadata finding |
| Report contract | schemaVersion, golden, exit codes, schema | met |
| Entrances | command line, library, single file, Action | + browser, nothing installed |
| Input safety | read budgets, advisory, own mutations | + declared encodings read without loss |
| Upstream | pinned by commit | + checked weekly for change |

**Explanation** — 4 of 5:
- what is wrong, in one sentence — done (`README.md`: "Three parts, every time: what is wrong")
- the evidence as read from the file — done (`README.md`: "the evidence as read from your file")
- a remedy, for every rule — done (`README.md`: "A rule without a remedy does not ship")
- the source of every rule's requirement — done (`README.md`: "each rule carries where its requirement comes from")
- the line, for every metadata finding — not yet

**Report contract** — 4 of 4:
- schemaVersion in every report — done (`docs/golden-report.json`: ""schemaVersion": 1, "summary": {")
- a golden report held by a test — done (`tools/golden_report.py`: "The whole report for one container, kept as a file a diff can be read from")
- exit codes under test — done (`tests/test_cli.py`: "is where the exit codes are written down")
- a field-by-field schema page — done (`docs/report-schema.md`: "This page is what is in an element")

**Entrances** — 4 of 5:
- command line — done (`pyproject.toml`: "vdi2770-validate = "vdi2770_validate.entry:run"")
- Python library — done (`README.md`: "from vdi2770 import read_container_file")
- single file, nothing to install — done (`tools/build_zipapp.py`: "Build the single-file form")
- GitHub Action — done (`action.yml`: "Check VDI 2770 document containers in a workflow")
- browser, nothing installed — not yet

**Input safety** — 3 of 4:
- read budgets, per member and per archive — done (`SECURITY.md`: "Per-member size, total size, member count and compression-ratio caps")
- a security fix ships with an advisory — done (`SECURITY.md`: "a security fix that ships in a release gets a GitHub security advisory")
- tests verified against their own mutations — done (`tools/mutation_table.py`: "Every claim this project makes about a gate, as a mutation somebody can run")
- declared encodings read without loss — not yet

**Upstream** — 1 of 2:
- upstream corpus pinned by commit — done (`corpus/MANIFEST.json`: ""repo": "DigitalDataChainConsortium/vdi2770", "commit":")
- checked weekly for change — not yet

Before it calls a release 1.0, this project asks of itself — Coverage: 39 of 42, every rule that can have one; Explanation: what is wrong, in one sentence · the evidence as read from the file · a remedy, for every rule · the source of every rule's requirement · the line, for every metadata finding; Report contract: schemaVersion in every report · a golden report held by a test · exit codes under test · a field-by-field schema page; Entrances: command line · Python library · single file, nothing to install · GitHub Action · browser, nothing installed; Input safety: read budgets, per member and per archive · a security fix ships with an advisory · tests verified against their own mutations · declared encodings read without loss; Upstream: upstream corpus pinned by commit · checked weekly for change.
