#!/usr/bin/env python3
"""Capabilities picture: six axes, what is checked now against what this project asks of itself before 1.0.

Each repository keeps this file at tools/capabilities_svg.py, the data in docs/capabilities.json, the
rendered docs/capabilities.svg and docs/capabilities.md committed, and a test that calls `--check`.

Usage:
  capabilities_svg.py docs/capabilities.json            write the picture and the summary, stamp README
  capabilities_svg.py docs/capabilities.json --check    exit 1 if the committed files or the stamp differ

Data file (public text only):
{
  "product": "your-project",              # the name the page uses for itself (each repo's own; never another's)
  "as_of": "0.7.0",                       # must equal the package version (the test asserts it)
  "detail": "docs/what-it-catches.md",    # where the picture links to
  "axes": [                               # exactly six, in drawing order (top, then clockwise)
    {"key": "coverage", "label": "Coverage",
     "now": 40, "target": 60,             # a measured count: ratio drawn = min(now / target, 1)
     "now_text": "40 of 80 obligations covered",         # leads with now
     "target_text": "at least 60 of 80 covered",         # leads with target
     "evidence": [{"file": "docs/scope.md", "says": "Coverage of the standard is 40 of 80"}]},
    {"key": "entrances", "label": "Entrances",
     "items": [                           # a checklist: now = items done, target = all items
       {"text": "command line", "done": true,
        "evidence": {"file": "pyproject.toml", "says": "yourtool = \"your_project.cli:main\""}},
       {"text": "browser, nothing installed", "done": false}],   # undone items need no evidence
     "now_text": "command line",                          # pieces of done items ("none yet" if none)
     "target_text": "+ browser, nothing installed"}       # "+ " pieces of undone items ("met" if none)
  ]
}
The card also carries "as of <as_of>" in its corner, so a copy of the picture shown beside an older
release's text still says which release it describes.
An axis is either a count (now/target) or a checklist (items); never both. Evidence is a file in
this repository plus the words that file says; `--check` and the test read the file and look for the
words, so a done item cannot point at a file that does not say it. What the gates hold the words to:
  - a quote is at least three words, and never from a file generated from this data (the picture's
    own files, the detail page), nor from this generator or its test, nor from README's own copy of
    it (the "Where it stands" section, the 1.0 paragraph, HTML comments);
  - for a count, now_text, target_text and one quote each LEAD with the number drawn or promised,
    as whole tokens (280 in "172 of 280" is not 28 and not 280 for now=172);
  - for a checklist, every comma-separated piece of now_text is part of a done item, target_text is
    "+ " plus pieces of undone items, or exactly "met" when nothing is undone;
  - README states the 1.0 condition paragraph (`condition_paragraph`, printed at the end of
    docs/capabilities.md) verbatim in its visible text: every checklist item, done or not, right
    after its axis label, so a shrunken checklist changes a public sentence.
Words that would turn a self-description into a comparison (including comparatives and contrasts
such as "stricter than any other", "unlike other validators"), dates, and text too wide for the card
are refused. Output is deterministic: no dates, no environment values, fixed geometry. The picture
is a dark card with its own background, like the other pictures on the page, so it reads the same
on light and dark pages. README carries the picture as `capabilities.svg?v=<first 8 hex of its
sha256>` with the summary line as its alt text; writing the picture re-stamps both, and `--check`
confirms the stamp is the committed picture's, the alt text is the summary line, the 1.0 paragraph
is on the page, and the detail page exists.
"""
import hashlib
import json
import math
import os
import posixpath
import re
import sys
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SELF = "/".join(os.path.relpath(os.path.abspath(__file__), ROOT).split(os.sep))
# files whose words come from this data, or that are this machinery itself: none of them is evidence
OWN_FILES = ("docs/capabilities.json", "docs/capabilities.svg", "docs/capabilities.md",
             _SELF, "tests/test_capabilities_current.py")

# A self-description, not a comparison. The short texts on the picture refuse these words outright,
# and so is any comparative or superlative aimed past this tool ("stricter than any other ...",
# "more rules than X", "unlike other validators", "the most thorough", "second to none").
# "than" followed by a number, in digits or words ("more than 200 rules", "more than one"), describes
# this tool and passes; so does "no other check here has run" -- only "no other" naming a tool is a
# comparison. Prose pages are read through prose_only(): captured output and quotations are not the
# project speaking -- the generated detail page only; README's hand-written section is read as visible()
# text, every line. (v3.2)
NUM = (r"(?:\d[\d.,]*|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|"
       r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|once|twice|half)")
TOOL = (r"(?:validators?|tools?|checkers?|readers?|projects?|implementations?|librar(?:y|ies)|linters?|SDKs?|"
        r"products?|solutions?|software|programs?|engines?)")
OWN = (r"(?:checks?|rules?|findings?|files?|entr(?:y|ies)|values?|propert(?:y|ies)|elements?|records?|cases?|"
       r"lines?|items?|packages?|units?)")
COMPARATIVE = (rf"(?<!rather )(?<!other )\bthan\b(?!\s+{NUM}\b(?!\s+(?:as|times)\b))|"  # "than twice as many" is not a count
               r"\b(?:unlike|versus|vs\.?|compared\s+(?:to|with)|competit\w*|outperform\w*)\b|"
               rf"\bother\s+(?:[\w.+-]+\s+){{0,2}}?{TOOL}\b|"  # "other iiRDS validators"
               rf"\b(?:any|no|none)\s+other\b(?!\s+{OWN}\b)|"  # "no other check here has run" passes
               rf"\bof\s+any\s+{TOOL}\b|"
               r"\bsecond\s+to\s+none\b|"
               r"\bmost\s+(?:thorough|complete|accurate|reliable|strict|precise|comprehensive|rigorous|careful|"
               r"capable|advanced|robust|mature|efficient|powerful|extensive|detailed)\b|"
               r"\b(?:strict|wid|broad|deep|rich|strong|safe|tough|full|tight|great)est\b|"
               r"\b(?:better|stricter|faster|stronger|safer|more\s+(?:accurate|complete|reliable|thorough))\b")
FORBIDDEN = re.compile(
    r"\b(world|first|only|unique|best|leading|fastest|unmatched|superior|exhaustive(?:ly)?|"
    r"guarantee[sd]?|certif\w*|state[- ]of[- ]the[- ]art|ahead\s+of|no(?:body|\s+one)\s+else)\b|"
    r"\bfalse[\s-]+positives?\b|" + COMPARATIVE, re.IGNORECASE)
# Prose pages (the detail page, the README paragraph) get the same list without the everyday words.
FORBIDDEN_PROSE = re.compile(
    r"\b(world|best|leading|fastest|unmatched|superior|exhaustive(?:ly)?|"
    r"guarantee[sd]?|certif\w*|state[- ]of[- ]the[- ]art|ahead\s+of|no(?:body|\s+one)\s+else)\b|"
    r"(?<!be )\bunique(?:ly)?\b(?!\s+(?:within|in|per|across|to|for)\b)|"  # "MUST be unique within" passes
    r"\bfalse[\s-]+positives?\b|" + COMPARATIVE, re.IGNORECASE)
DATED = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b|\bQ[1-4]\b|"
                   r"\b(?:January|February|March|April|June|July|August|September|October|November|December)\b")
MARKUP = re.compile(r'["<>&|]')      # would break the alt attribute, a markdown table cell, or the picture

W, H = 950, 330                      # card size
CX, CY, R = 232, 162, 104            # radar centre and radius (left labels need ~120 px of room)
RINGS = (0.25, 0.5, 0.75, 1.0)
PANEL_X = 450                        # right-hand summary panel (right-side axis labels end near 440)
COL_TEXT = 150                       # text column offset inside the panel
ROW_Y0, ROW_DY = 92, 36
# width budgets in px, estimated per glyph class (proportional fonts: a count of characters proves nothing)
BUDGET = {"label": (106, 12, False), "now_text": (W - 24 - PANEL_X - COL_TEXT, 12, False),
          "target_text": (W - 24 - PANEL_X - COL_TEXT - 27, 11, False)}
FONT = "-apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
# palette: a dark card, like the sibling pictures; ink is off-white, the accent is teal, the 1.0 ring is grey
BG, INK, INK2, LINE, ACCENT, TARGET = "#0b0f14", "#e6edf3", "#9da7b1", "#2a3238", "#2dd4bf", "#7d8891"


def _pt(i, ratio):
    a = -math.pi / 2 + i * math.pi / 3          # six axes, first at 12 o'clock, clockwise
    return CX + R * ratio * math.cos(a), CY + R * ratio * math.sin(a)


def _fmt(x, y):
    return f"{x:.1f},{y:.1f}"


def _width(text, size, bold=False):
    w = 0.0
    for c in text:
        if c in "WM":
            w += 0.95
        elif c.isupper() or c.isdigit():
            w += 0.75
        elif c in " il.,:;'":
            w += 0.3
        else:
            w += 0.55
    return w * size * (1.08 if bold else 1.0)


def _refuse(where, text):
    m = FORBIDDEN.search(text or "")
    if m:
        raise SystemExit(f"{where}: the word {m.group(0)!r} turns a self-description into a comparison; "
                         f"the picture describes this tool and nothing else")
    m = DATED.search(text or "")
    if m:
        raise SystemExit(f"{where}: {m.group(0)!r} says when; the picture says what, not when")
    m = MARKUP.search(text or "")
    if m:
        raise SystemExit(f"{where}: {m.group(0)!r} is not allowed in picture text (alt text, table cells)")


def _numbers(text):
    """Whole-number tokens in reading order; '220' is not a hit for 22, '280' is not a hit for 28."""
    return [int(n) for n in re.findall(r"(?<![\d.,])\d+(?![\d.,])", text or "")]


def _pieces(text, prefix=""):
    """The comma-separated pieces of a short summary, casefolded, without the given prefix."""
    body = text[len(prefix):] if text.startswith(prefix) else None
    if body is None:
        raise SystemExit(f"summary {text!r} must start with {prefix!r}")
    pieces = [p.strip().casefold() for p in body.split(",")]
    if not all(pieces):
        raise SystemExit(f"summary {text!r} has an empty piece")
    return pieces


def _evidence(where, ev, generated):
    if not isinstance(ev, dict) or not ev.get("file") or not isinstance(ev.get("says"), str):
        raise SystemExit(f"{where}: evidence must be {{\"file\": ..., \"says\": ...}}")
    raw = ev["file"]
    if "\\" in raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise SystemExit(f"{where}: evidence {raw!r} must be a relative posix path inside the repository")
    # posixpath on purpose: os.path is ntpath on Windows, which would render backslashes into the
    # committed summary (a spurious drift) and would let "..\\" past the check below.
    path = posixpath.normpath(raw)
    if path == ".." or path.startswith("../"):
        raise SystemExit(f"{where}: evidence {raw!r} points outside the repository")
    if path.casefold() in generated:
        raise SystemExit(f"{where}: evidence {raw!r} is generated from this data or copied from the picture; "
                         f"cite the page the fact comes from")
    says = ev["says"].strip()
    if len(says) < 12 or len(says.split()) < 3 or not re.search(r"[A-Za-z0-9]", says):
        raise SystemExit(f"{where}: evidence 'says' must quote at least three words of the file "
                         f"(a fragment like {ev['says']!r} is found in almost any file)")
    return {"file": path, "says": ev["says"]}


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for k in ("product", "as_of", "detail"):
        if not data.get(k):
            raise SystemExit(f"missing {k}")
    _refuse("product", data["product"])
    _refuse("as_of", str(data["as_of"]))
    # files whose words come from this data (or are copied from the picture) cannot be evidence for it
    generated = {f.casefold() for f in OWN_FILES} | {posixpath.normpath(data["detail"]).casefold()}
    axes = data["axes"]
    if len(axes) != 6:
        raise SystemExit(f"exactly six axes are drawn; got {len(axes)}")
    seen = set()
    for ax in axes:
        key = ax.get("key", "?")
        for k in ("key", "label", "now_text", "target_text"):
            if k not in ax:
                raise SystemExit(f"axis {key}: missing {k}")
        if key in seen:
            raise SystemExit(f"axis {key}: duplicate key")
        seen.add(key)
        if "items" in ax:
            if "now" in ax or "target" in ax or "evidence" in ax:
                raise SystemExit(f"axis {key}: a checklist carries items, not now/target/evidence")
            if not ax["items"]:
                raise SystemExit(f"axis {key}: empty checklist")
            for it in ax["items"]:
                if "text" not in it or "done" not in it:
                    raise SystemExit(f"axis {key}: every item needs text and done")
                _refuse(f"axis {key} item", it["text"])
                if it["done"]:
                    it["evidence"] = _evidence(f"axis {key} item {it['text']!r}", it.get("evidence"), generated)
            ax["now"] = sum(1 for it in ax["items"] if it["done"])
            ax["target"] = len(ax["items"])
            ax["evidence"] = [it["evidence"] for it in ax["items"] if it["done"]]
            # the two summaries are abbreviations of the items, not free text: every comma-separated
            # piece of now_text is part of a done item, every piece of target_text (after "+ ") is part
            # of an undone item, and "met" is the only target_text when nothing is undone
            done = [it["text"].casefold() for it in ax["items"] if it["done"]]
            undone = [it["text"].casefold() for it in ax["items"] if not it["done"]]
            if not done:
                if ax["now_text"] != "none yet":
                    raise SystemExit(f"axis {key}: with no item done, now_text is 'none yet'")
            else:
                for piece in _pieces(ax["now_text"]):
                    if not any(piece in d for d in done):
                        raise SystemExit(f"axis {key}: now_text piece {piece!r} is not part of any done item")
            if not undone:
                if ax["target_text"] != "met":
                    raise SystemExit(f"axis {key}: with every item done, target_text is 'met'")
            else:
                for piece in _pieces(ax["target_text"], "+ "):
                    if not any(piece in u for u in undone):
                        raise SystemExit(f"axis {key}: target_text piece {piece!r} is not part of any undone item")
        else:
            for k in ("now", "target", "evidence"):
                if k not in ax:
                    raise SystemExit(f"axis {key}: missing {k}")
            if not ax["evidence"]:
                raise SystemExit(f"axis {key}: a count names at least one evidence file")
            if not isinstance(ax["now"], int) or not isinstance(ax["target"], int):
                raise SystemExit(f"axis {key}: now and target are whole numbers")
            ax["evidence"] = [_evidence(f"axis {key}", ev, generated) for ev in ax["evidence"]]
            # the count drawn is the first number of now_text and of one evidence quote, and the count
            # promised is the first number of target_text — whole tokens, so 280 in "172 of 280" is not
            # a hit for now=28 or now=280, and the polygon cannot move without the words moving
            if _numbers(ax["now_text"])[:1] != [ax["now"]]:
                raise SystemExit(f"axis {key}: now_text {ax['now_text']!r} must lead with now={ax['now']}")
            if _numbers(ax["target_text"])[:1] != [ax["target"]]:
                raise SystemExit(f"axis {key}: target_text {ax['target_text']!r} must lead with target={ax['target']}")
            if not any(_numbers(ev["says"])[:1] == [ax["now"]] for ev in ax["evidence"]):
                raise SystemExit(f"axis {key}: no evidence quote leads with the count now={ax['now']}")
        if ax["target"] <= 0:
            raise SystemExit(f"axis {key}: target must be positive")
        if ax["now"] < 0:
            raise SystemExit(f"axis {key}: now must not be negative")
        for k, (budget, size, bold) in BUDGET.items():
            _refuse(f"axis {key} {k}", ax[k])
            if _width(ax[k], size, bold) > budget:
                raise SystemExit(f"axis {key}: {k} {ax[k]!r} is too wide for the card "
                                 f"(about {_width(ax[k], size, bold):.0f} px of {budget}); the long form belongs "
                                 f"on the detail page")
    return data


def ratio(ax):
    return min(ax["now"] / ax["target"], 1.0)


def summary_line(data):
    """One line, the same six facts as the picture; README uses it as the image alt text."""
    return "; ".join(f"{ax['label']}: {ax['now_text']}" for ax in data["axes"])


def condition_paragraph(data):
    """The 1.0 condition in full — every checklist item, done or not — as README must state it.

    The picture's outer ring is this paragraph; README carries it verbatim (the test and `--check`
    look for it in the visible text, after stripping HTML comments), each condition right after its
    axis label, so the picture cannot promise what the page does not, and a shrunken checklist shows
    up as a change to a public sentence.
    """
    parts = []
    for ax in data["axes"]:
        if "items" in ax:
            parts.append(f"{ax['label']}: " + " · ".join(it["text"] for it in ax["items"]))
        else:
            parts.append(f"{ax['label']}: {ax['target_text']}")
    return "Before it calls a release 1.0, this project asks of itself — " + "; ".join(parts) + "."


COMMENT = re.compile(r"<!--(?:-?>|.*?-->)", re.DOTALL)
STANDS = re.compile(r"(?ms)^## Where it stands$.*?(?=^## |\Z)")


def _squash(text):
    return re.sub(r"\s+", " ", text)


FENCE = re.compile(r"(?ms)^[ \t]*(`{3,}|~{3,})[^`\n]*$.*?^[ \t]*\1[ \t]*$")
CAPTURED = re.compile(r"(?m)^(?:(?: {4}|\t).*|>.*|\s*<?https?://\S+>?\s*|\[[^\]]+\]:\s*\S+.*)$")


def prose_only(text):
    """A generated page's own words: fenced and indented blocks (captured tool output, quoted rule text),
    quotation lines and bare link lines are not the project speaking, so the comparison gate does not read
    them. Hand-written README text is read whole (visible()), since a reader sees every line of it."""
    return CAPTURED.sub(" ", FENCE.sub(" ", visible(text)))


def visible(text):
    """Markdown as a reader sees it: without HTML comments."""
    return COMMENT.sub(" ", text)


def _quotable(path, text, data):
    """The part of a file that may be quoted as evidence: README without the picture's own section
    and the 1.0 paragraph (both are copies of this data), markdown without HTML comments."""
    if path.casefold().endswith(".md"):
        text = visible(text)
    if posixpath.basename(path).casefold() == "readme.md":
        text = STANDS.sub(" ", text)
        if data is not None:
            text = _squash(text).replace(_squash(condition_paragraph(data)), " ")
    return text


def evidence_holds(root, ev, data=None):
    """True when the evidence file lies inside root and contains the words it is said to say."""
    rootr = os.path.realpath(root)
    real = os.path.realpath(os.path.join(rootr, ev["file"]))
    if os.path.commonpath([rootr, real]) != rootr or not os.path.isfile(real):
        return False
    try:
        with open(real, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    return _squash(ev["says"]) in _squash(_quotable(ev["file"], text, data))


def digest_of(svg_text):
    return hashlib.sha256(svg_text.encode("utf-8")).hexdigest()[:8]


def render_svg(data):
    axes = data["axes"]
    title = data["product"]
    out = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
               f'role="img" aria-labelledby="t d">')
    out.append(f'<title id="t">{escape(title)}: six capability axes, what is checked now against the 1.0 condition</title>')
    desc = "; ".join(f"{ax['label']}: {ax['now_text']} (1.0: {ax['target_text']})" for ax in axes)
    out.append(f'<desc id="d">{escape(desc)}; as of {escape(str(data["as_of"]))}</desc>')
    out.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="{BG}" stroke="{LINE}"/>')
    # rings (the outer ring is the 1.0 condition)
    for r in RINGS:
        pts = " ".join(_fmt(*_pt(i, r)) for i in range(6))
        stroke = TARGET if r == 1.0 else LINE
        width = 1.5 if r == 1.0 else 1
        dash = "" if r == 1.0 else ' stroke-dasharray="3 3"'
        out.append(f'<polygon points="{pts}" fill="none" stroke="{stroke}" stroke-width="{width}"{dash}/>')
    # spokes
    for i in range(6):
        x, y = _pt(i, 1.0)
        out.append(f'<line x1="{CX}" y1="{CY}" x2="{x:.1f}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
    # now polygon
    pts = " ".join(_fmt(*_pt(i, ratio(ax))) for i, ax in enumerate(axes))
    out.append(f'<polygon points="{pts}" fill="{ACCENT}" fill-opacity="0.16" stroke="{ACCENT}" stroke-width="2" '
               f'stroke-linejoin="round"/>')
    for i, ax in enumerate(axes):
        x, y = _pt(i, ratio(ax))
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{ACCENT}"/>')
    # axis labels, placed outside the outer ring with an anchor that depends on the side
    anchors = ["middle", "start", "start", "middle", "end", "end"]
    dy = [-10, 4, 14, 20, 14, 4]
    dx = [0, 8, 8, 0, -8, -8]
    for i, ax in enumerate(axes):
        x, y = _pt(i, 1.0)
        out.append(f'<text x="{x + dx[i]:.1f}" y="{y + dy[i]:.1f}" text-anchor="{anchors[i]}" font-family="{FONT}" '
                   f'font-size="12" fill="{INK}">{escape(ax["label"])}</text>')
    # legend, bottom-left corner of the card (clear of the bottom axis label)
    ly = H - 16
    out.append(f'<line x1="24" y1="{ly - 4}" x2="44" y2="{ly - 4}" stroke="{ACCENT}" stroke-width="2"/>')
    out.append(f'<text x="50" y="{ly}" font-family="{FONT}" font-size="11" fill="{INK2}">now</text>')
    out.append(f'<line x1="86" y1="{ly - 4}" x2="106" y2="{ly - 4}" stroke="{TARGET}" stroke-width="1.5"/>')
    out.append(f'<text x="112" y="{ly}" font-family="{FONT}" font-size="11" fill="{INK2}">1.0 condition</text>')
    # the version this picture describes: a copy of the picture shown beside an older release's text
    # (a package index keeps each release's page) still says which release it is about
    out.append(f'<text x="{W - 24}" y="{ly}" text-anchor="end" font-family="{FONT}" font-size="11" fill="{INK2}">'
               f'as of {escape(str(data["as_of"]))}</text>')
    # right panel: title, then one row per axis (label, what is checked now, the 1.0 condition)
    out.append(f'<text x="{PANEL_X}" y="40" font-family="{FONT}" font-size="16" font-weight="600" fill="{INK}">'
               f'{escape(title)}</text>')
    out.append(f'<text x="{PANEL_X}" y="62" font-family="{FONT}" font-size="12" fill="{INK2}">'
               f'Checked now, and what this project asks of itself for 1.0.</text>')
    out.append(f'<line x1="{PANEL_X}" y1="72" x2="{W - 24}" y2="72" stroke="{LINE}"/>')
    for i, ax in enumerate(axes):
        y = ROW_Y0 + i * ROW_DY
        out.append(f'<text x="{PANEL_X}" y="{y}" font-family="{FONT}" font-size="13" font-weight="600" fill="{INK}">'
                   f'{escape(ax["label"])}</text>')
        out.append(f'<text x="{PANEL_X + COL_TEXT}" y="{y}" font-family="{FONT}" font-size="12" fill="{INK}">'
                   f'{escape(ax["now_text"])}</text>')
        out.append(f'<text x="{PANEL_X + COL_TEXT}" y="{y + 14}" font-family="{FONT}" font-size="11" fill="{INK2}">'
                   f'1.0: {escape(ax["target_text"])}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_md(data):
    """Markdown summary for the detail page and for readers without the picture."""
    lines = ["| Axis | Now | 1.0 condition |", "|---|---|---|"]
    for ax in data["axes"]:
        lines.append(f"| {ax['label']} | {ax['now_text']} | {ax['target_text']} |")
    for ax in data["axes"]:
        if "items" in ax:
            lines.append("")
            lines.append(f"**{ax['label']}** — {ax['now']} of {ax['target']}:")
            for it in ax["items"]:
                if it["done"]:
                    lines.append(f"- {it['text']} — done (`{it['evidence']['file']}`: \"{it['evidence']['says']}\")")
                else:
                    lines.append(f"- {it['text']} — not yet")
    lines += ["", condition_paragraph(data)]
    return "\n".join(lines) + "\n"


STAMP = re.compile(r"(capabilities\.svg\?v=)[0-9a-fA-F]+")
# the README image's alt text is the summary line; the generator rewrites it with the stamp so that a
# change to any now_text cannot leave the page saying something the picture no longer says
ALT = re.compile(r'(capabilities\.svg\?v=[0-9a-fA-F]+"\s+alt=")[^"]*(")')


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main(argv):
    if len(argv) < 2 or argv[1].startswith("--"):
        print(__doc__)
        return 2
    src = os.path.abspath(argv[1])
    if not os.path.isfile(src):
        print(f"no such data file: {src}")
        return 2
    if os.path.dirname(src) != os.path.join(ROOT, "docs"):
        print(f"the data file must live in {os.path.join(ROOT, 'docs')} (found {src})")
        return 2
    data = load(src)
    base = os.path.splitext(src)[0]
    svg_path, md_path = base + ".svg", base + ".md"
    readme = os.path.join(ROOT, "README.md")
    svg, md = render_svg(data), render_md(data)
    if "--check" in argv:
        bad = []
        for path, want in ((svg_path, svg), (md_path, md)):
            have = _read(path) if os.path.exists(path) else None
            if have != want:
                bad.append(f"{os.path.relpath(path, ROOT)} is stale or missing: rerun the generator")
        for ax in data["axes"]:
            for ev in ax["evidence"]:
                if not evidence_holds(ROOT, ev, data):
                    bad.append(f"{ax['key']}: {ev['file']} does not say {ev['says']!r} "
                               f"(or is missing, or says it only in the picture's own text)")
        if not os.path.isfile(os.path.join(ROOT, data["detail"])):
            bad.append(f"detail page {data['detail']} does not exist (the picture would link to a 404)")
        if os.path.exists(readme):
            page = visible(_read(readme))
            if STAMP.search(page) and f"capabilities.svg?v={digest_of(svg)}" not in page:
                bad.append("README.md: the ?v= stamp is not the committed picture's hash; rerun the generator")
            if "capabilities.svg" not in page:
                bad.append("README.md does not embed docs/capabilities.svg")
            elif f'alt="{summary_line(data)}"' not in page:
                bad.append("README.md: the picture's alt text is not the generator's summary line")
            if _squash(condition_paragraph(data)) not in _squash(page):
                bad.append("README.md does not state the 1.0 condition paragraph (see docs/capabilities.md)")
        if bad:
            print("capabilities drift:", *bad, sep="\n  ")
            return 1
        print("capabilities current")
        return 0
    _write(svg_path, svg)
    _write(md_path, md)
    print("wrote", os.path.relpath(svg_path, ROOT), os.path.relpath(md_path, ROOT))
    if os.path.exists(readme):
        page = _read(readme)
        stamped, n = STAMP.subn(lambda m: m.group(1) + digest_of(svg), page)
        stamped, n_alt = ALT.subn(lambda m: m.group(1) + summary_line(data) + m.group(2), stamped)
        if (n or n_alt) and stamped != page:
            _write(readme, stamped)
            print(f"stamped README.md ?v={digest_of(svg)}" + (" and the alt text" if n_alt else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
