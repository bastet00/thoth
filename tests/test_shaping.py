"""Shaping test for the built font, run by "make test".

    python3 tests/test_shaping.py [FONT.ttf]

Shapes text with HarfBuzz and compares the result with what the font must
do. Exits with status 1 if any expectation fails.
"""

import sys
from pathlib import Path

import ufoLib2
import uharfbuzz as hb
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from glyphsets import unicodes_per_glyphset

ROOT = Path(__file__).resolve().parent.parent
FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fonts/ttf/Thoth-Regular.ttf"
SOURCE = ROOT / "sources/Thoth-Regular.ufo"

SIGNS = [*range(0x13000, 0x13430), *range(0x13441, 0x13447)]
CONTROLS = range(0x13430, 0x13441)
FALLBACK = "control.fallback"

# Egyptological transliteration, beyond the basic Latin set.
TRANSLITERATION = [
    *range(0xA722, 0xA726),  # Ꜣ ꜣ Ꜥ ꜥ
    *range(0xA7BC, 0xA7BE),  # Ꞽ ꞽ
    *(0x1E24, 0x1E25, 0x1E2A, 0x1E2B, 0x1E96),  # Ḥ ḥ Ḫ ḫ ẖ
    *(0x0160, 0x0161, 0x015A, 0x015B),  # Š š Ś ś
    *(0x1E6E, 0x1E6F, 0x1E70, 0x1E71),  # Ṯ ṯ Ṱ ṱ
    *(0x1E0E, 0x1E0F, 0x1E32, 0x1E33),  # Ḏ ḏ Ḳ ḳ
    *(0x00EF, 0x0131, 0x02BE, 0x02BF),  # ï ı ʾ ʿ
    *(0x032E, 0x032F, 0x0331, 0x0357),  # combining marks
    *(0x2E17, 0x2E22, 0x2E23, 0x2E2E),  # ⸗ ⸢ ⸣ ⸮
]

# Golden lines: text and its exact shaping result, (glyph, advance, x, y) per
# glyph. The numbers are written here, not read from the font, so a moved
# anchor fails. U+034F keeps HarfBuzz from replacing h + U+0331 with ẖ.
GOLDEN = [
    ("H\u0331", [("H", 741, 0, 0), ("uni0331", 0, -373, 0)]),
    ("h\u034F\u0331", [("h", 618, 0, 0), ("space", 0, 0, 0), ("uni0331", 0, -308, 0)]),
    ("h\u0331", [("uni1E96", 618, 0, 0)]),  # composed to the precomposed ẖ
    ("i\u0357", [("dotlessi", 258, 0, 0), ("uni0357", 0, -128, 0)]),  # i loses its dot
    ("\u0131\u0357", [("dotlessi", 258, 0, 0), ("uni0357", 0, -128, 0)]),
    ("I\u0357", [("I", 339, 0, 0), ("uni0357", 0, -168, 178)]),  # raised over the capital
    ("i\u032F", [("i", 258, 0, 0), ("uni032F", 0, -127, 0)]),
    ("I\u032F", [("I", 339, 0, 0), ("uni032F", 0, -169, 0)]),
    (  # a sign, a space and a transliterated word on one line
        "\U00013000 \uA725n\u1E2B",
        [("u13000", 898, 0, 0), ("space", 244, 0, 0), ("uniA725", 401, 0, 0),
         ("n", 618, 0, 0), ("uni1E2B", 618, 0, 0)],
    ),
]

ttfont = TTFont(FONT)
cmap = ttfont.getBestCmap()
glyph_order = ttfont.getGlyphOrder()
hbfont = hb.Font(hb.Face(FONT.read_bytes()))
failures = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def shape(text):
    """Shape text; return [(glyph name, advance, x offset, y offset)]."""
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(hbfont, buffer)
    return [
        (glyph_order[info.codepoint], pos.x_advance, pos.x_offset, pos.y_offset)
        for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions)
    ]


def outline(name):
    pen = DecomposingRecordingPen(ttfont.getGlyphSet())
    ttfont.getGlyphSet()[name].draw(pen)
    return pen.value


def test_cmap():
    wanted = [*unicodes_per_glyphset("GF_Latin_Core"), *TRANSLITERATION, *CONTROLS]
    for codepoint in wanted:
        check(codepoint in cmap, f"U+{codepoint:04X} is not in cmap")


def test_lone_signs():
    """A sign on its own is the source glyph with the source advance."""
    source = {u: glyph for glyph in ufoLib2.Font.open(SOURCE) for u in glyph.unicodes}
    for codepoint in SIGNS:
        if codepoint not in source:
            continue
        expected = [(source[codepoint].name, source[codepoint].width, 0, 0)]
        shaped = shape(chr(codepoint))
        check(shaped == expected, f"U+{codepoint:05X}: {shaped}, expected {expected}")
    check(sum(u in source for u in SIGNS) == 1078, "the source should have 1,078 signs")


def test_controls():
    """A control on its own shows the fallback outline and takes up space."""
    box = outline(FALLBACK)
    advance = ttfont["hmtx"][FALLBACK][0]
    check(box and advance > 0, "the fallback glyph is empty")
    for codepoint in CONTROLS:
        expected = [(f"u{codepoint:05X}", advance, 0, 0)]
        shaped = shape(chr(codepoint))
        check(shaped == expected, f"U+{codepoint:05X}: {shaped}, expected {expected}")
        check(outline(shaped[0][0]) == box, f"U+{codepoint:05X} does not show the fallback")


def test_golden():
    """Marks land where expected, and signs and Latin share a line."""
    for text, expected in GOLDEN:
        label = " ".join(f"U+{ord(c):04X}" for c in text)
        shaped = shape(text)
        check(shaped == expected, f"{label}: {shaped}, expected {expected}")


for test in (test_cmap, test_lone_signs, test_controls, test_golden):
    try:
        test()
    except Exception as error:  # for example a glyph that is not in the font
        check(False, f"{test.__name__} stopped: {error!r}")
for failure in failures:
    print("FAIL", failure)
print(f"shaping test: {checks} checks, {len(failures)} failed ({FONT.name})")
sys.exit(1 if failures else 0)
