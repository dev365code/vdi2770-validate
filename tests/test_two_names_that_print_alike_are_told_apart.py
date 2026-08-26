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
    identical lines — the detail interpolates other things, and the location line
    carries the raw member name. This asserts on the sentence.
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
