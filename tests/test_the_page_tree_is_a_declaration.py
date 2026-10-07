"""ISO 32000-1's Count is a declaration, not a rendering or a leaf walk."""
import json
import zipfile

import pytest
from vdi2770_validate.model import About, Obligation, Severity
from vdi2770_validate.runner import check_file

import vdi2770
from conftest import FIXTURES
from vdi2770_validate import report as rendering

CASES = json.loads((FIXTURES / "pages/MANIFEST.json").read_text(encoding="utf-8"))


def pdf(name):
    with zipfile.ZipFile(FIXTURES / "pages" / (name + ".zip")) as archive:
        return archive.read("B.pdf")


@pytest.mark.parametrize("name", CASES)
def test_the_model_keeps_the_original_number_of_pages(name):
    with zipfile.ZipFile(FIXTURES / "pages" / (name + ".zip")) as archive:
        data = archive.read("VDI2770_Metadata.xml")
    document = vdi2770.build_document(vdi2770.parse_xml(data), vdi2770.Location(member="VDI2770_Metadata.xml"))
    assert document.versions[0].number_of_pages == CASES[name]["number"]
    assert document.versions[0].src.line and document.versions[0].src.column is not None


@pytest.mark.parametrize("name", CASES)
def test_the_reader_follows_the_declared_page_tree(name):
    facts = vdi2770.read_pdf(pdf(name), page_count=True)
    expected = CASES[name]["page_count"]
    if isinstance(expected, int):
        assert facts.page_count == expected
        assert facts.page_count_why is None
    elif expected is None:
        if "is_pdf" in CASES[name]:
            assert facts.is_pdf is None and facts.page_count is None and facts.page_count_why is None
        else:
            assert facts.encrypted and facts.page_count is None
    else:
        assert facts.page_count is None
        assert expected in facts.page_count_why
    assert facts.is_pdf is CASES[name].get("is_pdf", True)
    assert facts.pdfa_claim == "2b"


def test_an_unrequested_page_count_costs_nothing():
    facts = vdi2770.read_pdf(pdf("different"))
    assert facts.page_count is None and facts.page_count_why is None


def test_a_real_number_is_not_read_as_an_integer():
    body = pdf("real-count")
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None and "integer" in facts.page_count_why


def test_a_large_pdf_integer_is_refused_before_int_conversion():
    body = pdf("large-count")
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None and "range" in facts.page_count_why


def test_the_page_count_does_not_follow_an_attachment_tree():
    body = pdf("equal")
    # A second catalog/page tree outside Root cannot choose the result.
    body += b"\n200 0 obj << /Type /Catalog /Pages 201 0 R >> endobj\n201 0 obj << /Count 99 >> endobj\n"
    assert vdi2770.read_pdf(body, page_count=True).page_count == 7


def test_page_reading_windows_are_bounded_and_the_file_search_is_linear(monkeypatch):
    from vdi2770 import _pdfpages, pdfread

    real = _pdfpages.PageReader.window
    sampled = []

    def counted(self, at):
        out = real(self, at)
        sampled.append(len(out))
        return out

    class Charged(bytes):
        searched = 0

        def rfind(self, sub, start=0, end=None):
            end = len(self) if end is None else end
            self.searched += end - start
            return super().rfind(sub, start, end)

    monkeypatch.setattr(_pdfpages.PageReader, "window", counted)
    costs = []
    for size in (100_000, 400_000, 1_600_000):
        sampled.clear()
        body = Charged(pdf("equal") + b" " * size)
        facts = vdi2770.read_pdf(body, page_count=True)
        assert facts.page_count == 7
        assert sampled and max(sampled) <= pdfread.MAX_PAGE_OBJECT_WINDOW
        assert len(sampled) <= pdfread.MAX_TRAILERS + pdfread.MAX_PAGE_OBJECTS
        assert body.searched <= 4 * len(body)
        costs.append((size, len(sampled), sum(sampled), body.searched))
    assert len({c[1] for c in costs}) == 1
    assert max(c[2] for c in costs) <= min(c[2] for c in costs) + pdfread.MAX_PAGE_OBJECT_WINDOW
    print("page-cost-coefficients", costs)


def test_object_resolution_stops_at_its_cap():
    import sys

    from conftest import ROOT
    from vdi2770 import pdfread

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from page_fixtures import append_revision, objects
    finally:
        sys.path.pop(0)
    values = objects(7)
    values[2] = b"<< /Type /Pages /Count 110 0 R >>"
    for n in range(110, 140):
        values[n] = f"{n + 1} 0 R".encode("ascii")
    values[140] = b"7"
    facts = vdi2770.read_pdf(append_revision(b"%PDF-1.7\n", values), page_count=True)
    assert facts.page_count is None
    assert f"object limit {pdfread.MAX_PAGE_OBJECTS}" in facts.page_count_why


def test_xref_resolution_stops_at_its_section_cap(monkeypatch):

    from conftest import ROOT
    from vdi2770 import pdfread

    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from page_fixtures import append_revision

    body = pdf("equal")
    import re
    for _ in range(pdfread.MAX_TRAILERS):
        previous = int(re.findall(rb"startxref\n([0-9]+)", body)[-1])
        body = append_revision(body, {200: b"0"}, root=None, prev=previous)
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None
    assert "xref section limit" in facts.page_count_why


@pytest.mark.parametrize("limit", ["file", "read"])
def test_page_reading_spends_the_shared_inflation_before_claim_search(monkeypatch, limit):
    from vdi2770 import pdfread

    body = pdf("compressed-claim")
    real = pdfread.zlib.decompressobj
    expanded = []

    class Counted:
        def __init__(self):
            self.inner = real()

        def decompress(self, body, cap):
            out = self.inner.decompress(body, cap)
            expanded.append(len(out))
            return out

        @property
        def eof(self):
            return self.inner.eof

    monkeypatch.setattr(pdfread.zlib, "decompressobj", Counted)
    if limit == "file":
        monkeypatch.setattr(pdfread, "MAX_INFLATED_TOTAL", 1000)
    read = pdfread.reader(1000 if limit == "read" else pdfread.MAX_INFLATED_PER_READ)
    facts, cut = read(body, page_count=True)
    assert facts.page_count == 7, "claim search must not spend the allowance first"
    assert sum(expanded) <= 1000
    assert facts.pdfa_claim is None
    assert cut == limit
    print("shared-page-inflation", limit, expanded)


def test_a_latest_null_root_is_not_replaced_by_an_older_root(monkeypatch):
    import re

    from conftest import ROOT

    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from page_fixtures import append_revision

    body = pdf("equal")
    previous = int(re.findall(rb"startxref\n([0-9]+)", body)[-1])
    body = append_revision(body, {200: b"0"}, root=None, prev=previous, extra=b" /Root null")
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None and "Root" in facts.page_count_why


QUIET = {"equal", "incremental-equal", "object-stream", "png-xref", "encrypted",
         "linearized", "plus", "space", "invalid-zero", "invalid-negative",
         "invalid-underscore", "invalid-unicode", "compressed-claim", "multiple-pdfs", "unconfirmed",
         "padded-pdf-count", "hybrid-hidden", "hybrid-conflict", "hybrid-pages-in-stream",
         "hybrid-in-prev"}


@pytest.mark.parametrize("name", CASES)
def test_p6_compares_each_version_at_the_metadata_number(name):
    path = FIXTURES / "pages" / (name + ".zip")
    report = check_file(str(path))
    findings = [f for f in report.findings if f.rule.id == "P6"]
    expected = 0 if name in QUIET else 2 if name == "two-versions" else 1
    assert len(findings) == expected, [(f.rule.id, f.detail) for f in report.findings]
    with zipfile.ZipFile(path) as archive:
        lines = archive.read("VDI2770_Metadata.xml").decode("utf-8").splitlines()
    for f in findings:
        assert f.severity is Severity.WARNING and f.rule.obligation is Obligation.OURS
        assert f.where.member == "VDI2770_Metadata.xml" and f.where.subject == "B.pdf"
        assert f.where.column is not None and "NumberOfPages" in lines[f.where.line - 1]
        assert "B.pdf" in f.detail
        if isinstance(CASES[name]["page_count"], str):
            assert f.about is About.TOOL
            assert "could not be read" in f.message and "could not be read:" in f.detail
            assert json.loads(rendering.as_json(report))["read"]["complete"] is False
        else:
            assert f.about is About.CONTAINER
            assert f.message == "The metadata and the PDF's page tree declare different page counts"
            assert "NumberOfPages" in f.remedy and "page tree" in f.remedy
            assert "declares" in f.detail and "metadata says" in f.detail
            if name == "zero":
                assert "declares no pages" in f.detail
            if name == "false-count":
                assert "declares 5" in f.detail and "has 5" not in f.detail
            if name == "long-number":
                assert len(f.detail) < 220 and "4301 digits" in f.detail
    assert "X5" not in {f.rule.id for f in report.findings}


def test_page_inflation_refusal_is_reported_even_when_a_raw_pdfa_claim_exists(monkeypatch):
    from vdi2770 import pdfread

    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 0)
    report = check_file(str(FIXTURES / "pages/object-stream.zip"))
    pages = [f for f in report.findings if f.rule.id == "P6"]
    assert len(pages) == 1 and pages[0].about is About.TOOL
    assert "read inflation budget" in pages[0].detail
    assert {"Z5", "P4"} <= {f.rule.id for f in report.findings}
    assert json.loads(rendering.as_json(report))["read"]["complete"] is False
    z5 = next(f for f in report.findings if f.rule.id == "Z5")
    assert "page tree" in z5.detail and "Every other check" not in z5.remedy


def test_changing_a_reader_refusal_sentence_does_not_remove_z5(tmp_path):
    import os
    import shutil
    import subprocess
    import sys

    from conftest import ROOT

    source = ROOT / "packages/vdi2770/src/vdi2770"
    copied = tmp_path / "vdi2770"
    shutil.copytree(source, copied, ignore=shutil.ignore_patterns("__pycache__"))
    old, new = "read inflation budget exhausted", "read-wide expansion allowance exhausted"
    changed = 0
    # Change only the reader's sentence. Consumers must use its shared vocabulary.
    for path in copied.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        changed += text.count(old)
        path.write_text(text.replace(old, new), encoding="utf-8")
    assert changed == 1, "the reader's refusal sentence is not defined once"
    program = """
import json, sys
from vdi2770 import pdfread
from vdi2770.validate.runner import check_file
from vdi2770.validate.report import as_json
pdfread.MAX_INFLATED_PER_READ = 0
report = check_file(sys.argv[1])
print(as_json(report))
"""
    done = subprocess.run([sys.executable, "-B", "-c", program,
                           str(FIXTURES / "pages/object-stream.zip")],
                          cwd=tmp_path, env=dict(os.environ, PYTHONPATH=str(tmp_path)),
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    rendered = json.loads(done.stdout)
    findings = rendered["findings"]
    assert {"Z5", "P4", "P6"} <= {f["rule"] for f in findings}
    assert new in next(f["detail"] for f in findings if f["rule"] == "P6")
    assert rendered["read"]["complete"] is False


def test_excel_template_page_declarations_produce_seven_true_warnings():
    from conftest import CORPUS

    report = check_file(str(CORPUS / "container/vdi2770_excel.zip"))
    pages = [f for f in report.findings if f.rule.id == "P6"]
    assert len(pages) == 7
    assert all(f.about is About.CONTAINER and "declares 1" in f.detail for f in pages)
    assert report.count(Severity.ERROR) == 0


def test_a_pdf_without_a_comparison_does_not_read_its_page_tree(monkeypatch):
    from conftest import CLEAN_DOCUMENT
    from vdi2770 import _pdfpages

    def forbidden(*args):
        pytest.fail("the page tree was read without a valid comparison")

    monkeypatch.setattr(_pdfpages, "declared_count", forbidden)
    for path in [CLEAN_DOCUMENT, FIXTURES / "pages/multiple-pdfs.zip",
                 FIXTURES / "pages/invalid-unicode.zip", FIXTURES / "pages/encrypted.zip",
                 FIXTURES / "pages/unconfirmed.zip"]:
        report = check_file(str(path))
        assert "P6" not in {f.rule.id for f in report.findings}


def test_overlapping_xref_indices_are_declined_before_inflation(monkeypatch):
    from vdi2770 import pdfread

    body = pdf("overlapping-index")

    def forbidden():
        pytest.fail("a malformed Index spent the inflation allowance")

    monkeypatch.setattr(pdfread.zlib, "decompressobj", forbidden)
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None and "Index" in facts.page_count_why


def test_published_silent_paths_are_the_generated_verdicts():
    import subprocess
    import sys

    from conftest import ROOT

    done = subprocess.run([sys.executable, "tools/silent_paths.py"], cwd=ROOT,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
