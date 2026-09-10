"""The generated page shows, per layer, what its rules stand on.

`obligation` says where a requirement comes from and the page already lists how
many rules hold each value. What it did not show is how those fall across the
layers, and that is the shape of the answer somebody actually wants: the four
`container` rules are ZIP and XML mechanics, the `files` layer is entirely the
reference implementation's, and every `pdf` rule but one is our own judgement.

Read from the catalogue rather than from prose. A table of counts written by
hand is a table that is right on the day it is written.
"""
import collections

from vdi2770_validate.catalog import rules

from conftest import ROOT

PAGE = ROOT / "docs" / "rules.md"


def counted():
    tab = collections.Counter((r.layer, r.obligation.value) for r in rules().values())
    layers = sorted({layer for layer, _ in tab})
    kinds = sorted({kind for _, kind in tab})
    return tab, layers, kinds


def test_the_page_has_a_row_for_every_layer():
    _, layers, _ = counted()
    body = PAGE.read_text(encoding="utf-8")
    start = body.index("| layer |")
    where = body[start:body.index("\n\n", start)]
    for layer in layers:
        assert f"| `{layer}` |" in where, (
            f"the page's provenance table has no row for the {layer} layer")


def test_every_number_in_the_table_is_the_number_in_the_data():
    tab, layers, kinds = counted()
    body = PAGE.read_text(encoding="utf-8")
    start = body.index("| layer |")
    lines = body[start:body.index("\n\n", start)].splitlines()
    header = [c.strip(" `") for c in lines[0].strip("|").split("|")]
    assert header[0] == "layer", header
    # The totals are cells too. The first version skipped the last row and the
    # last column as "sums of the ones above", so a generator that miscounted
    # them, regenerated, read as a page that matched its catalogue.
    for line in lines[2:]:
        cells = [c.strip(" `*") for c in line.strip("|").split("|")]
        layer = cells[0]
        for kind, said in zip(header[1:], cells[1:]):
            if layer.lower() == "total":
                want = (sum(tab.values()) if kind == "total"
                        else sum(n for (_, k), n in tab.items() if k == kind))
            elif kind == "total":
                want = sum(n for (lay, _), n in tab.items() if lay == layer)
            else:
                want = tab[(layer, kind)]
            assert int(said) == want, (
                f"the page says {layer}/{kind} is {said}; the catalogue has {want}")


def test_the_totals_are_the_sum_of_the_rules():
    tab, layers, kinds = counted()
    assert sum(tab.values()) == len(rules()), "a rule is missing from the count"
    body = PAGE.read_text(encoding="utf-8")
    start = body.index("| layer |")
    lines = body[start:body.index("\n\n", start)].splitlines()
    last = [c.strip(" `*") for c in lines[-1].strip("|").split("|")]
    assert last[0].strip("*").lower() == "total", last
    assert int(last[-1]) == len(rules()), (
        f"the table totals {last[-1]} and the catalogue holds {len(rules())}")
