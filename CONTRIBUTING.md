# Contributing

## The Developer Certificate of Origin

Every commit carries a `Signed-off-by` line — `git commit -s`. That is a
[certificate of origin](https://developercertificate.org/), not a transfer of
rights; you keep the copyright in what you write. Pull requests are checked for
it automatically.

## Before you open a pull request

```bash
python -m pip install -e ".[dev]"
make check
```

`make check` is the whole gate: lint, tests, the corpus is unchanged, and every
rule still fires. CI runs exactly those commands — a test asserts that, because
"the same command" is not the same thing as "the same environment".

## Three rules of the road

Each exists because ignoring it would break something specific.

1. **A new rule is a row in `rules.json` plus a function.** The row carries where
   the requirement comes from, and a remedy sentence saying what the user should
   *do*. A finding that only restates the problem is half a finding.

2. **A new rule needs a fixture pair.** One container that violates it, one that
   does not, differing in as little as possible — add the violating one to
   `tools/make_fixtures.py`. A rule that has never been seen to fire has never
   been tested, and `make check` will say so.

3. **Rules may not import a parser.** `tests/test_layering.py` walks the import
   graph and fails if a module under `rules/` reaches `zipfile` or an XML
   library. Rules read the model; how the document was spelled is not their
   business.

## Where the requirement came from matters

`rules.json` gives every rule an `obligation`: `schema` (the XSD VDI publishes
free), `table` (a freely published table), `container` (mechanics anyone can
observe), or `ours` — and `ours` must carry a `whyOurs` sentence.

**The VDI 2770 guideline text is sold by DIN Media and is not used here.** Do not
quote or paraphrase it, even from memory, and do not copy message text from other
implementations into a remedy — a test checks for that. See
[docs/licensing.md](docs/licensing.md).

## Reporting something without writing code

An issue with a container that is judged wrongly — in either direction — is one
of the most useful things you can send. Strip anything confidential first; a
minimal archive that still reproduces is ideal.
