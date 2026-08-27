"""A report has to let a reader tell apart two names that print the same.

That is the whole job of `names.escaped`, and it was pinned by nothing: replacing
its body with `return name` left the entire suite green. The test that was meant
to hold it compared Python tuples, which differ in code points — an assertion
satisfied by a difference the reader cannot see.

Every fixture here is built from `unicodedata.normalize` or from explicit `\\u`
escapes, never from a literal typed into this file. Two spellings of one name
typed as literals are one editor, one paste, or one `git` filter away from being
the same string, and then these assertions pass while testing nothing.
"""
import re
import unicodedata

from vdi2770_validate.names import escaped


def shown(text: str) -> str:
    """Roughly what a terminal draws: composed, with what takes no width removed.

    Not a claim about terminals. It is the weaker, checkable claim that two
    strings compose to the same sequence of spacing characters — which is what
    canonical equivalence means, plus Unicode's own statement that default
    ignorable code points draw nothing.

    It is wrong in three known ways, all of which make it call things *alike*
    more readily than a font would: a ZWJ emoji sequence strips to its parts, a
    presentation selector strips to nothing, and a visible combining mark is
    dropped along with the invisible ones. Every assertion below demands that two
    renderings be *different*, so a predicate biased towards "alike" can only
    make this stricter. It says nothing about homoglyphs across scripts — Cyrillic
    А against Latin A — which it calls different, and which are not this
    function's problem: the names it is given are canonically equivalent.
    """
    composed = unicodedata.normalize("NFC", text)
    return "".join(c for c in composed
                   if c.isprintable()
                   and unicodedata.combining(c) == 0
                   and unicodedata.category(c) not in ("Mn", "Me", "Cf"))


def spellings_of(name):
    """The canonically equivalent ways to write `name`, as the archive might."""
    return {unicodedata.normalize(form, name) for form in ("NFC", "NFD")}


# Each row is a different mechanism by which two names come to print alike, and
# every one is written in code points. A Korean name typed as a literal reached
# this file *partially* decomposed — first syllable in jamo, second composed —
# through nothing more than a shell heredoc, and the assertions below would have
# been about a string nobody chose.
ONE_NAME_MANY_SPELLINGS = [
    ("Hangul, as macOS writes it against as Windows does", "\ub3c4\uba74.pdf"),
    ("Hangul, a longer stem", "\uc124\uba85\uc11c_2024.pdf"),
    ("Latin with a diaeresis", "Pr\u00fcfung.pdf"),
    ("Vietnamese, stacked marks", "B\u1ea3n_v\u1ebd.pdf"),
    ("Japanese with a handakuten", "\u30ac\u30a4\u30c9.pdf"),
]

# Canonical singletons: one character, one other character, one glyph. `NFD` does
# not produce these — both spellings normalise to the same thing in both forms —
# so the pair is named outright.
SINGLETONS = [
    ("angstrom sign", "\u212bngstrom.pdf", "\u00c5ngstrom.pdf"),
    ("ohm sign", "R_10\u2126.pdf", "R_10\u03a9.pdf"),
    ("kelvin sign", "\u212aelvin.pdf", "Kelvin.pdf"),
]


def test_every_spelling_of_one_name_gets_its_own_rendering():
    """The one that dies if `escaped` becomes the identity function.

    `도면.pdf` in NFC and in NFD both rendered as `도면.pdf`, in the same finding,
    on the two lines whose only purpose is to be told apart. Conjoining jamo are
    `Lo`, printable and combining class 0, so a rule that escapes by combining
    class never saw them — and macOS stores filenames decomposed, which makes
    this the ordinary case for a Korean supplier rather than an exotic one.
    """
    for label, name in ONE_NAME_MANY_SPELLINGS:
        forms = sorted(spellings_of(name))
        assert len(forms) == 2, f"{label}: only one spelling — {forms}"
        a, b = (escaped(f) for f in forms)
        assert shown(a) != shown(b), f"{label}: both render as {shown(a)!r}"

    for label, one, other in SINGLETONS:
        assert one != other, f"{label}: the two spellings arrived as one string"
        assert unicodedata.normalize("NFC", one) == other, f"{label}: not a singleton pair"
        assert shown(escaped(one)) != shown(escaped(other)), (
            f"{label}: both render as {shown(escaped(one))!r}")


def test_a_rendering_can_be_read_back_as_the_name_it_renders():
    """No two names may render the same, which needs the escapes not to be forgeable.

    A member named with a literal backslash — `A\\u030angstrom.pdf`, seven ASCII
    characters where the escape would be — rendered exactly like `A` followed by
    a combining ring above. Both lines said `A\\u030angstrom.pdf` and nothing on
    the page said which one it was. `\\\\` for a backslash is what closes that,
    and reading the escapes back is how this says so.
    """
    def read_back(text):
        def one(m):
            digits = m.group(1) or m.group(2)
            return chr(int(digits, 16)) if digits else "\\"

        return re.sub(r"\\U([0-9a-f]{8})|\\u([0-9a-f]{4})|\\\\", one, text)

    names = [n for _, n in ONE_NAME_MANY_SPELLINGS]
    names += [n for _, one, other in SINGLETONS for n in (one, other)]
    names += ["A\\u030angstrom.pdf", "back\\\\slash.pdf", "ok_\U0001f600.pdf",
              "\U0001f3f4\U000e0067\U000e0062\U000e0073.pdf", "plain.pdf"]
    for name in names:
        for form in spellings_of(name) | {name}:
            assert read_back(escaped(form)) == form, (
                f"{form!r} rendered as {escaped(form)!r}, which reads back as "
                f"{read_back(escaped(form))!r}")


def test_a_name_with_nothing_wrong_with_it_is_printed_as_itself():
    """The guard against the other failure, which this function had too.

    Escaping by combining class took Thai tone marks, Devanagari viramas and
    Arabic harakat — visible letters, every one — and turned them into hex. A
    supplier whose delivery has one ambiguous name read a report in which their
    other, blameless filenames had been mangled by the tool complaining about
    encoding.
    """
    ordinary = [
        ("Thai", "คู่มือ.pdf"),
        ("Devanagari", "परीक्षण.pdf"),
        ("Arabic with harakat", "تَقْرِير.pdf"),
        ("Khmer", "របាយការណ៍.pdf"),
        ("Lao", "ບົດລາຍງານ.pdf"),
        ("Korean", "제품_도면.pdf"),
        ("Japanese", "検査報告書.pdf"),
        ("Chinese", "检验报告.pdf"),
        ("Cyrillic", "Отчёт.pdf"),
        ("Vietnamese", "Báo_cáo.pdf"),
        ("ASCII", "drawing_A-1.pdf"),
    ]
    for label, name in ordinary:
        assert unicodedata.normalize("NFC", name) == name, f"{label}: fixture is not NFC"
        assert escaped(name) == name, f"{label}: {name!r} was printed as {escaped(name)!r}"


def test_a_character_that_draws_nothing_is_spelled_out():
    """`escaped` promises to spell out anything invisible and did not.

    A variation selector is `Mn`, printable, combining class 0 — so it went
    through untouched and rendered as nothing at all, which is the one thing this
    function exists to refuse.
    """
    for hidden in ("️", "\U000e0101", "‍", "ㅤ"):
        name = f"report_{hidden}A.pdf"
        assert hidden not in escaped(name), (
            f"U+{ord(hidden):04X} survived into the rendering, where it draws nothing")


def test_the_report_tells_two_look_alike_members_apart():
    """End to end, because the helper is not what a reader sees.

    A unit test on `escaped` can pass while the finding still prints two
    identical lines, because the detail interpolates other things around it.
    This asserts on the sentence.

    Not on the location line, which carries the member's name as the archive
    spells it and is meant to: running every `at` through `escaped` would spell
    out every filename in every report from a delivery written on a Mac, where
    nothing is ambiguous at all. What tells the two apart is the detail, and it
    does.
    """
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT
    from vdi2770_validate.runner import check_bytes

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    forms = sorted(spellings_of("도면.pdf"))
    assert len(forms) == 2
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            if name == "B.pdf":
                for form in forms:
                    z.writestr(form, src.read(name))
            else:
                z.writestr(name, src.read(name))
    report = check_bytes(buf.getvalue(), "twins.zip")
    said = [f.detail for f in report.findings if f.rule.id == "Z10"]
    assert len(said) == 2, said
    assert shown(said[0]) != shown(said[1]), (
        f"both findings print as {shown(said[0])!r}")


def _container_declaring_class_name(german: str):
    """The clean document container with its German class name replaced."""
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode("utf-8")
    assert meta.count("Technische Spezifikation") == 1, "the fixture no longer names the class"
    meta = meta.replace("Technische Spezifikation", german, 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            z.writestr(name, meta.encode("utf-8") if name == "VDI2770_Metadata.xml"
                       else src.read(name))
    return buf.getvalue()


def test_a_class_name_that_differs_where_nothing_shows_is_spelled_out():
    """`M3` printed two strings that draw the same and said they differ.

    One Cyrillic `е` (U+0435) among the Latin ones and the finding read

        'Tеchnische Spezifikation' for class 02-01; published name is
        'Technische Spezifikation'

    which asks a supplier to find a difference they cannot see. This is the
    failure the Hangul repair was about, arriving through a different door:
    there the two spellings were canonically equivalent and `escaped` could tell
    them apart on its own, and here they are not — both strings are their own
    NFC and every character is printable and non-combining, so no rule that
    looks at one string at a time can see anything wrong.

    What this call site has that `escaped` does not is *both* strings. The
    difference is a position, and a position can be spelled.
    """
    from vdi2770_validate.runner import check_bytes

    latin = "Technische Spezifikation"
    # Built from the code point, never typed: a Cyrillic letter among Latin ones
    # is exactly the character an editor, a paste, or a shell heredoc silently
    # turns back into its look-alike, and then this asserts nothing.
    cyrillic = latin[:1] + "\u0435" + latin[2:]
    assert len(latin) == len(cyrillic), "the fixture changed the length"
    apart = [i for i, (a, b) in enumerate(zip(latin, cyrillic)) if a != b]
    assert apart == [1], f"the fixture no longer differs in exactly one place: {apart}"

    report = check_bytes(_container_declaring_class_name(cyrillic), "homoglyph.zip")
    m3 = [f for f in report.findings if f.rule.id == "M3"]
    assert m3, [f.rule.id for f in report.findings]

    quoted = re.findall(r"'([^']*)'", m3[0].detail or "")
    assert len(quoted) >= 2, m3[0].detail
    observed, published = quoted[0], quoted[1]

    # The property, stated the only way it can be checked. What a terminal draws
    # is not knowable from code points -- `shown()` above says so, and comparing
    # them would call a Cyrillic `е` different from a Latin one, which on the
    # page it is not. What *is* checkable: the two lines differ **only** inside
    # escapes. Strip the escapes and what is left is identical, so every
    # character a reader can see is the same and every difference is spelled.
    def without_escapes(text):
        return re.sub(r"\\u[0-9a-f]{4}|\\U[0-9a-f]{8}", "", text)

    assert "\\u" in observed and "\\u" in published, (
        f"neither string spells anything out: {m3[0].detail}")
    assert without_escapes(observed) == without_escapes(published), (
        f"the two differ somewhere other than in the escapes: {m3[0].detail}")
    assert observed != published, m3[0].detail


def test_a_class_name_that_is_plainly_wrong_is_left_readable():
    """The other half. A name that differs visibly needs no code points, and
    spelling one out would bury the difference the reader can already see."""
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_container_declaring_class_name("Betriebsanleitung"),
                         "plain.zip")
    m3 = [f for f in report.findings if f.rule.id == "M3"]
    assert m3, [f.rule.id for f in report.findings]
    assert "\\u" not in (m3[0].detail or ""), (
        f"a plainly different name was printed as code points: {m3[0].detail}")


def test_whitespace_at_the_edge_of_a_name_is_spelled_out():
    """A trailing space draws nothing, and `escaped` printed it as itself.

    So a report could carry

        F1  'B.pdf' is declared but not in the archive
        F2  at space.zip!/B.pdf

    two lines that read as a contradiction, about two names that differ by a
    character the page cannot show. It is the promise in this function's first
    line — *a name a reader can tell apart from anything that prints like it* —
    and a space at the end of a name is the cheapest way to break it.

    In the middle of a name a space is ordinary and visible, and spelling it
    there would make every `my report.pdf` unreadable. The rule is about the
    edges: of the name, and of each path segment, which is where a space has
    nothing beside it to be seen against.
    """
    for name, why in ((" B.pdf", "leading"),
                      ("B.pdf ", "trailing"),
                      ("docs /B.pdf", "at the end of a segment"),
                      ("docs/ B.pdf", "at the start of a segment"),
                      ("B.pdf\t", "a tab")):
        rendered = escaped(name)
        assert "\\u" in rendered, f"{why}: {name!r} rendered as {rendered!r}"
        assert rendered != name, f"{why}: {name!r} came back unchanged"

    for ordinary in ("my report.pdf", "docs/my report.pdf", "B.pdf"):
        assert escaped(ordinary) == ordinary, (
            f"a space where it can be seen was spelled out: {escaped(ordinary)!r}")


def test_the_archives_own_spelling_still_shows_whitespace_at_an_edge():
    """`as_written` makes the same promise one function up, for the case where
    the difference between two names is not a spelling difference. A space at
    the end of a name is invisible there too."""
    from vdi2770_validate.names import as_written

    assert as_written("B.pdf ") != "B.pdf ", "a trailing space came back unchanged"
    assert as_written("my report.pdf") == "my report.pdf"


def test_a_member_name_cannot_forge_lines_in_the_report():
    """A supplier chose what a CI log appeared to say about another container.

    `Location.__str__` interpolates the member name, and the text report prints
    `at {where}`. A member called

        notes.txt\\n\\n  0 error(s), 0 warning(s), 0 note(s)\\n\\nsupplier-delivery.zip\\n  no findings\\n

    put a summary line and a second container's clean verdict into the middle of
    a finding. `--json` was never affected — `json.dumps` escapes it — so only
    the page people read was forgeable.

    `as_written` is the tool for it: a newline is a character that draws nothing
    and it spells those out, while leaving an ordinary name, decomposed Korean
    included, exactly as the archive spells it. Escaping this line with `escaped`
    would have hexed every filename in every report from a delivery written on a
    Mac.
    """
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT
    from vdi2770_validate.report import as_text
    from vdi2770_validate.runner import check_bytes

    forged = ("notes.txt\n\n  0 error(s), 0 warning(s), 0 note(s)\n\n"
              "supplier-delivery.zip\n  no findings\n")
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            z.writestr(name, src.read(name))
        z.writestr(forged, b"x")
    page = as_text(check_bytes(buf.getvalue(), "t.zip"), True)

    assert "supplier-delivery.zip" in page, "the name should still be reported"
    assert "\n  no findings" not in page, "a member name forged a line of the report"
    assert "\n  0 error(s), 0 warning(s), 0 note(s)\n\n" not in page, (
        "a member name forged a summary line")
    # Exactly one *line* that is a summary line, and it is the tool's own. The
    # words still appear inside the escaped name, which is honest -- that is what
    # the member is called. What they cannot do any more is begin a line.
    summaries = [line for line in page.splitlines()
                 if re.match(r"^  \d+ error\(s\), ", line)]
    assert len(summaries) == 1, summaries


def test_a_difference_a_reader_can_see_is_left_readable():
    """The repair for one invisible difference started hexing visible ones.

    `identification` against `Identification` differs in one ASCII letter, and
    printing `'\\u0069dentification'` beside `'\\u0049dentification'` buries the
    one character that matters. It reached this project's own corpus: the `M4`
    finding for `demo_invalid_doc_type_names.zip` was the only content that
    changed in forty-six containers, and it changed for the worse.
    """
    from vdi2770_validate.names import told_apart

    for observed, published in (("identification", "Identification"),
                                ("Technische Spezifikatiom", "Technische Spezifikation"),
                                ("Betriebsanleitung", "Technische Spezifikation"),
                                ("Technische Spezifikationen", "Technische Spezifikation")):
        shown, against = told_apart(observed, published)
        assert "\\u" not in shown and "\\u" not in against, (
            f"a difference a reader can see was spelled out: {shown!r} / {against!r}")


def test_a_difference_at_both_ends_is_still_spelled():
    """`head == 0 and tail == 0` was read as *alike in nothing* and left raw.

    Two homoglyphs, one at each end, share neither a prefix nor a suffix — and
    that is not "alike in nothing", it is the case where the whole string is the
    differing run. `Вauteilе` against `Bauteile`, Cyrillic В and е, came back
    unspelled on both sides: the finding named the name it was asking for.
    """
    from vdi2770_validate.names import told_apart

    observed = "Вauteilе"          # Cyrillic В … е
    published = "Bauteile"
    assert len(observed) == len(published)
    shown, against = told_apart(observed, published)
    assert "\\u0412" in shown and "\\u0042" in against, (shown, against)
    assert "\\u0435" in shown and "\\u0065" in against, (shown, against)
    # And only those: the letters in between are plain and stay plain.
    assert "auteil" in shown and "auteil" in against, (shown, against)


def test_one_invisible_difference_does_not_hide_another():
    """A trailing space explained, and the homoglyph beside it drawn as Latin.

    The early return fired when `escaped` had changed *something*, not when it
    had shown *the* difference. The supplier strips the space, resubmits, and
    fails again for a reason the report showed them once and never named.
    """
    from vdi2770_validate.names import told_apart

    shown, against = told_apart("Tеchnische Spezifikation ",
                                "Technische Spezifikation")
    assert "\\u0020" in shown, shown          # the trailing space
    assert "\\u0435" in shown and "\\u0065" in against, (shown, against)


def test_a_length_change_made_only_of_whitespace_is_spelled():
    """A doubled space is a difference nobody can see, and it changes the length,
    so the length test alone let it through."""
    from vdi2770_validate.names import told_apart

    shown, against = told_apart("Technische  Spezifikation", "Technische Spezifikation")
    assert "\\u0020" in shown, shown
    assert "\\u" not in against, against


def test_free_text_has_no_path_segments():
    """`escaped` renders member names and class names, and only one of them is a
    path. Splitting on `/` made both spaces around a slash in a class name the
    edge of a *segment*, so they were spelled out while the slash — the thing
    that is actually wrong — was left for the reader to find among the escapes.
    """
    from vdi2770_validate.names import escaped, told_apart

    shown, _ = told_apart("Technische / Spezifikation", "Technische Spezifikation")
    assert shown == "Technische / Spezifikation", shown
    # A member name is still a path, and a space at a segment edge still shows.
    assert escaped("docs /B.pdf") != "docs /B.pdf"
