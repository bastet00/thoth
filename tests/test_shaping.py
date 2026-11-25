"""Shaping test for the built font, run by "make test".

    python3 tests/test_shaping.py [FONT.ttf]

Shapes text with HarfBuzz and compares the result with what the font must
do: for hieroglyphs, the reference layout (scripts/stack/layout.py), glyph
by glyph; for the transliteration letters, golden lines. Exits with status
1 if any expectation fails. Other scripts can import Shaper.compare().

What "the same" means (the rounding contract of layout.py): the same glyphs
(sign and level, or lone sign, or control box) in the same order, the same
advance per cluster, and the same position to the unit. A variant is drawn
from the centre of the bottom of its cell: its outline sits at
layout.sign_offset() from the glyph's position, which the generator bakes
into the variant, and its ink may differ from layout.ink_box() by 2 units.
Markers (empty, zero-width glyphs that carry the state of a group) are not
drawn and are not compared, only checked to be empty and zero-width.

Clusters: every glyph of a stacked group has the cluster of the group's
first character, so that a text engine treats the group as one character;
every other sign and control has its own (the cluster of its character).
The tracking check adds space at every cluster boundary, as a text engine
does for letter spacing, and requires that the signs of a group do not
move against each other.
"""

import random
import re
import sys
import unicodedata
from pathlib import Path

import ufoLib2
import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from glyphsets import unicodes_per_glyphset

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "stack"))
sys.dont_write_bytecode = True  # a cache in scripts/stack would make "make" rebuild the font

import glyphs  # noqa: E402  (the generator: which glyphs it adds)
import layout as L  # noqa: E402

SOURCE = ufoLib2.Font.open(ROOT / "sources/Thoth-Regular.ufo")
SIGNS = L.sign_table(SOURCE)
NAMES = glyphs.Names(SIGNS, SOURCE)
V, H = L.VERTICAL_JOINER, L.HORIZONTAL_JOINER
FALLBACK = "control.fallback"

# Limits for the budget test, set from the build with widths in half units
# (12,398 glyphs, 1,083,928 bytes TTF, 392,760 bytes WOFF2) with a little room.
MAX_GLYPHS, MAX_TTF, MAX_WOFF2 = 12_600, 1_110_000, 405_000

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
    ("h\u034f\u0331", [("h", 618, 0, 0), ("space", 0, 0, 0), ("uni0331", 0, -308, 0)]),
    ("h\u0331", [("uni1E96", 618, 0, 0)]),  # composed to the precomposed ẖ
    ("i\u0357", [("dotlessi", 258, 0, 0), ("uni0357", 0, -128, 0)]),  # i loses its dot
    ("ı\u0357", [("dotlessi", 258, 0, 0), ("uni0357", 0, -128, 0)]),
    ("I\u0357", [("I", 339, 0, 0), ("uni0357", 0, -168, 178)]),  # raised over the capital
    ("i\u032f", [("i", 258, 0, 0), ("uni032F", 0, -127, 0)]),
    ("I\u032f", [("I", 339, 0, 0), ("uni032F", 0, -169, 0)]),
    (  # a sign, a space and a transliterated word on one line
        "\U00013000 ꜥnḫ",
        [("u13000", 898, 0, 0), ("space", 244, 0, 0), ("uniA725", 401, 0, 0),
         ("n", 618, 0, 0), ("uni1E2B", 618, 0, 0)],
    ),
]


def gardiner(code):
    """The code point of a Gardiner code: "D21" -> U+1308B."""
    letters, number, suffix = re.fullmatch(r"([A-Z][a-z]?)(\d+)([A-Za-z]?)", code).groups()
    return ord(unicodedata.lookup(f"EGYPTIAN HIEROGLYPH {letters.upper()}{int(number):03d}{suffix.upper()}"))


def encode(mdc):
    """Text from a little Manuel de Codage: codes, ":" and "*" as joiners,
    "-" between groups, <hex> for any code point, "quoted" for letters."""
    out = []
    for token in re.findall(r'"[^"]*"|<[0-9A-F]+>|[A-Z][a-z]?\d+[A-Za-z]?|[:*-]', mdc):
        if token[0] == '"':
            out += map(ord, token[1:-1])
        elif token[0] == "<":
            out.append(int(token[1:-1], 16))
        elif token in ":*":
            out.append(V if token == ":" else H)
        elif token != "-":
            out.append(gardiner(token))
    return out


def group(rows):
    """Text for a group given as rows of code points."""
    text = []
    for row in rows:
        text += [V] * bool(text)
        for member in row:
            text += [H] * bool(text and text[-1] != V) + [member]
    return text


def label(codepoints):
    return " ".join(f"{c:04X}" for c in codepoints)


def script_runs(codepoints):
    """Cut text where its script changes, as a text engine does before it
    shapes: [(start, end)]. Spaces, marks and other characters of no script
    stay with the run they follow."""
    def kind(c):
        if 0x13000 <= c <= 0x1345F:
            return "egyp"
        return None if unicodedata.category(chr(c))[0] in "ZPCMS" else "other"
    runs, current = [], None
    for index, codepoint in enumerate(codepoints):
        k = kind(codepoint)
        if not runs or (k and current and k != current):
            runs.append([index, index + 1])
        else:
            runs[-1][1] = index + 1
        current = k or current
    return [tuple(run) for run in runs]


class Shaper:
    def __init__(self, path):
        self.path = Path(path)
        self.font = TTFont(self.path)
        self.order = self.font.getGlyphOrder()
        self.hb = hb.Font(hb.Face(self.path.read_bytes()))
        self.lone = {sign.name: c for c, sign in SIGNS.items()}
        self.variants = {NAMES.variant(c, k): (c, k) for c in SIGNS for k in glyphs.LEVELS}
        self.boxes = {glyphs.control_name(c): c for c in glyphs.CONTROLS}

    def shape(self, codepoints, level=hb.BufferClusterLevel.MONOTONE_CHARACTERS, tracking=0):
        """[(glyph, cluster, x, y, advance)], x from the start of the line;
        each script run shaped on its own, clusters as code point indices.
        level: HarfBuzz's cluster level (MONOTONE_CHARACTERS keeps every
        character its own cluster unless the font merges them; the default
        of HarfBuzz and of most text engines, MONOTONE_GRAPHEMES, also puts
        a combining mark into the cluster of its base). tracking: space
        added after every cluster, as letter spacing does."""
        out, pen = [], 0
        for start, end in script_runs(codepoints):
            buffer = hb.Buffer()
            buffer.add_codepoints(codepoints[start:end])
            buffer.guess_segment_properties()
            buffer.cluster_level = level
            hb.shape(self.hb, buffer)
            infos = buffer.glyph_infos
            for i, (info, pos) in enumerate(zip(infos, buffer.glyph_positions)):
                out.append((self.order[info.codepoint], start + info.cluster,
                            pen + pos.x_offset, pos.y_offset, pos.x_advance))
                pen += pos.x_advance
                if i + 1 == len(infos) or infos[i + 1].cluster != info.cluster:
                    pen += tracking
        return out

    def drawn(self, name):
        """(code point, level) of a glyph that draws a sign or a control:
        level None for a lone sign or a box; None for anything else."""
        if name in self.lone:
            return self.lone[name], None
        if name in self.variants:
            return self.variants[name]
        if name in self.boxes:
            return self.boxes[name], None
        return None

    def compare(self, codepoints):
        """What differs between the font and the reference: [] if nothing."""
        shaped = self.shape(codepoints)
        problems = []
        if 0x25CC not in codepoints and any(g[0] == NAMES.dotted_circle for g in shaped):
            problems.append("a dotted circle appeared")
        clusters = L.layout(codepoints, SIGNS)
        covered = {i for c in clusters for i in range(c.start, c.end)}
        for name, cluster, *_ in shaped:
            if self.drawn(name) and cluster not in covered:
                problems.append(f"{name} drawn outside any cluster of the reference")
        for c in clusters:
            mine = [i for i, g in enumerate(shaped) if c.start <= g[1] < c.end]
            if not mine:
                problems.append(f"cluster at {c.start} missing")
                continue
            pen = sum(g[4] for g in shaped[:mine[0]])  # where the cluster starts
            advance = sum(shaped[i][4] for i in mine)
            if advance != c.advance:
                problems.append(f"cluster at {c.start}: advance {advance}, reference {c.advance}")
            seen = [(self.drawn(shaped[i][0]), shaped[i][2] - pen, shaped[i][3], shaped[i][4])
                    for i in mine if self.drawn(shaped[i][0])]
            for i in mine:
                name, _, _, _, glyph_advance = shaped[i]
                if not self.drawn(name) and not name.startswith("Q.") and glyph_advance:
                    problems.append(f"{name} has an advance")
            if len(seen) != len(c.glyphs):
                problems.append(f"cluster at {c.start}: {len(seen)} glyphs drawn, reference {len(c.glyphs)}")
                continue
            problems += self.clusters(c, [shaped[i][1] for i in mine])
            for ((codepoint, level), x, y, glyph_advance), glyph in zip(seen, c.glyphs):
                if codepoint != glyph.codepoint or (level if c.stacked else None) != level:
                    problems.append(f"U+{codepoint:X} at level {level}, reference U+{glyph.codepoint:X}"
                                    f" at {glyph.level if c.stacked else 'none (lone)'}")
                    continue
                if c.stacked:
                    dx, dy = L.sign_offset(SIGNS[codepoint], level)  # baked into the variant
                    expected = (glyph.x - dx, glyph.y - dy)
                else:  # the lift is baked into the lone glyph
                    expected = (glyph.x, glyph.y - (SIGNS[codepoint].lift if codepoint in SIGNS else 0))
                if (x, y) != expected:
                    problems.append(f"U+{codepoint:X} at {(x, y)}, reference {expected}")
                if not c.stacked and glyph_advance == 0:
                    problems.append(f"U+{codepoint:X} has no advance")
        problems += self.tracking(codepoints, clusters)
        return problems

    @staticmethod
    def clusters(c, found):
        """A group is one cluster, the cluster of its first character; any
        other sign or control is the cluster of its own character."""
        if set(found) != {c.start}:
            kind = "group" if c.stacked else "character"
            return [f"{kind} at {c.start}: clusters {sorted(set(found))}, expected {c.start}"]
        return []

    def tracking(self, codepoints, clusters, space=60):
        """Letter spacing (`space` after each cluster) moves whole groups:
        the signs of a group keep their places against each other. At
        HarfBuzz's default cluster level and at the one Skia (Flutter) uses."""
        problems = []
        for level in (hb.BufferClusterLevel.MONOTONE_GRAPHEMES, hb.BufferClusterLevel.MONOTONE_CHARACTERS):
            plain, spaced = (self.shape(codepoints, level, tracking) for tracking in (0, space))
            for c in clusters:
                if not c.stacked:
                    continue
                mine = [i for i, g in enumerate(plain) if c.start <= g[1] < c.end]
                if len({plain[i][1] for i in mine}) != 1:
                    problems.append(f"group at {c.start}: more than one cluster at {level.name}")
                places = [[(line[i][2] - line[mine[0]][2], line[i][3]) for i in mine]
                          for line in (plain, spaced)]
                if places[0] != places[1]:
                    problems.append(f"group at {c.start}: letter spacing moves its signs at {level.name}")
        return problems


failures = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def compare_all(shaper, texts, known=()):
    """Compare each text; returns (compared, failed). A text listed in
    known may fail without failing the test, and must still fail."""
    failed = 0
    for text in texts:
        problems = shaper.compare(text)
        failed += bool(problems)
        if label(text) in known:
            check(problems, f"{label(text)} is a known failure but passes: remove it")
        else:
            check(not problems, f"{label(text)}: {problems[:3]}")
    return len(texts), failed


def outline(shaper, name):
    pen = DecomposingRecordingPen(shaper.font.getGlyphSet())
    shaper.font.getGlyphSet()[name].draw(pen)
    return pen.value


def bounds(shaper, name):
    pen = BoundsPen(shaper.font.getGlyphSet())
    shaper.font.getGlyphSet()[name].draw(pen)
    return pen.bounds


def shape_simple(shaper, text):
    """Golden-line form: [(glyph, advance, x offset, y offset)]."""
    out, previous = [], 0
    for name, _, x, y, advance in shaper.shape([ord(c) for c in text]):
        out.append((name, advance, x - previous, y))
        previous += advance
    return out


# --- the tests --------------------------------------------------------------

def test_cmap(shaper):
    cmap = shaper.font.getBestCmap()
    wanted = [*unicodes_per_glyphset("GF_Latin_Core"), *TRANSLITERATION, *glyphs.CONTROLS]
    for codepoint in wanted:
        check(codepoint in cmap, f"U+{codepoint:04X} is not in cmap")


def test_lone_signs(shaper):
    """A sign on its own: the source glyph, its advance, and (rule 1) a low
    sign moved up by its lift, nothing else (its ink box, within the 2 units
    that the build's overlap removal may change it by)."""
    lifted = 0
    for codepoint, sign in SIGNS.items():
        shaped = shaper.shape([codepoint])
        check([g[0] for g in shaped] == [sign.name] and shaped[0][2:] == (0, 0, sign.advance),
              f"U+{codepoint:05X}: {shaped}")
        box = bounds(shaper, sign.name)
        if box and codepoint not in L.BLANK_BOX:
            expected = (sign.box[0], sign.box[1] + sign.lift, sign.box[2], sign.box[3] + sign.lift)
            check(all(abs(a - b) <= 2 for a, b in zip(box, expected)),
                  f"U+{codepoint:05X}: ink {box}, expected {expected}")
            lifted += bool(sign.lift)
    check(len(SIGNS) == 1078 and lifted == 185, f"{len(SIGNS)} signs, {lifted} lifted")


def test_controls(shaper):
    """A control on its own shows the fallback outline and takes up space."""
    box = outline(shaper, FALLBACK)
    advance = shaper.font["hmtx"][FALLBACK][0]
    check(box and advance == L.CONTROL_ADVANCE, "the fallback glyph is wrong")
    for codepoint in glyphs.CONTROLS:
        expected = [(glyphs.control_name(codepoint), 0, 0, advance)]
        shaped = [(g[0], g[2], g[3], g[4]) for g in shaper.shape([codepoint])]
        check(shaped == expected, f"U+{codepoint:05X}: {shaped}, expected {expected}")
        check(outline(shaper, shaped[0][0]) == box, f"U+{codepoint:05X} does not show the fallback")


def test_glyphs(shaper):
    """Variants are one scaled component of their sign, in the place the
    reference gives (2 units for the outline's own rounding); markers are
    empty and zero-width; only group heads have an advance."""
    glyf, hmtx = shaper.font["glyf"], shaper.font["hmtx"]
    worst = 0
    for name, (codepoint, level) in shaper.variants.items():
        sign = SIGNS[codepoint]
        check(hmtx[name][0] == 0, f"{name} has an advance")
        if codepoint in L.BLANK_BOX:
            check(not outline(shaper, name), f"{name}: a blank draws something")
            continue
        (component,) = glyf[name].components
        transform = getattr(component, "transform", [[1, 0], [0, 1]])
        scale = transform[0][0]
        check(component.glyphName == sign.name and abs(scale - sign.scales[level]) < 1 / 16384
              and transform[1][1] == scale and not transform[0][1] and not transform[1][0],
              f"{name}: component {component.glyphName} at {transform}")
        dx, dy = L.sign_offset(sign, level)
        expected = (scale * sign.box[0] + dx, scale * sign.box[1] + dy,
                    scale * sign.box[2] + dx, scale * sign.box[3] + dy)
        found = bounds(shaper, name)
        worst = max(worst, *(abs(a - b) for a, b in zip(found, expected)))
    check(worst <= 2, f"a variant's ink is {worst:.2f} units from the reference")
    markers = [*NAMES.markers(), *(n for k in glyphs.LEVELS for n in NAMES.leveled(k)
                                   if n not in shaper.variants)]
    check(all(hmtx[m][0] == 0 and not outline(shaper, m) for m in markers), "a marker draws or advances")
    heads = NAMES.heads()
    check(all(not outline(shaper, h) for h in heads), "a group head draws something")
    print(f"  {len(shaper.variants)} variants (ink at most {worst:.2f} units off), "
          f"{len(markers)} markers, {len(heads)} heads")


def test_golden(shaper):
    """Marks land where expected, and signs and Latin share a line."""
    for text, expected in GOLDEN:
        label_ = " ".join(f"U+{ord(c):04X}" for c in text)
        shaped = shape_simple(shaper, text)
        check(shaped == expected, f"{label_}: {shaped}, expected {expected}")


# The owner's words and a few figures of the Unicode chapter, as golden
# lines of the font: the glyphs that draw, (glyph, x, y) from the start of
# the line, and the line's advance. Written here, not read from the font
# or from layout.py, so that font and reference cannot drift together.
WORDS = {
    "F35-I9:D21": (1683, [("u13124", 0, 0), ("_0.u13191", 1021, 554), ("_0.u1308B", 1021, 76)]),
    "R4:X1*Q3": (1324, [("_0.u132B5", 662, 509), ("_0.u133CF", 324, 31), ("_0.u132AA", 1112, 31)]),
    "D4:X1*Z1": (1234, [("_0.u13079", 617, 577), ("_0.u133CF", 324, 53), ("_0.u133E4", 1112, 53)]),
    "Q3*X1:N1": (1324, [("_0.u132AA", 212, 577), ("_0.u133CF", 999, 577), ("_0.u131EF", 662, 53)]),
    "N16:Z1*N23": (1324, [("_0.u131FE", 662, 577), ("_0.u133E4", 122, 53), ("_0.u13207", 954, 53)]),
    "D21:N35": (1234, [("_0.u1308B", 617, 599), ("_0.u13216", 617, 121)]),
    "S34-N35:Aa1": (1791, [("u132F9", 0, 0), ("_0.u13216", 1174, 757), ("_0.u1340D", 1174, 53)]),
    "<132B9><131CB><133CF>": (1562, [("u132B9", 0, 0), ("u131CB", 587, 0), ("u133CF", 929, 0)]),
    "A1:O1": (820, [("_4.u13000", 410, 432), ("_4.u13250", 410, 0)]),  # figure 11-1
    "W24*Z7": (1009, [("_0.u133CC", 257, 0), ("_0.u133F2", 729, 0)]),  # figure 11-1
}


def test_words(shaper):
    for mdc, expected in WORDS.items():
        text = encode(mdc)
        shaped = shaper.shape(text)
        found = (sum(g[4] for g in shaped), [(g[0], g[2], g[3]) for g in shaped if shaper.drawn(g[0])])
        check(found == expected, f"{mdc}: {found}, expected {expected}")
        check(not shaper.compare(text), f"{mdc}: {shaper.compare(text)[:3]}")


def random_groups():
    """Seeded random groups: at least 60 at each level and 60 over the caps,
    and at least 600 in all; plus groups exactly at the caps."""
    rng = random.Random(11)
    codepoints = sorted(SIGNS)
    tall = [c for c in codepoints if SIGNS[c].cell[1] >= 10]
    a1, z16 = gardiner("A1"), gardiner("Z16")
    f35, q3 = gardiner("F35"), gardiner("Q3")
    texts = [  # at the caps and one over (64 half units wide, 36 units high)
        group([[a1, a1, a1, f35]]), group([[a1, a1, a1, q3]]),
        group([[a1], [a1], [a1]]), group([[a1], [a1], [a1], [z16]]),
        group([[a1, a1, a1, f35], [a1], [a1]]), group([[a1, a1, a1, f35], [a1], [a1], [z16]]),
    ]
    by_level = {}
    while len(texts) < 600 or min(by_level.get(k, 0) for k in [*glyphs.LEVELS, None]) < 60:
        pool = tall if rng.random() < 0.3 else codepoints
        rows = [[rng.choice(pool) for _ in range(rng.choice((1, 1, 2, 2, 3, 4)))]
                for _ in range(rng.choice((1, 2, 2, 3, 4, 5)))]
        text = group(rows)
        if len(text) == 1:
            continue
        level = L.fit_level(*L.measure(L.parse(text), SIGNS)[:2])
        if by_level.get(level, 0) >= 150 and len(texts) >= 600:
            continue  # enough of this level
        by_level[level] = by_level.get(level, 0) + 1
        texts.append(text)
    return texts, by_level


# Cases where the font differs from the reference, each with its reason.
# Every case is compared; one listed here must still fail.
KNOWN_FAILURES = {}


def test_groups(shaper):
    texts, by_level = random_groups()
    compared, failed = compare_all(shaper, texts, KNOWN_FAILURES)
    levels = ", ".join(f"{'over the caps' if k is None else f'level {k}'}: {n}"
                       for k, n in sorted(by_level.items(), key=lambda x: (x[0] is None, x[0] or 0)))
    print(f"  groups: {compared} compared with the reference, {failed} differ, "
          f"{len(KNOWN_FAILURES)} known failures ({levels}; plus 6 at the caps)")


# Malformed text (layout rule 9, ruling 14 of decision 001): every sign at
# its lone advance, every control a box; a good group next to a bad run
# stays a group.
MALFORMED = [
    ":", ":N35", "*A1-A1", "X1:N35:", "X1::N35", "X1::N35-A1", "X1:*N35", 'X1:" "N35', 'X1"\u200d":N35',
    '":"A1:N35', '"*"', '<13437>X1:N35', "X1:N35<13438>", "<13437>X1:N35<13438>",
    "M17*<13437>X1:N35:A1", "X1<13436>O1-N35", "A1<13432>O1-X1", "A1<13440>",
    "I9:N35:<13113><13433>A1", "".join(f"<{c:X}>" for c in glyphs.CONTROLS),
    "A1:A1:A1:A1", "N35*N35*N35", "D58:D58:D58:D58:N35",  # over the caps
    '"a":X1', 'X1:"a"', 'X1"\u0331":N35', 'X1:N35"\u0331"', '":"', "X1*",
    # default ignorables and the dotted circle: HarfBuzz skips the former in
    # contexts, and its USE shaper puts a dotted circle before a ZWNJ
    'X1"\u200c":N35', 'X1:"\u200c"N35', '":\u200c"X1:N35', 'X1"\u2060":N35', 'X1:"\ufe00"N35',
    'X1:N35"\u200d":A1', '"\u200c"A1', 'A1"\u034f":N35', 'X1:N35"\u200d"*A1',
]


def test_malformed(shaper):
    texts = [encode(mdc) for mdc in MALFORMED]
    rng = random.Random(3)
    codepoints = sorted(SIGNS)
    for _ in range(1500):  # any mixture of signs, joiners and other characters
        text = []
        for _ in range(rng.randint(1, 9)):
            kind = rng.random()
            if kind < 0.55:
                text.append(rng.choice(codepoints))
            elif kind < 0.93:
                text.append(rng.choice((V, H)))
            else:
                text.append(rng.choice((0x13432, 0x13436, 0x13437, 0x13438, 0x20, 0x200C, 0x200D)))
        texts.append(text)
    compared, failed = compare_all(shaper, texts)
    print(f"  malformed and mixed controls: {compared} compared, {failed} differ")


# Groups among other text: lone signs, spaces, transliteration with marks.
MIXED = [
    'R4:X1*Q3" ḥtp "F35-I9:D21" nfr"', '"ꜥnḫ "S34-N35:Aa1"."',
    'D21:N35"(rn) "A1"; "N35*N35*N35" (mw)"', '"I\u0357 h\u0331 "D4:X1*Z1" jr.t"',
    'Q3*X1:N1"⸢"N16:Z1*N23"⸣"', 'X1:N35" "X1:N35"  "X1"-"N35',
    '"Ꜣ"A1:O1"\u032e "W24*Z7"⸗"', '"word "<132B9><131CB><133CF>" word"',
]


def test_mixed(shaper):
    texts = [encode(mdc) for mdc in MIXED]
    compared, failed = compare_all(shaper, texts)
    # the letters of a mixed line come out as they do on their own
    for text in texts:
        line = shaper.shape(text)
        for start, end in script_runs(text):
            if not 0x13000 <= text[start] <= 0x1345F:
                alone = [(g[0], g[4]) for g in shaper.shape(text[start:end])]
                check([(g[0], g[4]) for g in line if start <= g[1] < end] == alone,
                      f"{label(text)}: the letters change next to hieroglyphs")
    print(f"  mixed lines: {compared} compared, {failed} differ")


def glyphs_of(lookup, names):
    """Every glyph name a lookup refers to (coverages, classes, outputs)."""
    found = set()

    def walk(value):
        if isinstance(value, str):
            found.update({value} & names)
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                walk(item)
        elif hasattr(value, "__dict__"):
            for item in vars(value).values():
                walk(item)

    walk(lookup)
    return found


def test_lookups(shaper):
    """The stacking lookups are registered for DFLT and egyp only and touch
    no Latin glyph; no lookup of the Latin letters touches a sign, a control
    or a glyph of the generator; mark and mkmk lookups are one or the other."""
    font = shaper.font
    egyptian = {*shaper.lone, *shaper.boxes, *shaper.variants, FALLBACK, *NAMES.joined.values(),
                *NAMES.heads(), *NAMES.markers(), *(n for k in glyphs.LEVELS for n in NAMES.leveled(k))}
    shared = {".notdef", "space", NAMES.dotted_circle, NAMES.zwnj, *NAMES.ignorables}
    names = set(shaper.order)
    for tag in ("GSUB", "GPOS"):
        table = font[tag]
        records = table.table.FeatureList.FeatureRecord
        scripts = {s.ScriptTag: s.Script for s in table.table.ScriptList.ScriptRecord}
        check({"DFLT", "egyp"} <= set(scripts), f"{tag}: egyp or DFLT is not declared")
        stacking = {"rlig"} if tag == "GSUB" else set()
        for script_tag, script in scripts.items():
            tags = {records[i].FeatureTag for i in script.DefaultLangSys.FeatureIndex}
            check(script_tag in ("DFLT", "egyp") or not tags & {"rlig"},
                  f"{tag}: rlig is registered for {script_tag}")
        for record in records:
            for index in record.Feature.LookupListIndex:
                used = glyphs_of(table.table.LookupList.Lookup[index], names) - shared
                is_egyptian, is_latin = bool(used & egyptian), bool(used - egyptian)
                if record.FeatureTag in stacking:
                    check(not is_latin, f"{tag} {record.FeatureTag} lookup {index} touches Latin")
                elif record.FeatureTag in ("mark", "mkmk"):
                    check(not (is_egyptian and is_latin), f"{tag} lookup {index} mixes signs and Latin")
                else:
                    check(not is_egyptian, f"{tag} {record.FeatureTag} lookup {index} touches signs")
        print(f"  {tag}: {len(table.table.LookupList.Lookup)} lookups")


def test_budget(shaper):
    glyph_count = len(shaper.order)
    size = shaper.path.stat().st_size
    woff2 = shaper.path.parent.parent / "webfonts" / (shaper.path.stem + ".woff2")
    check(glyph_count <= MAX_GLYPHS, f"{glyph_count} glyphs, the budget is {MAX_GLYPHS}")
    check(size <= MAX_TTF, f"the TTF has {size} bytes, the budget is {MAX_TTF}")
    if woff2.exists():
        check(woff2.stat().st_size <= MAX_WOFF2, f"the WOFF2 has {woff2.stat().st_size} bytes")
    print(f"  {glyph_count} glyphs, TTF {size} bytes"
          + (f", WOFF2 {woff2.stat().st_size} bytes" if woff2.exists() else ""))


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fonts/ttf/Thoth-Regular.ttf"
    shaper = Shaper(path)
    tests = (test_cmap, test_lone_signs, test_controls, test_glyphs, test_golden, test_words,
             test_groups, test_malformed, test_mixed, test_lookups, test_budget)
    for test in tests:
        try:
            test(shaper)
        except Exception as error:  # a test that stops is a failure, not a pass
            check(False, f"{test.__name__} stopped: {error!r}")
    for failure in failures[:40]:
        print("FAIL", failure)
    print(f"shaping test: {checks} checks, {len(failures)} failed ({path.name})")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
