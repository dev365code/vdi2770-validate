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


def test_every_named_fix_source_is_used_in_the_page_lists():
    import ast
    import inspect
    import sys

    from vdi2770.validate.rules import container, files, metadata, pdf, schema

    sys.path.insert(0, str(ROOT / "tools"))
    import rules_doc

    generator = ast.parse(inspect.getsource(rules_doc))
    listed = {(node.value.id, node.attr) for node in ast.walk(generator)
              if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)}
    body = PAGE.read_text(encoding="utf-8")
    expected = set()
    for module in (container, files, metadata, pdf, schema):
        tree = ast.parse(inspect.getsource(module))
        module_name = module.__name__.rsplit(".", 1)[-1]
        named = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        named |= {target.id for node in tree.body if isinstance(node, ast.Assign)
                  for target in node.targets if isinstance(target, ast.Name)}
        if module is files:
            named |= {"ONE_NAME", "layout_remedy", "method_remedy"}
        expressions = [node.value for node in ast.walk(tree)
                       if isinstance(node, ast.keyword) and node.arg == "fix"
                       or isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "fix" for t in node.targets)]
        for expression in expressions:
            for node in ast.walk(expression):
                if isinstance(node, ast.Name) and node.id in named:
                    expected.add((module_name, node.id))
                    remedy = getattr(module, node.id)
                    if isinstance(remedy, str):
                        assert remedy in body, (module_name, node.id)
    assert expected <= listed, sorted(expected - listed)
    for remedy in container.REMEDY_FOR_DEFECT.values():
        assert remedy in body


def test_the_page_puts_each_reason_beside_its_remedy():
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    import rules_doc

    body = PAGE.read_text(encoding="utf-8")
    for rid, rows in rules_doc.reason_rows().items():
        section = body.split(f"### `{rid}` — ", 1)[1].split("\n### ", 1)[0]
        for when, remedy in rows:
            assert f"- When the finding says {when}: {remedy}" in section
    assert "<method>" in body and "<member>" in body


def test_the_namespace_and_english_advice_stay_with_their_findings():
    import sys

    from vdi2770.validate.rules import metadata

    sys.path.insert(0, str(ROOT / "tools"))
    import rules_doc

    rows = rules_doc.reason_rows()
    assert metadata.NAMESPACE_DECLARATION in [fix for _, fix in rows["M1"]]
    assert metadata.PUBLISHED_ENGLISH in [fix for _, fix in rows["M4"]]
    assert "M3" not in rows


def test_the_file_reasons_quote_the_messages_the_rule_prints():
    import ast
    import inspect
    import sys

    from vdi2770.validate.rules import files

    sys.path.insert(0, str(ROOT / "tools"))
    import rules_doc

    messages = {node.value.value for node in ast.walk(ast.parse(inspect.getsource(files)))
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and any(isinstance(t, ast.Name) and t.id == "message" for t in node.targets)}
    headings = [when for when, _ in rules_doc.reason_rows()["F1"]]
    assert all(any(message in when for when in headings) for message in messages)


def test_template_slots_are_visible_in_markdown():
    body = PAGE.read_text(encoding="utf-8")
    assert "It is compressed with `<method>`, and this tool" in body
    assert "The member '`<member>`' stores this name" in body
