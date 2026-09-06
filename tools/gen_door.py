#!/usr/bin/env python3
"""Draw the front door: `docs/assets/door.svg` and `docs/assets/tenseconds.svg`.

The banner is mathematics and words -- a grid pulled toward a gravity well, an
event-horizon ring, one slow hotspot -- and carries no count and no version, so
there is nothing in it that can go stale. The terminal shot is the real output
of `vdi2770-validate` on a container that ships in this repository, laid out
over more rows than a terminal would use and given colour; the characters are
the tool's.

Neither is trusted. `--check` rebuilds both and fails if either differs from
what is committed, and `tests/test_the_front_door_pictures_are_true.py` rebuilds
every logical line out of `SHOT_LINES` and asserts it against a live run. A
drawing of a verdict that no longer matches the verdict is worse than no
drawing, because it reads exactly like a true one.

Writing also restamps the front page's `?v=` for each picture with that
picture's hash. GitHub serves these through an image proxy that caches by URL,
so a changed file behind an unchanged address reaches nobody who has already
seen the old one -- and "regenerate, then restamp" being two steps is how the
second one gets forgotten.

    python3 tools/gen_door.py            # write, and restamp the front page
    python3 tools/gen_door.py --check    # fail if what is committed differs
"""
from __future__ import annotations

import hashlib
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets"
README = ROOT / "README.md"

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SANS = ("-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,"
        "'Apple SD Gothic Neo','Malgun Gothic',sans-serif")

# ── the banner ──────────────────────────────────────────────────────────────
CX, CY, W, H = 470.0, 100.0, 940, 408
A, S, EXT = 0.55, 165.0, 182

#: The wordmark, sized by the line's rule: ceiling 52, floor 40, and within that
#: the largest whole size whose drawn width stays under 60% of the canvas. The
#: ceiling binds first -- a short name must not be allowed to grow to fill the
#: allowance -- and only then the width. `vdi2770-validate.` is seventeen glyphs
#: and the narrowest real face in the stack advances 0.60205em, so 52 draws it
#: at 532px, 57% of 940: the ceiling is what decides, not the width.
WORDMARK = "vdi2770-validate"
WORDMARK_SIZE = 52


def _warp(x, y):
    dx, dy = x - CX, y - CY
    r = math.hypot(dx, dy)
    g = 1.0 - A * math.exp(-(r / S) ** 2)
    return CX + dx * g, CY + dy * g


def _grid():
    parts = []
    for xi in range(-EXT, W + EXT + 1, 26):
        pts = [_warp(xi, yy) for yy in range(-EXT, H + 1, 10)]
        parts.append('M' + 'L'.join(f'{px:.1f},{py:.1f}' for px, py in pts))
    for yi in range(-EXT, H + 1, 26):
        pts = [_warp(xx, yi) for xx in range(-EXT, W + EXT + 1, 10)]
        parts.append('M' + 'L'.join(f'{px:.1f},{py:.1f}' for px, py in pts))
    return " ".join(parts)


def _smear():
    segs, N, SPAN, RR = [], 48, 94.0, 57
    C = 2 * math.pi * RR
    seg = C * (SPAN / 360.0) / N
    for i in range(N):
        t = (i + 0.5) / N
        op = 0.55 * (1 - abs(t - 0.5) * 2)
        off = -C * (SPAN / 360.0) * i / N
        segs.append(f'<circle cx="470" cy="100" r="{RR}" fill="none" stroke="#ffeede" '
                    f'stroke-opacity="{op:.3f}" stroke-width="18" '
                    f'stroke-dasharray="{seg:.2f} {C-seg:.2f}" stroke-dashoffset="{off:.2f}"/>')
    return "".join(segs)


def banner() -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 408" role="img" aria-label="vdi2770-validate — check VDI 2770 document containers offline: deterministic, and every finding tells you how to fix it">
<defs>
<radialGradient id="halo" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#2f5d8a" stop-opacity=".30"/><stop offset="100%" stop-color="#2f5d8a" stop-opacity="0"/></radialGradient>
<filter id="soft"><feGaussianBlur stdDeviation="2.2"/></filter>
<filter id="softer"><feGaussianBlur stdDeviation="5"/></filter>
<filter id="smear" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="3"/></filter>
</defs>
<rect width="940" height="408" fill="#0b0f14"/>
<path d="{_grid()}" fill="none" stroke="rgba(198,212,224,0.075)" stroke-width="1"/>
<circle cx="470" cy="100" r="230" fill="url(#halo)"/>
<circle cx="470" cy="100" r="58" fill="none" stroke="#8fb8dd" stroke-opacity=".28" stroke-width="7" filter="url(#softer)"/>
<circle cx="470" cy="100" r="51" fill="#03050a"/>
<circle cx="470" cy="100" r="57" fill="none" stroke="#ffeede" stroke-opacity=".45" stroke-width="2" filter="url(#soft)"/>
<g filter="url(#smear)">{_smear()}
<animateTransform attributeName="transform" type="rotate" from="0 470 100" to="360 470 100" dur="16s" repeatCount="indefinite"/></g>
<text x="470" y="206" font-family="{MONO}" font-size="12.5" letter-spacing="3.4" fill="#93a1ad" text-anchor="middle">STANDARDS, JUDGED OFFLINE</text>
<text x="470" y="262" font-family="{MONO}" font-size="{WORDMARK_SIZE}" font-weight="700" fill="#e8edf2" text-anchor="middle">{WORDMARK}<tspan fill="#8fb8dd">.</tspan></text>
<text x="470" y="292" font-family="{SANS}" font-size="15.5" fill="#c6d2dc" text-anchor="middle">Check VDI 2770 document containers before they ship —</text>
<text x="470" y="313" font-family="{SANS}" font-size="15.5" fill="#c6d2dc" text-anchor="middle">offline, deterministic, and every finding tells you how to fix it.</text>
<text x="470" y="345" font-family="{MONO}" font-size="15" font-weight="700" fill="#e8edf2" text-anchor="middle">AI proposes. <tspan fill="#8fb8dd">Rules judge.</tspan> People decide.</text>
<text x="470" y="376" text-anchor="middle" font-family="{SANS}" font-size="12" fill="#93a1ad"><tspan font-family="{MONO}" font-size="10.5" font-weight="700" fill="#7da7cf">DE&#160;&#160;</tspan>Prüft VDI 2770-Container offline<tspan font-family="{MONO}" font-size="10.5" font-weight="700" fill="#ddab74">&#160;&#160;&#160;&#160;&#160;KO&#160;&#160;</tspan>VDI 2770 컨테이너 오프라인 검증</text>
</svg>'''


# ── the terminal shot ───────────────────────────────────────────────────────
#: The run the picture shows, as arguments. The test that checks the drawing
#: executes exactly this, so the picture and the run cannot part.
SHOT_COMMAND = ["check", "corpus/examples/missingdocuments/folders.zip"]

G, D, E, A_, F, T, N = "#8fd0a8", "#7d8a99", "#e0604d", "#e8c268", "#5cb87f", "#d8dfe5", "#93a1ad"

#: Each row is `(leading, runs, kind)`. `kind` says what the row *claims*:
#:
#: A run carries the spaces the tool printed even though `x` already puts it
#: where it belongs: the drawing is laid out by geometry and the *text* has to
#: stay the tool's, or the gate below reconstructs "errorF1A file named…" and
#: compares that against a line nobody printed.
#:
#:   "chrome"  — the prompt. Not output; checked as a command this project has.
#:   "line"    — one line the tool printed. Asserted against a live run.
#:   "wrap"    — the rest of the line above it. This shot is 940 pixels wide and
#:               the tool wraps nothing, so a remedy has to be laid out over
#:               rows. Recorded here rather than guessed from indentation later,
#:               because guessing is how a genuinely missing line gets silently
#:               glued to the one above it.
#:   "elision" — a marked gap. Still a claim about the output, so it has a gate.
SHOT_LINES = [
    (21, [(28, G, "$ ", 1), (46, T, "pip install vdi2770-validate", 0)], "chrome"),
    (30, [(28, G, "$ ", 1),
          (46, T, "vdi2770-validate check corpus/examples/missingdocuments/folders.zip", 0)], "chrome"),
    (24, [(28, T, "folders.zip", 1)], "line"),
    (19, [(46, E, "error ", 1), (104, A_, "F1 ", 1),
          (150, T, "A file named in the metadata is not in the container", 0)], "line"),
    (17, [(150, N, "at ", 0), (172, D, "folders.zip!/VDI2770_Main.xml:56:2", 0)], "line"),
    (19, [(150, D, "'VDI2770_Main.pdf' is declared but not in the archive", 0)], "line"),
    (17, [(150, N, "per the reference implementation - observed there, not verified", 0)], "line"),
    (19, [(172, N, "against the standard (REP_007)", 0)], "wrap"),
    (17, [(150, F, "-> Add the missing file to the container, or remove its DigitalFile entry", 0)], "line"),
    (26, [(172, F, "from the metadata. The two must agree.", 0)], "wrap"),
    (19, [(46, E, "error ", 1), (104, A_, "Z7 ", 1),
          (150, T, "The documentation container has no VDI2770_Main.pdf", 0)], "line"),
    (19, [(150, N, "at ", 0), (172, D, "folders.zip", 0)], "line"),
    (17, [(150, N, "per the reference implementation - observed there, not verified", 0)], "line"),
    (19, [(172, N, "against the standard (REP_025)", 0)], "wrap"),
    (17, [(150, F, "-> Add the main document as VDI2770_Main.pdf at the root of the", 0)], "line"),
    (28, [(172, F, "documentation container, next to VDI2770_Main.xml.", 0)], "wrap"),
    (30, [(46, D, "… 1 more error (Z13) and 1 warning (Z9)", 0)], "elision"),
    (17, [(28, T, "3 error(s), 1 warning(s), 0 note(s) ", 1),
          (292, N, "— 1 of the errors is this tool", 0)], "line"),
    (21, [(292, N, "declining to look, not the container", 0)], "wrap"),
    (14, [(28, N, "read 1 of 1 archives, 1 of 3 metadata files", 0)], "line"),
]

SHOT = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 {h}" role="img" aria-label="Real vdi2770-validate output on a container that ships in this repository: error F1, a file named in the metadata is not in the container, with the line it is declared on and how to fix it; error Z7, the documentation container has no VDI2770_Main.pdf, with its remedy">
<rect x="1" y="1" width="938" height="{inner}" rx="10" fill="#12161a" stroke="#252b30" stroke-width="1.5"/>
<circle cx="24" cy="19" r="5" fill="#e0604d"/><circle cx="42" cy="19" r="5" fill="#e8c268"/><circle cx="60" cy="19" r="5" fill="#5cb87f"/>
<text x="80" y="23" font-family="{mono}" font-size="11" fill="#7d8a99">vdi2770-validate — real output, colour added</text>
{lines}
</svg>'''


def _escape(text: str) -> str:
    """XML, not HTML: a remedy that ever contains `&` or `<` would otherwise
    draw as a broken document rather than as the wrong sentence, and the gate
    that reads the drawing would never get to run."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tenseconds() -> str:
    rendered, y = [], 40
    for dy, runs, _kind in SHOT_LINES:
        parts = []
        for x, colour, text, bold in runs:
            weight = ' font-weight="700"' if bold else ""
            parts.append(
                f'<tspan x="{x}" fill="{colour}"{weight}>{_escape(text)}</tspan>')
        rendered.append(f'<text y="{y}" font-family="{MONO}" font-size="12.5" '
                        f'xml:space="preserve">{"".join(parts)}</text>')
        y += dy
    height = y + 18
    return SHOT.format(h=height, inner=height - 2, mono=MONO,
                       lines="".join(rendered))


PICTURES = {"door.svg": banner, "tenseconds.svg": tenseconds}


def _stamp(page: str, name: str, drawn: str):
    """Set the front page's `?v=` for one picture to that picture's hash."""
    digest = hashlib.sha256(drawn.encode("utf-8")).hexdigest()[:8]
    stamped, seen = re.subn(rf"({re.escape(name)}\?v=)[0-9a-f]+",
                            r"\g<1>" + digest, page)
    return stamped, seen, digest


def main(argv) -> int:
    checking = "--check" in argv
    OUT.mkdir(parents=True, exist_ok=True)
    page = README.read_text(encoding="utf-8") if README.is_file() else None
    stale = []
    for name, draw in PICTURES.items():
        drawn = draw()
        path = OUT / name
        if page is not None:
            page, seen, digest = _stamp(page, name, drawn)
            if not seen:
                stale.append(f"{name} (the front page does not point at it)")
            elif checking and f"{name}?v={digest}" not in \
                    README.read_text(encoding="utf-8"):
                stale.append(f"{name} (the front page's ?v= is not its hash)")
        if checking:
            if not path.is_file() or path.read_text(encoding="utf-8") != drawn:
                stale.append(name)
            continue
        path.write_text(drawn, encoding="utf-8")
        print(f"{name}  {len(drawn) // 1024} KB")
    if page is not None and not checking:
        README.write_text(page, encoding="utf-8")
    if stale:
        print("out of date, regenerate with tools/gen_door.py: "
              + ", ".join(stale), file=sys.stderr)
        return 1
    if checking:
        print("the front door's pictures match their generator")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
