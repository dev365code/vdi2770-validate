# Contributing

## The Developer Certificate of Origin

Every commit carries a `Signed-off-by` line — `git commit -s`. That is a
[certificate of origin](https://developercertificate.org/), not a transfer of
rights; you keep the copyright in what you write.

## Before you open a pull request

```bash
python -m pip install -e packages/vdi2770   # the reader, from this tree
python -m pip install -e ".[dev]"
make check
```

The reader first, and from this tree. Skipping that line resolves `vdi2770` from
PyPI, so the gate you run is the published reader rather than the one in the
commit you are changing — which is exactly the split that shipped a release whose
own fix never reached the user. CI installs it in that order for the same reason;
a test compares the two recipes.

`make check` also builds distributions, which needs `pip install build`.

`make mutations` is separate and slower. It takes every claim this project
makes about a gate, breaks the thing that gate protects, and checks the gate
notices — including one row that must *survive*, because a harness that
reports red for a change that does not matter is reporting red for
everything. Run it when you add or change a gate. `tools/mutation_table.py`
with no arguments lists the table.

`make standalone` runs every test file on its own. A suite is a shared
process, so a file can pass because an earlier one imported something —
`tests/test_offline.py` did exactly that for weeks. Run it when you add a
module-level import to a test.

`make check` is the whole gate. It is ten targets, and one of them —
`fixtures` — is a build step rather than a gate: it regenerates the
fixtures the tests need, and can only fail if the generator crashes. The
other nine judge something: `lint`,
`test`, `corpus` (the vendored corpus is unchanged), `coverage-check` (every rule
still fires somewhere), `rules-doc` (the generated rule reference matches
the catalogue), `oracle-half` (our half of the recorded differential sweep is
what this tool currently reports), `sdist-runs-its-own-tests` (each package's source
distribution can run its own suite — three times a gate reached outside its own
distribution and only this caught it), and `wheel-installs-and-runs`
(the wheels are built, looked inside, installed and run — nobody installs a
source distribution), and `reader-api-matches-its-version`
(the reader's public surface is recorded against the version that published
it — changing one without the other is how a release ships a pin nobody can
satisfy). CI runs exactly those commands — a test
asserts that, because "the same command" is not the same thing as "the same
environment".

## Three rules of the road

Each exists because ignoring it would break something specific, and the
changelog records what that was.

1. **A new rule is a row in `rules.json` plus a function.** The row carries where
   the requirement comes from, and a remedy sentence saying what the user should
   *do*. A finding that only restates the problem is half a finding.

2. **A new rule needs a fixture pair.** One container that violates it, one that
   does not, differing in as little as possible — add the violating one to
   `tools/make_fixtures.py`. A rule that has never been seen to fire has never
   been tested, and `make check` will say so.

3. **Rules may not import a parser.** `tests/test_layering.py` fails if a module
   under `rules/` imports `zipfile` or an XML library. (Rules do import the
   readers' reserved file names — that exemption is written into the test.)
   Rules read the model; how the document was spelled is not their business.

## Where the requirement came from matters

`rules.json` gives every rule an `obligation`, which says where its requirement
comes from: `schema` (the XSD VDI publishes free), `table` (a freely published
table), `container` (mechanics of ZIP and XML that anyone can observe, true
without VDI 2770), `reference` (observed in the MIT reference implementation and
**not** verified against the guideline, which is paywalled), or `ours` — and
`ours` must carry a `whyOurs` sentence.

`reference` and `ours` are the two largest groups, and both are weaker claims
than they look. If you add a rule under either, the burden is to say what you
actually observed, not what the standard requires.

**The VDI 2770 guideline text is sold by DIN Media and is not used here.** Do not
quote or paraphrase it, even from memory, and do not copy message text from other
implementations into a remedy — a test checks for that. See
[docs/licensing.md](docs/licensing.md).

## Reporting something without writing code

An issue with a container that is judged wrongly — in either direction — is one
of the most useful things you can send. Strip anything confidential first; a
minimal archive that still reproduces is ideal.
