# What it catches, and where it stands

The picture on the [front page](https://github.com/dev365code/vdi2770-validate#where-it-stands)
draws six things this tool holds itself to, measured on the code this page
describes, against what it asks of itself before it calls a release 1.0. This
page is the evidence behind each of them: a case first, then what stands now,
then the 1.0 condition and the reason for it. Every case can be rerun from a
clone of this repository after `make fixtures`.

## Coverage

**Case.** `tests/fixtures/m2-unknown-class-id.zip` is the sample container
`corpus/examples/container/documentcontainer.zip` with one class id changed to
`99-99`. The sample draws no error and no warning; the changed container draws

```
  error  M2  The class id is not one of the published VDI 2770 classes
         at m2-unknown-class-id.zip!/VDI2770_Metadata.xml:13:4
         ClassId '99-99'
```

and exits `1`. Rerun it with
`vdi2770-validate check tests/fixtures/m2-unknown-class-id.zip`.

**Now.** 28 of 42 rules have a minimal fixture pair like this one: a container
that breaks the rule, built from one that does not. `tools/make_fixtures.py`
records which fixture each one is built from, and `tests/test_readme_sample.py`
holds the README's sentence to that count.

**1.0.** 39 of 42, every rule that can have one. Two rules cannot fire from any
container: `X0` reports that this tool's own installation is broken, and `X5`
that one of its own steps raised. And `P4`, which notes a claim of PDF/A
conformance this tool does not verify, fires on every conforming container: a
conforming container carries a PDF, and a readable PDF either makes that claim
or draws `P3` for not making it. Every other rule can have a pair, the rule for
*this file is not a ZIP* included: a conforming document container cut short
is not one.

## Explanation

**Case.** The finding above, part by part: what is wrong (*The class id is not
one of the published VDI 2770 classes*), the evidence as read from the file
(`ClassId '99-99'`, at line 13, column 4 of the metadata), where the requirement
comes from (*per a table published free (IDTA 02004)*), and the remedy (*Use one
of: 01-01, 02-01, …*). A finding with nothing to quote points at what it is
about instead: the member an undeclared file is, or the line an empty
identifier is on.

**Now.**

- what is wrong, in one sentence — done
- the evidence as read from the file — done
- a remedy, for every rule — done
- the source of every rule's requirement — done; [docs/rules.md](rules.md) lists
  each rule's source and remedy
- the line, for every metadata finding — not yet

**1.0.** A finding about the metadata carries a line and column where the check
knows one, as the case above does, and nothing yet requires every such finding
to. The condition is a test that does, so that a rule written later cannot drop
it without the build saying so.

## Report contract

**Case.** `vdi2770-validate check --json tests/fixtures/m2-unknown-class-id.zip`
exits `1` and writes a JSON array with one element, which carries
`"schemaVersion": 1`. The whole report for one container is kept as
`docs/golden-report.json`, and `python tools/golden_report.py --check` fails
when the tool says anything else about it.

**Now.**

- schemaVersion in every report — done
- a golden report held by a test — done
- exit codes under test — done
- a field-by-field schema page — done; [docs/report-schema.md](report-schema.md)

**1.0.** Met. What 1.0 adds here is a commitment, stated in the README: the
report's `schemaVersion` is `1`, and 1.0 commits to not changing it.

## Entrances

**Case.** One container, one verdict, through each door that exists:

- the command line: `vdi2770-validate check tests/fixtures/m2-unknown-class-id.zip`
  exits `1`, and the sample container exits `0`;
- the single file: `python tools/build_zipapp.py` builds `dist/vdi2770.pyz`, and
  `python dist/vdi2770.pyz check` gives the same two exit codes on the same two
  containers;
- the Python library: `from vdi2770 import read_container_file` reads the
  archive the command reads, and `import vdi2770_validate` is the command's own
  package;
- the GitHub Action: the README's *In a workflow* section runs the same check
  in a workflow and hands the exit code to the next step.

**Now.**

- command line — done
- Python library — done
- single file, nothing to install — done
- GitHub Action — done
- browser, nothing installed — not yet

**1.0.** Five doors to one verdict. The fifth is a page that checks a container
in the browser, installing nothing and sending the container nowhere.

## Input safety

**Case.** `tests/fixtures/z4-path-traversal.zip` names a member
`../escaped.txt`:

```
  error  Z4  A member name would escape the extraction directory
         at z4-path-traversal.zip!/../escaped.txt
```

Nothing is extracted to disk at any point, so there is nowhere for that name to
escape to. And `tests/fixtures/z5b-declared-bomb.zip` holds a member whose
header says it expands 1028 times: it is refused before it is decompressed, as
`Z5`, and the file the metadata names is reported as declined rather than as
missing, as `F1`.

**Now.**

- read budgets, per member and per archive — done; the table in
  [SECURITY.md](../SECURITY.md) sets each kind of hostile archive beside what
  meets it and the test that holds it, and the archive reader's limits that
  span a whole read -- containers opened, bytes inflated, entries listed,
  metadata held -- are in `packages/vdi2770/src/vdi2770/zipread.py`
- a security fix ships with an advisory — done; the advisories are listed in
  [SECURITY.md](../SECURITY.md)
- tests verified against their own mutations — done;
  `python tools/mutation_table.py --run`
- declared encodings read without loss — not yet

**1.0.** Metadata may declare an encoding in its XML declaration. The condition
is a test that reads metadata in each encoding the declaration allows and quotes
it back unchanged.

## Upstream

**Case.** The sample corpus is copied from the reference repository at a single
commit, which `corpus/MANIFEST.json` names, and is not edited. The oracle
workflow runs the reference implementation at a pinned commit as well; its
schedule looks for rot in everything around that pin, not for changes in the
reference.

**Now.**

- upstream corpus pinned by commit — done
- checked weekly for change — not yet

**1.0.** A weekly check that says when the reference moves. The reference has
not moved since this project pinned it -- its default branch is at the pinned
commit -- so moving the pin is not something this project can do on its own;
the check is what will say when there is a move to make.

The same six, as a table: [docs/capabilities.md](capabilities.md).
