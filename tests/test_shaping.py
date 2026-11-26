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
TABLE = L.automatic_table()  # the automatic layer (feature calt), on by default
AUTOMATIC = glyphs.Automatic(TABLE)
AUTOMATIC_MARKS = set(AUTOMATIC.markers())
NAMES = glyphs.Names(SIGNS, SOURCE)
NESTING, SIDES = glyphs.Nesting(SIGNS), glyphs.SideInserts(SIGNS)  # layout sections 8 and 9
ENCLOSURES = glyphs.Enclosures(SIGNS, L.ring_table(SOURCE, SIGNS))  # layout section 10
V, H = L.VERTICAL_JOINER, L.HORIZONTAL_JOINER
FALLBACK = "control.fallback"

# Limits for the budget test, set from the build with every control (20,099
# glyphs, 1,903,636 bytes TTF, 589,584 to 590,480 bytes WOFF2, which vary
# with the build time) with a little room. Its
# parts, each built alone on the base (d0898e3: 12,604 glyphs, 1,215,364
# bytes TTF, 435,736 bytes WOFF2): enclosures (section 10) +264 glyphs and
# about 70 KB TTF, sign modifiers (section 11) +5,057 and about 333 KB,
# segments, overlay and side insertion (sections 8 and 9) +2,174 and about
# 268 KB. Before them: without the shape rule 12,602, 1,213,596 and 434,888;
# without the automatic layer 12,594, 1,184,664 and 427,992; without corner
# insertion 12,398, 1,083,928 and 392,620.
MAX_GLYPHS, MAX_TTF, MAX_WOFF2 = 20_300, 1_950_000, 610_000

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


def enclosure_parts():
    """Every layout.Frame part an enclosure can draw (layout section 10)."""
    parts = [("piece", d) for d in (*L.OPENINGS, *L.CLOSINGS)]
    parts += [("line", k, m, s) for k in ENCLOSURES.kinds for m in L.SEGMENTS for s in ("start", "end")]
    return parts + [("merlons", "walled", n) for n in ENCLOSURES.counts]


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
    def __init__(self, path, table=TABLE, features=None):
        """table: what layout.py compares with (None: no automatic layer);
        features: HarfBuzz features, {"calt": False} switches it off."""
        self.table, self.features = table, features
        self.path = Path(path)
        self.font = TTFont(self.path)
        self.order = self.font.getGlyphOrder()
        self.hb = hb.Font(hb.Face(self.path.read_bytes()))
        self.lone = {sign.name: c for c, sign in SIGNS.items()}
        self.variants = {NAMES.variant(c, k): (c, k) for c in SIGNS for k in glyphs.LEVELS}
        self.boxes = {glyphs.control_name(c): c for c in glyphs.CONTROLS}
        self.shrunk = {NAMES.inserts.shrunk(c, k): (c, k) for c, k in NAMES.inserts.shrunk_glyphs}
        # what an enclosure draws (layout.Frame parts) and its spacers, which carry an advance
        self.frames = {ENCLOSURES.frame_name(part): part for part in enclosure_parts()}
        self.spacers = {ENCLOSURES.spacer(cell) for cell in ENCLOSURES.cells}
        # section 11: mirrored signs (drawn as their sign, flipped), the boxes
        # of stray damage modifiers, pieces of shading, the small mirror box
        m = NAMES.modifiers
        self.mirrored = {m.lone(c): (c, None) for c in m.mirrored}
        self.mirrored.update({m.variant(c, k): (c, k) for c in m.mirrored for k in m.levels})
        self.mirrored.update({m.shrunk_glyph(c, k): (c, k) for c, k in m.shrunk})
        self.boxes.update({m.stray(c): c for c in L.DAMAGE})
        self.pieces = {m.piece(q, v, w): L.hatch_code(q, v, w) for q in L.QUADRANTS for v, w in m.sizes}

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
            hb.shape(self.hb, buffer, self.features)
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
        if name in self.shrunk:  # a bird drawn smaller for an insertion
            return self.shrunk[name]
        if name in self.mirrored:
            return self.mirrored[name]
        if name in self.pieces:
            return self.pieces[name], None
        if name == NAMES.modifiers.mirror_box:
            return L.MIRROR, None
        return None

    def compare(self, codepoints):
        """What differs between the font and the reference: [] if nothing."""
        shaped = self.shape(codepoints)
        problems = []
        if 0x25CC not in codepoints and any(g[0] == NAMES.dotted_circle for g in shaped):
            problems.append("a dotted circle appeared")
        clusters = L.layout(codepoints, SIGNS, self.table)
        implied = L.implied_text(codepoints, self.table)
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
            self.drawn_names = [shaped[i][0] for i in mine if self.drawn(shaped[i][0])]
            for i in mine:
                name, _, _, _, glyph_advance = shaped[i]
                if (not self.drawn(name) and not name.startswith("Q.") and glyph_advance
                        and name not in self.frames and name not in self.spacers):
                    problems.append(f"{name} has an advance")
            frame = sorted((self.frames[shaped[i][0]], shaped[i][2] - pen, shaped[i][3])
                           for i in mine if shaped[i][0] in self.frames)
            if frame != sorted(tuple(part) for part in c.frame):
                problems.append(f"cluster at {c.start}: frame {frame}, reference {sorted(c.frame)}")
            if len(seen) != len(c.glyphs):
                problems.append(f"cluster at {c.start}: {len(seen)} glyphs drawn, reference {len(c.glyphs)}")
                continue
            problems += self.clusters(c, [shaped[i][1] for i in mine])
            run = [t for t, o in zip(*implied) if c.start <= o < c.end]  # with the implied controls
            inserted = c.stacked and ((L.is_insertion(run) and L.insertion(*run, SIGNS) is not None)
                                      or (L.is_side_insertion(run) and L.side_insertion(*run, SIGNS) is not None))
            for index, (((codepoint, level), x, y, glyph_advance), glyph) in enumerate(zip(seen, c.glyphs)):
                if L.is_hatch(glyph.codepoint) or (glyph.codepoint == L.MIRROR and glyph.scale == L.MIRROR_BOX):
                    # section 11: a piece of shading or the small mirror box,
                    # drawn from the point it hangs from
                    box = L.mirror_box(0, 0) if glyph.codepoint == L.MIRROR else L.Glyph(0, 0, 0, 0, 1.0)
                    if codepoint != glyph.codepoint or (x, y) != (glyph.x - box.x, glyph.y - box.y):
                        problems.append(f"{codepoint:X} at {(x, y)}, reference {glyph.codepoint:X} at "
                                        f"{(glyph.x - box.x, glyph.y - box.y)}")
                    continue
                if (glyph.scale < 0) != (self.drawn_names[index] in self.mirrored):
                    problems.append(f"U+{codepoint:X}: mirrored {self.drawn_names[index] in self.mirrored}, "
                                    f"reference {glyph.scale < 0}")
                    continue
                # a mirrored glyph is flipped across the middle of its ink (rule M4)
                turn = L._round(-glyph.scale * (SIGNS[codepoint].box[0] + SIGNS[codepoint].box[2])) \
                    if glyph.scale < 0 else 0
                glyph = glyph._replace(x=glyph.x - turn, scale=abs(glyph.scale))
                # the base of an insertion is its lone glyph, or at a level its shrunk glyph
                lone = not c.stacked or (inserted and index == 0 and not glyph.level)
                if codepoint != glyph.codepoint or (None if lone else glyph.level) != level:
                    problems.append(f"U+{codepoint:X} at level {level}, reference U+{glyph.codepoint:X}"
                                    f" at {'none (lone)' if lone else glyph.level}")
                    continue
                if inserted and index == 0 and not lone:  # the shrink is baked into the glyph
                    _, dx, dy = L.shrink(SIGNS[codepoint].box, level)
                    expected = (glyph.x - dx, glyph.y - dy - SIGNS[codepoint].lift)
                elif not lone:
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
        if name in AUTOMATIC_MARKS:  # the empty marks of the automatic layer
            continue
        out.append((name, advance, x - previous, y))
        previous += advance
    return out


# --- the tests --------------------------------------------------------------

def test_cmap(shaper):
    cmap = shaper.font.getBestCmap()
    wanted = [*unicodes_per_glyphset("GF_Latin_Core"), *TRANSLITERATION, *glyphs.CONTROLS, *L.DAMAGE]
    for codepoint in wanted:
        check(codepoint in cmap, f"U+{codepoint:04X} is not in cmap")


def test_lone_signs(shaper):
    """A sign on its own: the source glyph, its advance, and (rule 1) a low
    sign moved up by its lift, nothing else (its ink box, within the 2 units
    that the build's overlap removal may change it by)."""
    lifted = 0
    for codepoint, sign in SIGNS.items():
        shaped = [g for g in shaper.shape([codepoint]) if g[0] not in AUTOMATIC_MARKS]
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
    markers = [*NAMES.markers(), *NAMES.inserts.markers(), *AUTOMATIC.markers(),
               *(n for k in glyphs.LEVELS for n in NAMES.leveled(k) if n not in shaper.variants),
               *NESTING.markers(), NESTING.run_start, NESTING.bad_start, *SIDES.markers()]
    check(all(hmtx[m][0] == 0 and not outline(shaper, m) for m in markers), "a marker draws or advances")
    # a shrunk bird (layout rule I4): one component, its bird scaled and
    # moved as layout.shrink() says, with the bird's advance
    for name, (codepoint, level) in shaper.shrunk.items():
        sign = SIGNS[codepoint]
        (component,) = glyf[name].components
        scale, x, y = L.shrink(sign.box, level)
        transform = getattr(component, "transform", [[1, 0], [0, 1]])
        check(component.glyphName == sign.name and abs(transform[0][0] - scale) < 1 / 16384
              and (component.x, component.y) == (x, L._round(y + sign.lift - scale * sign.lift))
              and hmtx[name][0] == sign.advance, f"{name}: {component.glyphName} at {transform}")
    for name in NAMES.inserts.candidates() + SIDES.candidates():  # a candidate that no rule takes shows the box
        check(outline(shaper, name) == outline(shaper, FALLBACK) and hmtx[name][0] == L.CONTROL_ADVANCE,
              f"{name} is not the fallback box")
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
    "M17*<13437>X1:N35:A1", "X1<13436><13436>O1-N35", "A1<13432>O1-X1", "A1<13440>",
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


# Corner insertion (layout section 6). The owner's words as golden lines of
# the font (written here, not read from the font or from layout.py), then
# every bird with X1 and with Z1 at top end, all four corners on a sample
# of bases, the fallbacks and malformed text, and seeded random insertions
# in random lines, each compared with the reference glyph by glyph, which
# includes one cluster per block and letter spacing (compare()).
TS, BS, TE, BE = 0x13432, 0x13433, 0x13434, 0x13435
INSERT_WORDS = {  # mdc: (advance of the line, [(glyph, x, y)] of the glyphs that draw)
    # mwt: the vulture shrinks to level 1 so that the bread reaches level 2
    "G14<13434>X1-B1": (1732, [("u13150.shrink1", 0, 0), ("_2.u133CF", 781, 798), ("u13050", 1055, 0)]),
    "G43<13434>X1": (860, [("u13171.shrink1", 0, 0), ("_3.u133CF", 631, 769)]),  # quail chick
    "G1<13434>X1": (985, [("u1313F", 0, 0), ("_3.u133CF", 757, 836)]),  # vulture G1
    "G17<13434>X1": (1116, [("u13153", 0, 0), ("_2.u133CF", 842, 751)]),  # owl
    "G39<13434>Z1": (1248, [("u1316D", 0, 0), ("_2.u133E4", 1042, 431)]),  # s3
    "M23-G14<13434>X1-N35-G17-D21-D31": (  # the TLA word, the bread over the vulture's back
        5953, [("u131D3", 0, 0), ("u13150.shrink1", 668, 0), ("_2.u133CF", 1449, 798), ("u13216", 1723, 0),
               ("u13153", 2920, 0), ("u1308B", 4036, 0), ("u13096", 5213, 0)]),
}

INSERT_UNSTACKED = [  # what v1 draws unstacked, the corner control as its box (rule I1)
    "N35:G14<13434>X1", "G14<13434>X1:N35", "A1*G14<13434>X1",  # a base in a joiner group
    "G14<13434>X1*Z1", "G14<13434>X1:Z1",  # an inserted group
    "G14<13434>X1<13433>Z1", "G14<13434>X1<13434>Z1", "G14<13434>Z1<13434>X1",  # a second insertion
    "<13434>X1", "G14<13434>", "<13434>", "G14<13434><13434>X1", "G14<13434><13433>X1",  # malformed
    'G14<13434>"\u200d"X1', 'G14"\u200d"<13434>X1', 'G14<13434>" "X1', 'G14<13434>"\u200c"X1',
    "G14<13434>X1<13436>Z1", "<13437>G14<13434>X1<13438>",  # unsupported controls
]
INSERT_SIDE_BY_SIDE = [  # no room, or too large: the control is a horizontal joiner (rule I6)
    "D21<13434>X1", "G14<13434>A1", "G25<13435>Aa1", "I10<13433>D46", "N35<13432>X1",
]


def test_insertion(shaper):
    texts, outcomes = [], {}

    def add(text):
        texts.append(text)
        run = [c for c in text if L.is_sign(c) or c in L.CONTROLS]
        if len(run) == 3 and L.is_insertion(run):
            found = L.insertion(*run, SIGNS)
            key = "side by side" if found is None else ("shrinks" if found[0] else "fits")
            outcomes[key] = outcomes.get(key, 0) + 1

    birds = [c for c in L.BIRDS if c in SIGNS]
    x1, z1 = gardiner("X1"), gardiner("Z1")
    for bird in birds:
        for sign in (x1, z1):
            add([bird, TE, sign])
    bases = [gardiner(g) for g in ("A1", "D21", "G1", "G17", "G39", "G43", "I10", "N35", "O1",
                                    "M17", "Q3", "F35", "D58", "R4", "W24", "X1", "Aa1")] + [0x13441, 0x13444]
    signs = [gardiner(g) for g in ("X1", "Z1", "Z4", "N35", "Q3", "W24", "N29", "O49", "V31", "D21", "Z2")]
    for base in bases:
        for control in L.CORNERS:
            for sign in signs:
                add([base, control, sign])
    for mdc in INSERT_SIDE_BY_SIDE:
        text = encode(mdc)
        run = [c for c in text if L.is_sign(c)]
        check(L.layout(text, SIGNS) == L.layout([run[0], H, run[1]], SIGNS), f"{mdc}: not side by side")
        add(text)
    for mdc in INSERT_UNSTACKED:
        text = encode(mdc)
        check(not any(c.stacked for c in L.layout(text, SIGNS)), f"{mdc}: stacked")
        add(text)
    rng = random.Random(17)
    codepoints = sorted(SIGNS)
    small = [c for c in codepoints if L.insertable(SIGNS[c])]
    for _ in range(1500):  # any base, corner and sign; mostly signs small enough
        add([rng.choice(codepoints), rng.choice(list(L.CORNERS)), rng.choice(small if rng.random() < 0.8 else codepoints)])
    roomy = sorted({(base, control) for base, _, control, _ in NAMES.inserts.zones})
    for _ in range(1500):  # a base and corner with room for some sign, and a small sign
        add([*rng.choice(roomy), rng.choice(small)])
    for _ in range(300):  # and among other text
        line = []
        for _ in range(rng.randint(1, 4)):
            kind = rng.random()
            if kind < 0.5:
                line += [rng.choice(birds + small), rng.choice(list(L.CORNERS)), rng.choice(small)]
            elif kind < 0.7:
                line += group([[rng.choice(small)], [rng.choice(codepoints)]])
            elif kind < 0.85:
                line.append(rng.choice(codepoints))
            else:
                line += map(ord, rng.choice((" ", " ꜥnḫ ", "\u200d", ".")))
        texts.append(line)
    for mdc, expected in INSERT_WORDS.items():
        text = encode(mdc)
        shaped = shaper.shape(text)
        found = (sum(g[4] for g in shaped), [(g[0], g[2], g[3]) for g in shaped if shaper.drawn(g[0])])
        check(found == expected, f"{mdc}: {found}, expected {expected}")
        texts.append(text)
    compared, failed = compare_all(shaper, texts)
    blocks = sum(1 for text in texts for c in L.layout(text, SIGNS)
                 if L.is_insertion(text[c.start:c.end]) and L.insertion(*text[c.start:c.end], SIGNS))
    print(f"  insertions: {compared} texts compared, {failed} differ; {blocks} inserted blocks, each one cluster; "
          + ", ".join(f"{k}: {v}" for k, v in sorted(outcomes.items())))


def test_automatic(shaper):
    """The automatic layer (layout rules A1 to A9): plain text comes out as
    layout.py lays it out with the table, every entry of the table and
    seeded random plain text, next to spaces, ZWNJ and controls; with calt
    switched off, as layout.py without the table."""
    signs = [c for c in sorted(SIGNS) if c in L.HIEROGLYPHS]
    rng = random.Random(11)
    known = sorted({c for key in TABLE for c in key if c not in (L.START, L.END)})
    entries = [[c for c in key if c not in (L.START, L.END)] for key in sorted(TABLE, key=str)]
    texts = list(entries)  # each entry as a word of its own
    texts += [[rng.choice(known), *e, rng.choice(known)] for e in entries]  # inside a longer stretch
    texts += [[0x20, *e, 0x200C, rng.choice(known)] for e in entries[::5]]  # between a space and ZWNJ
    separators = (0x20, 0x200C, 0x200D, 0x13430, 0x13431, 0x13434, 0x13432)
    for _ in range(2000):  # random plain text, some of it next to controls
        text = []
        for _ in range(rng.randint(2, 14)):
            r = rng.random()
            text.append(rng.choice(known) if r < 0.8 else rng.choice(signs) if r < 0.92
                        else rng.choice(separators))
        texts.append(text)
    for words in range(300):  # running text: entries without spaces
        texts.append([c for _ in range(rng.randint(2, 6)) for c in rng.choice(entries)])
    # the shape rule (A7 to A9): plain text rich in half-block signs, next to
    # lower and tall signs, list words, spaces, ZWNJ and controls
    half = [c for c in signs if L.half_block(c, SIGNS)]
    lower = [c for c in signs if c not in half and SIGNS[c].cell[1] < L.HEIGHT_LIMIT]
    tall = [c for c in signs if SIGNS[c].cell[1] >= L.HEIGHT_LIMIT]
    shape_rng = random.Random(23)
    for _ in range(2000):
        text = []
        for _ in range(shape_rng.randint(2, 12)):
            r = shape_rng.random()
            text.append(shape_rng.choice(half) if r < 0.6 else shape_rng.choice(lower) if r < 0.72
                        else shape_rng.choice(tall) if r < 0.8 else shape_rng.choice(known) if r < 0.9
                        else shape_rng.choice(separators))
        texts.append(text)
    count, failed = compare_all(shaper, texts)
    stacked = sum(c.stacked for text in texts[:len(entries)] for c in L.layout(text, SIGNS, TABLE))
    # golden plain words: the glyphs that draw, as for the same words typed with controls
    golden = (("R4-X1-Q3", "R4:X1*Q3"), ("F35-I9-D21", "F35-I9:D21"), ("D21-N35", "D21:N35"),
              ("S34-N35-Aa1", "S34-N35:Aa1"), ("G14-X1-B1", "G14<13434>X1-B1"),  # mwt: t in the corner
              # the owner's cases (shape rule): bolt over viper, the rest as it is
              ("O34-I9-D19-A2", "O34:I9-D19-A2"), ("O34-I9-Aa1-G43" + "-Z1" * 7, "O34:I9-Aa1-G43" + "-Z1" * 7),
              ("N35-N35", "N35:N35"), ("O34-I9-N37-Y1", "O34:I9-N37:Y1"))
    for plain, explicit in golden:
        found = [(g[0], g[2], g[3]) for g in shaper.shape(encode(plain)) if shaper.drawn(g[0])]
        reference = [(g[0], g[2], g[3]) for g in shaper.shape(encode(explicit)) if shaper.drawn(g[0])]
        check(found == reference and len(found) > len({g[0] for g in found if g[0] in shaper.lone}),
              f"{plain} typed plainly: {found}, typed with controls: {reference}")
    for text in (encode('D21<200C>N35'), encode('D21" "N35'), encode('G14-X1-B1<200C>D21<200C>N35'),
                 encode('O34<200C>I9'), encode('O34" "I9'), encode('A1-O34<200C>I9')):
        drawn = [g[0] for g in shaper.shape(text) if shaper.drawn(g[0])]
        check(all(g in shaper.lone for g in drawn[-2:]), f"{label(text)}: ZWNJ or space joined {drawn}")
    # pairs that do not stack by shape: narrow low, low and tall, tall and
    # wide, a run right after a lower sign
    for plain in ("X1-Z1", "Q3-X1", "D21-A1", "G43-G43", "Q3-N35-D36", "X1-O34-I9-N37"):
        drawn = [g[0] for g in shaper.shape(encode(plain)) if shaper.drawn(g[0])]
        check(len(drawn) == len(encode(plain)) and all(g in shaper.lone for g in drawn), f"{plain}: stacked {drawn}")
    # the feature switched off: no automatic stacking at all
    off = Shaper(shaper.path, table=None, features={"calt": False})
    off_count, off_failed = compare_all(off, texts[:len(entries)] + texts[-2300:])
    print(f"  automatic: {count} texts compared ({len(entries)} table entries alone, {stacked} groups), "
          f"{failed} failed; with calt off {off_count} texts, {off_failed} failed")


# Segments and overlay (layout section 8). Golden lines of the font
# (written here, not read from the font or from layout.py), then malformed
# text, text with the automatic layer around it, and seeded random groups
# rich in these controls, each compared with the reference glyph by glyph.
SB, SE, OV = L.SEGMENT_START, L.SEGMENT_END, L.OVERLAY


def encode_nested(mdc):
    """encode(), and "(" ")" for the segment controls, "##" for the overlay."""
    return encode(mdc.replace("##", "<13436>").replace("(", "<13437>").replace(")", "<13438>"))


NEST_WORDS = {  # mdc: (advance of the line, [(glyph, x, y)] of the glyphs that draw)
    # Ptah: p over t beside the tall h, all at full size
    "(Q3:X1)*V28": (1054, [("_0.u132AA", 324, 554), ("_0.u133CF", 324, 76), ("_0.u1339B", 819, 0)]),
    "G17##D36": (1324, [("_0.u13153", 662, 0), ("_0.u1309D", 662, 270)]),  # arranged like G20
    "M17*(Y5:N35)": (1318, [("_1.u131CB", 165, 0), ("_1.u133E0", 792, 454), ("_1.u13216", 792, 85)]),
    "N35##(Q3:X1)": (1234, [("_0.u13216", 617, 270), ("_0.u132AA", 617, 360), ("_0.u133CF", 617, 0)]),
    "(Q3*X1)##N35": (1234, [("_0.u132AA", 325, 315), ("_0.u133CF", 797, 315), ("_0.u13216", 617, 405)]),
    "A1*G17##D36": (1098, [("_5.u13000", 241, 0), ("_5.u13153", 758, 0), ("_5.u1309D", 758, 135)]),
    "N35:(Q3:X1)*V28": (922, [("_2.u13216", 461, 852), ("_2.u132AA", 246, 438), ("_2.u133CF", 246, 85),
                              ("_2.u1339B", 741, 27)]),
    "(X1*Z1:N35)*A1": (1279, [("_4.u133CF", 207, 316), ("_4.u133E4", 680, 316), ("_4.u13216", 383, 62),
                              ("_4.u13000", 990, 0)]),  # the row of two justified in the box
    "(N35:N35:N35)*A40": (1294, [("_3.u13216", 422, 450), ("_3.u13216", 422, 270), ("_3.u13216", 422, 90),
                                 ("_3.u1302D", 1037, 0)]),
}

NEST_MALFORMED = [
    "(Q3:X1)", "(Q3*X1)*V28", "((Q3:X1):N35)*A1", "(Q3:X1*V28", "Q3:X1)*V28", "()*A1", "(Q3:)*A1",
    "G17##D36##N35", "(G17:D36)##N35", "N35##(Q3*X1)", "##N35", "N35##", "G17####D36",
    "(Q3##X1:N35)*A1" if L.MAX_DEPTH < 2 else "(((Q3:X1)*Z1:N35)*A1:N35)*A1",
    "((Q3:X1)*Z1:N35)*A1" if L.MAX_DEPTH < 2 else "((Q3##X1)*Z1:N35)*A1",
    "(G17:D36)*A1", "(A1*A1*A1:X1)*Z1",  # a box over one quadrat
    '(Q3:"\u200c"X1)*V28', '(Q3:X1)" "*V28', '(Q3:X1)*"\u200d"V28', 'G17"\u200c"##D36', 'N35##" "N35',
    "(Q3:X1)*V28<13432>X1", "(Q3<13434>X1:N35)*A1", "G17##<13440>D36", "(Q3:X1)*<13439>V28",
    # (with the sign modifiers, "G17##D36<13440>" is an overlay with D36 mirrored: test_all_controls)
]


def nested_random(rng, count):
    """Seeded random groups with segments and overlays (some one level
    deeper than the font goes), some broken, some in a line."""
    codepoints = sorted(SIGNS)
    small = [c for c in codepoints if SIGNS[c].cell[1] <= 6]
    narrow = [c for c in small if SIGNS[c].cell[0] <= 14]

    def sign(depth=1):
        r = rng.random()
        return rng.choice(narrow if depth and r < 0.7 else small if r < 0.8 else codepoints)

    def member(depth):
        r = rng.random()
        deeper = (depth < L.MAX_DEPTH or rng.random() < 0.1) and depth <= L.MAX_DEPTH
        if deeper and r < 0.25:
            rows = [row(depth + 1) for _ in range(rng.choice((2, 2, 3)))]
            return [SB] + sum(([V] + x for x in rows[1:]), rows[0]) + [SE]
        if deeper and r < 0.4:
            left = [sign()] if rng.random() < 0.6 else [SB, sign(), H, sign(), SE]
            right = [sign()] if rng.random() < 0.6 else [SB, sign(), V, sign(), SE]
            return left + [OV] + right
        return [sign(depth)]

    def row(depth):
        members = [member(depth) for _ in range(rng.choice((1, 2, 2, 3) if depth else (1, 2, 2)))]
        return sum(([H] + m for m in members[1:]), members[0])

    texts = []
    for _ in range(count):
        rows = [row(0) for _ in range(rng.choice((1, 1, 2)))]
        text = sum(([V] + r for r in rows[1:]), rows[0])
        if rng.random() < 0.35:  # broken: a control or character added or taken away
            for _ in range(rng.choice((1, 1, 2))):
                i = rng.randrange(len(text) + 1)
                r = rng.random()
                if r < 0.3 and len(text) > 1:
                    del text[min(i, len(text) - 1)]
                elif r < 0.6:
                    text.insert(i, rng.choice((SB, SE, OV, V, H, 0x13432, 0x13439, 0x200C, 0x20)))
                else:
                    text.insert(i, sign(0))
        if rng.random() < 0.3:  # in a line, next to plain signs (the automatic layer)
            text = [sign(0)] * rng.choice((0, 1, 2)) + [0x20] * (rng.random() < 0.5) + text + [sign(0)] * rng.choice((0, 1, 2))
        texts.append(text)
    return texts


def test_nesting(shaper):
    for mdc, expected in NEST_WORDS.items():
        text = encode_nested(mdc)
        shaped = shaper.shape(text)
        found = (sum(g[4] for g in shaped), [(g[0], g[2], g[3]) for g in shaped if shaper.drawn(g[0])])
        check(found == expected, f"{mdc}: {found}, expected {expected}")
        check(not shaper.compare(text), f"{mdc}: {shaper.compare(text)[:3]}")
    texts = [encode_nested(mdc) for mdc in NEST_MALFORMED]
    for text in texts:
        check(not any(c.stacked for c in L.layout(text, SIGNS, TABLE)), f"{label(text)}: the reference stacks it")
    rng = random.Random(41)
    texts += nested_random(rng, 3000)
    words = [list(key[1:-1] if key[-1] == L.END else key[1:]) for key in TABLE if key[0] == L.START][:40]
    for word in words:  # a word of the automatic layer right next to a segment
        texts += [word + encode_nested("(Q3:X1)*V28"), encode_nested("(Q3:X1)*V28") + word,
                  word + [H] + encode_nested("G17##D36")]
    stacked = sum(any(c.stacked and any(x in L.NESTING for x in t[c.start:c.end])
                      for c in L.layout(t, SIGNS, TABLE)) for t in texts)
    compared, failed = compare_all(shaper, texts)
    off = Shaper(shaper.path, table=None, features={"calt": False})
    off_compared, off_failed = compare_all(off, texts[::5])
    check(stacked > 400, f"only {stacked} nested groups among the texts")
    print(f"  segments and overlay: {len(NEST_WORDS)} golden lines; {compared} texts compared ({stacked} with a "
          f"stacked box), {failed} differ; with calt off {off_compared} compared, {off_failed} differ")


# Insertion at middle, top and bottom (layout section 9).
SIDE_WORDS = {  # mdc: (advance of the line, [(glyph, x, y)] of the glyphs that draw)
    "O6<13439>R8": (839, [("u13257", 0, 0), ("_5.u132B9", 420, 343)]),  # the house of the god
    "O1<13439>X1": (1377, [("u13250", 0, 0), ("_2.u133CF", 689, 343)]),
    "D28<1343A>Z1": (703, [("u13093", 0, 0), ("_2.u133E4", 352, 135)]),  # between the arms of ka
    "S12<1343B>X1": (1306, [("u132DE", 0, 0), ("_3.u133CF", 653, 14)]),  # under the collar
    "O6<1343A>X1": (1324, [("_0.u13257", 369, 0), ("_0.u133CF", 999, 0)]),  # no opening on top: side by side
}
SIDE_UNSTACKED = [
    "<13439>X1", "O6<13439>", "<13439>", "O6<13439><13439>X1", "O6<13439>X1:N35", "N35:O6<13439>X1",
    "O6<13439>X1<1343A>Z1", 'O6"‍"<13439>X1', 'O6<13439>" "X1', "O6<13439>X1<13436>Z1",
    "<13437>O6<13439>X1:N35<13438>*A1", "O6<13434>X1<13439>Z1",
]
SIDE_BY_SIDE = ["O6<1343A>X1", "A1<13439>X1", "N35<1343B>X1", "O1<1343A>A1", "D28<1343B>Z1"]


def test_side_insertion(shaper):
    for mdc, expected in SIDE_WORDS.items():
        text = encode(mdc)
        shaped = shaper.shape(text)
        found = (sum(g[4] for g in shaped), [(g[0], g[2], g[3]) for g in shaped if shaper.drawn(g[0])])
        check(found == expected, f"{mdc}: {found}, expected {expected}")
    texts = [encode(mdc) for mdc in [*SIDE_WORDS, *SIDE_UNSTACKED, *SIDE_BY_SIDE]]
    for mdc in SIDE_UNSTACKED:
        check(not any(c.stacked for c in L.layout(encode(mdc), SIGNS, TABLE)), f"{mdc}: the reference stacks it")
    for mdc in SIDE_BY_SIDE:
        run = [c for c in encode(mdc) if L.is_sign(c) or c in L.CONTROLS]
        check(L.side_insertion(*run, SIGNS) is None, f"{mdc}: the reference inserts it")
    rng = random.Random(43)
    codepoints = sorted(SIGNS)
    small = [c for c in codepoints if L.insertable(SIGNS[c])]
    inserted = 0
    for _ in range(1500):
        control = rng.choice(L.SIDES)
        having = [c for c in codepoints if SIGNS[c].corners[control][0]["flat"].width]
        run = [rng.choice(having if rng.random() < 0.7 else codepoints), control,
               rng.choice(small if rng.random() < 0.6 else codepoints)]
        inserted += L.side_insertion(*run, SIGNS) is not None
        line = [rng.choice(codepoints)] * (rng.random() < 0.3) + [0x20] * (rng.random() < 0.3) + run
        texts.append(line)
    compared, failed = compare_all(shaper, texts)
    check(inserted > 250, f"only {inserted} random side insertions insert")
    print(f"  side insertions: {len(SIDE_WORDS)} golden lines; {compared} texts compared ({inserted} inserted), "
          f"{failed} differ")


# Enclosures (layout section 10). Text in the little MdC of encode(), with
# the controls written as code points: B and E for the cartouche pair,
# BW and EW for the walled pair.
B, E, BW, EW = "<1343C>", "<1343D>", "<1343E>", "<1343F>"
ROYAL_NAMES = [  # flat and stacked spellings, in cartouches
    f"V11A{B}Aa1-G43-I9-G43{E}V11B",  # Khufu
    f"V11A{B}Aa1:I9-G43-I9-G43{E}V11B",  # Khufu, stacked
    f"V11A{B}N5-M17-Y5:N35-N28:Z2{E}V11B",  # Tutankhamun's throne name, flat
    f"V11A{B}M17-Y5:N35-X1:Z4-S34-S29{E}V11B",  # Tutankhamun, stacked
    f"V11A{B}N5-F12-Z1{E}V11B",  # Neferkare-style short name with r
    f"V11A{B}R4:X1*Q3-I9-N35:Z2{E}V11B",  # with ḥtp inside
    f"V11A{B}N5:C12-M17-Y5:N35{E}V11C",  # with a seated god
    f"V11D{B}M23-X1:N35{E}V11B",  # the knotted opening
    f"V11A{B}G39-N5{E}V11B", f"V11A{B}D21:N35-D21:N35-D21:N35-D21:N35-D21:N35-D21:N35-D21:N35{E}V11B",
    f"V11A{B}G14<13434>X1-B1{E}V11B",  # an insertion inside: the vulture with t in its corner
    f"V11A{B}N5-Z1-C1{E}V11B", f"V11A{B}S29-D21:N35-N35:Aa1{E}V11B",
]
WALLS = [  # the ḥwt and the walled enclosure around one to four groups
    f"O6A{B}R4:X1*Q3{E}O6D", f"O6B{B}A40-N35{E}O6E", f"O6C{B}G43-D21:N35-A1{E}O6F",
    f"O6A{B}X1:N35-M17-D21-A1{E}O6F",
    f"O36C{BW}M17{EW}O36D", f"O36C{BW}D21:N35-Aa1{EW}O36D", f"O36A{BW}O29:O1-X1-Z1{EW}O36B",
    f"O36A{BW}G43-D21:N35-A1-N35:N35{EW}O36B",
]
ENCLOSURE_MALFORMED = [
    f"V11A{B}Aa1-G43", f"{B}Aa1-G43", f"Aa1-G43{E}V11B", f"V11A{E}Aa1{B}V11B",  # begin without end, an end first
    f"V11A{B}{E}V11B", f"V11A-V11B", f"{B}{E}", f"V11A{B}Aa1{EW}V11B",  # empty, signs alone, the other kind
    f'V11A{B}Aa1" "G43{E}V11B', f'V11A{B}Aa1"\u200d"G43{E}V11B', f'V11A{B}"\u200c"Aa1{E}V11B',
    f"V11A{B}N5{B}Aa1{E}G43{E}V11B",  # nested: the inner one forms, the outer one not
    f"V11A{B}X1:N35{E}{E}V11B", f"{B}{B}X1{E}", f"V11A{B}G38<13434>X1{E}V11B",  # too tall for the ring (rule E5)
    f"N35:V11A{B}X1{E}V11B", f"V11A{B}X1:{E}V11B", f"V11A{B}X1::N35{E}V11B",  # joiners at the edges
    f'V11A"\u200d"{B}X1{E}V11B', f'V11A{B}X1{E}"\u200d"V11B',
]
ENCLOSURE_WORDS = {  # golden lines: (advance of the line, glyphs that draw, frame glyphs), (glyph, x, y)
    f"V11A{B}Aa1-G43-I9-G43{E}V11B": (  # Khufu: lone signs as groups of one, lines under each
        5000, [("_0.u1340D", 964, 0), ("_0.u13171", 1748, 0), ("_0.u13191", 2847, 315), ("_0.u13171", 3946, 0)],
        [("u13379.ring", 0, 0), ("_el.p.512.s", 617, 0), ("_el.p.512.e", 1311, 0), ("_el.p.512.s", 1311, 0),
         ("_el.p.512.e", 2185, 0), ("_el.p.1024.s", 2185, 0), ("_el.p.1024.e", 3509, 0), ("_el.p.512.s", 3509, 0),
         ("_el.p.512.e", 4383, 0), ("u1337A.ring", 4383, 0)]),
    f"O36C{BW}D21:N35{EW}O36D": (  # a group in a walled enclosure: eight merlons on each band
        2514, [("_0.u1308B", 1257, 599), ("_0.u13216", 1257, 121)],
        [("u13288.ring", 0, 0), ("_el.w.1024.s", 640, 0), ("_el.w.1024.e", 1874, 0), ("_em.w.8", 1257, 0),
         ("u13289.ring", 1874, 0)]),
    f"V11A{B}G43<13434>X1{E}V11B": (  # an insertion, moved up by 13 so that the chick stands on the line
        2094, [("u13171.shrink1", 617, 13), ("_3.u133CF", 1248, 782)],
        [("u13379.ring", 0, 0), ("_el.p.512.s", 617, 0), ("_el.p.512.e", 1477, 0), ("u1337A.ring", 1477, 0)]),
}


def enclosure_texts():
    """Royal names, walls, malformed text and seeded random enclosures."""
    texts = [encode(m) for m in ROYAL_NAMES + WALLS + ENCLOSURE_MALFORMED]
    texts += [encode(f"V11A{B}" + "-".join(["N5", "D21:N35", "Aa1", "G43"] * 6) + f"{E}V11B")]  # long
    texts += [encode(f"A1-V11A{B}D21-N35-X1-Q3{E}V11B-A1"), encode(f'"ꜥnḫ "V11A{B}X1:N35{E}V11B" ḏt"')]
    rng = random.Random(29)
    codepoints = sorted(SIGNS)
    small = [c for c in codepoints if L.insertable(SIGNS[c])]
    birds = [c for c in L.BIRDS if c in SIGNS]
    for _ in range(600):  # random groups, insertions and plain signs between random delimiters
        text = []
        for _ in range(rng.randint(0, 2)):
            text.append(rng.choice(codepoints))
        kind = rng.random() < 0.7
        if rng.random() < 0.85:
            text.append(rng.choice(L.OPENINGS))
        text.append(0x1343C if kind else 0x1343E)
        for _ in range(rng.randint(1, 6)):
            r = rng.random()
            if r < 0.4:
                text.append(rng.choice(codepoints))
            elif r < 0.7:
                text += group([[rng.choice(codepoints) for _ in range(rng.randint(1, 2))]
                               for _ in range(rng.randint(1, 3))])
            elif r < 0.85:
                text += [rng.choice(birds + small), rng.choice(list(L.CORNERS)), rng.choice(small)]
            else:
                text.append(rng.choice((V, H, 0x13432, 0x13437, 0x20, 0x200D, 0x1343C, 0x1343D, 0x1343F)))
        text.append(0x1343D if kind or rng.random() < 0.1 else 0x1343F)
        if rng.random() < 0.85:
            text.append(rng.choice(L.CLOSINGS))
        texts.append(text)
    return texts


def test_enclosures(shaper):
    """Enclosures (layout rules E1 to E7): the font equals the reference
    glyph by glyph, with the lines and the delimiters of every cluster, for
    royal names, walls, malformed text and random enclosures, with calt on
    and off; the golden lines; the outlines of the lines and pieces."""
    texts = enclosure_texts()
    compared, failed = compare_all(shaper, texts)
    formed = sum(bool(L.enclosures(t)) and any(c.frame for c in L.layout(t, SIGNS, TABLE)) for t in texts)
    off = Shaper(shaper.path, table=None, features={"calt": False})
    off_count, off_failed = compare_all(off, texts[:len(ROYAL_NAMES) + len(WALLS)] + texts[-200:])
    for mdc, expected in ENCLOSURE_WORDS.items():
        shaped = shaper.shape(encode(mdc))
        found = (sum(g[4] for g in shaped), [(g[0], g[2], g[3]) for g in shaped if shaper.drawn(g[0])],
                 [(g[0], g[2], g[3]) for g in shaped if g[0] in shaper.frames])
        check(found == expected, f"{mdc}: {found}, expected {expected}")
    for mdc in ENCLOSURE_MALFORMED:  # no frame, every control a box, every sign drawn
        text = encode(mdc)
        shaped = shaper.shape(text)
        drawn = [shaper.drawn(g[0]) for g in shaped if shaper.drawn(g[0])]
        boxes = [c for c in text if c in L.ENCLOSURE]
        laid = L.layout(text, SIGNS, TABLE)
        formed_here = any(c.frame for c in laid)
        pieces = [f.part[1] for c in laid for f in c.frame if f.part[0] == "piece"]
        signs = [c for c in text if L.is_sign(c)]
        drawn += [(c, None) for c in pieces]
        if not formed_here:
            check([c for c, _ in drawn if c in L.ENCLOSURE] == boxes and all(g[0] not in shaper.frames for g in shaped),
                  f"{mdc}: {[g[0] for g in shaped]}")
        check(sorted(c for c, _ in drawn if L.is_sign(c)) == sorted(signs), f"{mdc}: a sign is missing")
    # the line pieces: the bands of the profile piece, from 0 to their length
    for kind in ENCLOSURES.kinds:
        edges = L.band_edges(kind)
        for length in L.SEGMENTS:
            box = bounds(shaper, ENCLOSURES.line(kind, length, "start"))
            check(box == (0, edges[0], length, edges[7]), f"{kind} line {length}: {box}")
            box = bounds(shaper, ENCLOSURES.line(kind, length, "end"))
            check(box == (-length, edges[0], 0, edges[7]), f"{kind} line {length} (end): {box}")
    for d in (*L.OPENINGS, *L.CLOSINGS):  # a joined delimiter reaches its edge, inside the ring
        name, ring = ENCLOSURES.joined(d), L.default_rings()[d]
        box = bounds(shaper, name)
        check(shaper.font["hmtx"][name][0] == ring.advance and (box[2] == ring.advance if d in L.OPENINGS else box[0] == 0),
              f"{name}: advance {shaper.font['hmtx'][name][0]}, ink {box}")
    print(f"  enclosures: {compared} texts compared, {failed} differ ({formed} with an enclosure); "
          f"with calt off {off_count}, {off_failed} differ")



# --- sign modifiers: mirroring and damage (layout section 11) ----------------
#
# Golden lines of the font (glyphs that draw, (glyph, x, y), and the line's
# advance), written here; then every damage modifier on signs of different
# shapes, alone and in groups, every mirrored sign, modifiers in insertions
# and in plain text that stacks automatically, malformed modifiers, and
# seeded random text, each compared with the reference glyph by glyph,
# which includes one cluster per group with its modifiers (compare()).
MIR = 0x13440
DMG = {name: 0x13446 + q for q, name in enumerate(
    "ts bs s te t bste st be tsbe b sb e te_e be_e all".split(), 1)}  # the fifteen, by the quarters they name
MODIFIER_WORDS = {
    # a lone sign mirrored: the sign flipped across the middle of its ink
    "A1<13440>": (898, [("u13000.m", 0, 0)]),
    # mirrored in a group: the variant flipped, at the same place
    "G43<13440>:N35": (922, [("_2m.u13171", 461, 249), ("_2.u13216", 461, 27)]),
    "G43:N35": (922, [("_2.u13171", 461, 249), ("_2.u13216", 461, 27)]),
    # level 4 has no mirrored variants: the sign, and the small box over the middle of its cell
    "A1<13440>:O1": (820, [("_4.u13000", 410, 432), ("_mir.box", 410, 756), ("_4.u13250", 410, 0)]),
    "D21<13440>:N35": (1234, [("_0.u1308B", 617, 599), ("_0.u13216", 617, 121)]),  # symmetric: as it is
    "G43<13440>-X1:N35": (2094, [("u13171.m", 0, 0), ("_0.u133CF", 1477, 599), ("_0.u13216", 1477, 121)]),
    # damage: shading over the named quarters of the cell, from its middle
    "A1<13455>": (898, [("u13000", 0, 0), ("_ht.1.10.12", 449, 540), ("_ht.2.10.12", 449, 540),
                        ("_ht.4.10.12", 449, 540), ("_ht.8.10.12", 449, 540)]),
    "D21<13450>:N35": (1234, [("_0.u1308B", 617, 599), ("_ht.2.13.4", 617, 779), ("_ht.8.13.4", 617, 779),
                              ("_0.u13216", 617, 121)]),
    "A1<13440><13447>": (898, [("u13000.m", 0, 0), ("_ht.1.10.12", 449, 540)]),
}
MODIFIER_MALFORMED = [  # the stray modifier keeps its box (rule M3)
    "<13440>", "<13447>", "<13440>A1", "<13447>A1", "A1<13440><13440>", "A1<13447><13447>", "A1<13447><13440>",
    "<13441><13440>", "<13443><13447>", 'A1"\u200d"<13440>', 'A1"\u200c"<13447>', 'A1<13440>"\u200d"<13447>',
    "A1:<13440>O1", "A1<13430><13447>", "A1<13440><13434>X1", "<13437>A1<13440><13438>",
    'A1" "<13440>', "A1<13440><13440>:O1", "A1<13447><13440>:O1", "<13447>D21:N35",
]


def modifier_texts(rng):
    """Seeded random text with modifiers: groups, insertions, plain text,
    malformed sequences."""
    hieroglyphs = [c for c in sorted(SIGNS) if c in L.HIEROGLYPHS]
    tall = [c for c in hieroglyphs if SIGNS[c].cell[1] >= 10]
    small = [c for c in hieroglyphs if L.insertable(SIGNS[c])]
    birds = [c for c in L.BIRDS if c in SIGNS]
    damage = list(L.DAMAGE)

    def literal(sign):
        r = rng.random()
        mods = [MIR] * (r < 0.45) + [rng.choice(damage)] * (0.3 < r < 0.75)
        return [sign] + mods
    texts = []
    for _ in range(700):  # groups of one to four rows, every sign maybe modified
        rows = [[rng.choice(tall if rng.random() < 0.3 else hieroglyphs) for _ in range(rng.choice((1, 2, 2, 3)))]
                for _ in range(rng.choice((1, 2, 2, 3, 4)))]
        text = []
        for r, row in enumerate(rows):
            text += [V] * bool(r)
            for i, sign in enumerate(row):
                text += [H] * bool(i) + literal(sign)
        texts.append(text)
    for _ in range(500):  # insertions: a bird or any sign, a corner, a small sign
        base = rng.choice(birds if rng.random() < 0.6 else hieroglyphs)
        texts.append(literal(base) + [rng.choice(list(L.CORNERS))] + literal(rng.choice(small)))
    known = sorted({c for key in TABLE for c in key if c not in (L.START, L.END)})
    for _ in range(500):  # plain text the automatic layer stacks, modified
        text = []
        for _ in range(rng.randint(1, 8)):
            r = rng.random()
            text += literal(rng.choice(known)) if r < 0.75 else [rng.choice((0x20, 0x200C, V, H, 0x13434))]
        texts.append(text)
    for _ in range(500):  # anything: signs, modifiers, controls, other characters
        texts.append([rng.choice(hieroglyphs[:300] + [MIR] * 40 + damage * 4 + [V, H, 0x13434, 0x20, 0x200D,
                                                                                0xFE00, 0x13441, 0x13444])
                      for _ in range(rng.randint(1, 9))])
    return texts


def test_modifiers(shaper):
    for mdc, expected in MODIFIER_WORDS.items():
        text = encode(mdc)
        shaped = shaper.shape(text)
        found = (sum(g[4] for g in shaped), [(g[0], g[2], g[3]) for g in shaped if shaper.drawn(g[0])])
        check(found == expected, f"{mdc}: {found}, expected {expected}")
    texts = [encode(mdc) for mdc in list(MODIFIER_WORDS) + MODIFIER_MALFORMED]
    # every damage modifier on four signs of different shapes (tall, wide,
    # bird, small), alone, in a group, mirrored, inserted
    four = [gardiner(g) for g in ("A1", "N35", "G43", "X1")]
    for d in L.DAMAGE:
        for sign in four:
            texts += [[sign, d], [sign, MIR, d], [sign, d, V, gardiner("N35")], [gardiner("D21"), V, sign, d],
                      [sign, d, H, gardiner("Z1"), d]]
        texts += [[gardiner("G14"), d, 0x13434, gardiner("X1"), d], [gardiner("G43"), MIR, d, 0x13434, gardiner("X1")]]
    for c in NAMES.modifiers.mirrored:  # every mirrored sign, alone and in a group of two
        texts += [[c, MIR], [c, MIR, V, gardiner("N35")]]
    texts += modifier_texts(random.Random(29))
    compared, failed = compare_all(shaper, texts)
    # the stray modifiers of MODIFIER_MALFORMED keep their box
    for mdc in MODIFIER_MALFORMED:
        drawn = [g[0] for g in shaper.shape(encode(mdc)) if shaper.drawn(g[0])]
        check(any(g in shaper.boxes for g in drawn), f"{mdc}: no box for the stray modifier: {drawn}")
    # the automatic layer: a modified sign stacks as the sign does (rule M2)
    for plain, explicit in (("D21<13450>-N35", "D21<13450>:N35"), ("R4<13447>-X1-Q3<13440>", "R4<13447>:X1*Q3<13440>"),
                            ("G14<13440>-X1-B1", "G14<13440>-X1-B1")):
        found = [(g[0], g[2], g[3]) for g in shaper.shape(encode(plain)) if shaper.drawn(g[0])]
        reference = [(g[0], g[2], g[3]) for g in shaper.shape(encode(explicit)) if shaper.drawn(g[0])]
        check(found == reference, f"{plain} typed plainly: {found}, typed with controls: {reference}")
    off = Shaper(shaper.path, table=None, features={"calt": False})  # the modifiers do not need calt
    off_count, off_failed = compare_all(off, texts[:400])
    # the glyphs: a mirrored sign is one component of its sign, flipped
    glyf, m = shaper.font["glyf"], NAMES.modifiers
    for name, (codepoint, level) in list(shaper.mirrored.items())[::7]:
        (component,) = glyf[name].components
        transform = getattr(component, "transform", [[1, 0], [0, 1]])
        sign = SIGNS[codepoint]
        scale = sign.scales[level] if level is not None and name in [m.variant(codepoint, level)] else None
        check(component.glyphName == sign.name and transform[0][0] < 0 < transform[1][1]
              and abs(transform[0][0] + transform[1][1]) < 1 / 16384
              and (scale is None or abs(transform[1][1] - scale) < 1 / 16384), f"{name}: {transform}")
        flipped, plain = bounds(shaper, name), bounds(shaper, sign.name if level is None else
                                                      (NAMES.variant(codepoint, level) if name == m.variant(codepoint, level)
                                                       else NAMES.inserts.shrunk(codepoint, level)))
        check(all(abs(a - b) <= 2 for a, b in zip(flipped, plain)), f"{name}: ink {flipped}, unmirrored {plain}")
    for name, code in shaper.pieces.items():  # each piece inside its rectangle
        box, rect = bounds(shaper, name), L.hatch_rect(code)
        check(box and rect[0] <= box[0] and rect[1] <= box[1] and box[2] <= rect[2] and box[3] <= rect[3],
              f"{name}: ink {box} outside {rect}")
    print(f"  modifiers: {compared} texts compared, {failed} differ; with calt off {off_count}, {off_failed} differ; "
          f"{len(NAMES.modifiers.mirrored)} mirrored signs, {len(shaper.pieces)} pieces of shading")


# All the controls together (layout sections 8 to 11): golden lines in the
# form of ENCLOSURE_WORDS, written here, and seeded random text with
# literals in segments, overlays, side and corner insertions, plain words
# and groups, most of it in enclosures, compared glyph by glyph.
ALL_WORDS = {
    # Ptah in a cartouche, the stool in the segment damaged in full
    f"V11A{B}<13437>Q3<13455>:X1<13438>*V28{E}V11B": (
        2288, [("_0.u132AA", 941, 554), ("_ht.1.4.5", 941, 779), ("_ht.2.4.5", 941, 779), ("_ht.4.4.5", 941, 779),
               ("_ht.8.4.5", 941, 779), ("_0.u133CF", 941, 76), ("_0.u1339B", 1436, 0)],
        [("u13379.ring", 0, 0), ("_el.p.1024.s", 617, 0), ("_el.p.1024.e", 1671, 0), ("u1337A.ring", 1671, 0)]),
    # an overlay with its second operand mirrored
    "G17<13436>D36<13440>": (1324, [("_0.u13153", 662, 0), ("_0m.u1309D", 662, 270)], []),
    # the flag in the middle of the house, mirrored at level 5: the small box
    "O1<13439>R8<13440>": (1377, [("u13250", 0, 0), ("_5.u132B9", 689, 133), ("_mir.box", 689, 403)], []),
    # the same, damaged at top end, in a cartouche: moved down by 110
    f"V11A{B}O1<13439>R8<13440><1344A>{E}V11B": (
        2611, [("u13250", 617, -110), ("_5.u132B9", 1306, 23), ("_mir.box", 1306, 293), ("_ht.4.3.6", 1306, 293)],
        [("u13379.ring", 0, 0), ("_el.p.1024.s", 617, 0), ("_el.p.1024.e", 1994, 0), ("u1337A.ring", 1994, 0)]),
}


def all_control_texts(rng, count):
    """Seeded random text with every control (see above)."""
    hieroglyphs = [c for c in sorted(SIGNS) if c in L.HIEROGLYPHS]
    small = [c for c in hieroglyphs if L.insertable(SIGNS[c])]
    low = [c for c in hieroglyphs if SIGNS[c].cell[1] <= 6]
    narrow = [c for c in hieroglyphs if SIGNS[c].cell[0] <= 10]
    known = sorted({c for key in TABLE for c in key if c not in (L.START, L.END)})
    having = {c: [b for b in hieroglyphs if SIGNS[b].corners[c][0]["flat"].width] for c in L.SIDES}
    sb, se, ov = L.SEGMENT_START, L.SEGMENT_END, L.OVERLAY

    def literal(sign):
        r = rng.random()
        return [sign] + [MIR] * (r < 0.3) + [rng.choice(L.DAMAGE)] * (0.2 < r < 0.5)

    def part():
        r = rng.random()
        if r < 0.15:
            return literal(rng.choice(hieroglyphs))
        if r < 0.35:
            box = [sb, *literal(rng.choice(low)), V, *literal(rng.choice(low)), se]
            other = literal(rng.choice(narrow))
            return box + [H] + other if rng.random() < 0.5 else other + [H] + box
        if r < 0.5:
            left = literal(rng.choice(hieroglyphs)) if rng.random() < 0.7 else \
                [sb, *literal(rng.choice(narrow)), H, *literal(rng.choice(narrow)), se]
            out = left + [ov] + literal(rng.choice(hieroglyphs))
            return out + [V] + literal(rng.choice(low)) if rng.random() < 0.3 else out
        if r < 0.65:
            control = rng.choice(L.SIDES)
            return literal(rng.choice(having[control])) + [control] + literal(rng.choice(small if rng.random() < 0.6
                                                                                           else hieroglyphs))
        if r < 0.72:
            return literal(rng.choice(list(L.BIRDS) + small)) + [rng.choice(list(L.CORNERS))] + literal(rng.choice(small))
        if r < 0.85:
            return [c for _ in range(rng.randint(2, 4)) for c in literal(rng.choice(known))]
        if r < 0.93:
            out = []
            for i in range(rng.randint(1, 3)):
                out += [V] * bool(i)
                for j in range(rng.randint(1, 2)):
                    out += [H] * bool(j) + literal(rng.choice(hieroglyphs))
            return out
        return [rng.choice((V, H, sb, se, ov, 0x13439, 0x20, 0x200D, MIR, rng.choice(L.DAMAGE), 0x1343C, 0x1343D, 0xFE00))]
    texts = []
    for _ in range(count):
        text = [c for _ in range(rng.randint(0, 1)) for c in part()]
        if rng.random() < 0.8:
            plain = rng.random() < 0.6
            if rng.random() < 0.85:
                text += literal(rng.choice(L.OPENINGS)) if rng.random() < 0.2 else [rng.choice(L.OPENINGS)]
            text.append(0x1343C if plain else 0x1343E)
            for _ in range(rng.randint(1, 4)):
                text += part()
            text.append(0x1343D if plain else 0x1343F)
            if rng.random() < 0.85:
                text += literal(rng.choice(L.CLOSINGS)) if rng.random() < 0.2 else [rng.choice(L.CLOSINGS)]
        else:
            text += [c for _ in range(rng.randint(1, 3)) for c in part()]
        texts.append(text + [c for _ in range(rng.randint(0, 1)) for c in part()])
    return texts


def test_all_controls(shaper):
    """Every control together: the golden lines; the font equals the
    reference on seeded random text, with calt on and off; a modified sign
    in a box or inserted at middle, top or bottom stands where the sign does."""
    for mdc, expected in ALL_WORDS.items():
        shaped = shaper.shape(encode(mdc))
        found = (sum(g[4] for g in shaped), [(g[0], g[2], g[3]) for g in shaped if shaper.drawn(g[0])],
                 [(g[0], g[2], g[3]) for g in shaped if g[0] in shaper.frames])
        check(found == expected, f"{mdc}: {found}, expected {expected}")
    texts = [encode(mdc) for mdc in ALL_WORDS] + all_control_texts(random.Random(53), 1500)
    compared, failed = compare_all(shaper, texts)
    formed = sum(any(c.frame for c in L.layout(t, SIGNS, TABLE)) for t in texts)
    off = Shaper(shaper.path, table=None, features={"calt": False})
    off_count, off_failed = compare_all(off, texts[:300])
    for modified, plain in (("<13437>Q3<13455>:X1<13440><13438>*V28", "<13437>Q3:X1<13438>*V28"),
                            ("G17<13436>D36<1344F>", "G17<13436>D36"), ("O1<13439>X1<13447>", "O1<13439>X1")):
        def places(mdc):
            return [(g[2], g[3]) for g in shaper.shape(encode(mdc)) if g[0] in shaper.variants or g[0] in shaper.lone
                    or g[0] in shaper.mirrored]
        check(places(modified) == places(plain), f"{modified}: {places(modified)}, unmodified {places(plain)}")
    print(f"  all controls: {compared} texts compared, {failed} differ ({formed} with an enclosure); "
          f"with calt off {off_count}, {off_failed} differ")


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
                *NAMES.heads(), *NAMES.markers(), *(n for k in glyphs.LEVELS for n in NAMES.leveled(k)),
                *NAMES.inserts.bases(), *NAMES.inserts.markers(), *AUTOMATIC.markers(),
                *ENCLOSURES.bases(), *ENCLOSURES.empty_bases(), *ENCLOSURES.marks(),
                *NAMES.modifiers.bases(), *NAMES.modifiers.marks(), *NAMES.modifiers.markers(),
                *NESTING.markers(), NESTING.run_start, NESTING.bad_start, *SIDES.markers(), *SIDES.candidates()}
    shared = {".notdef", "space", NAMES.dotted_circle, NAMES.zwnj, *NAMES.ignorables}
    names = set(shaper.order)
    for tag in ("GSUB", "GPOS"):
        table = font[tag]
        records = table.table.FeatureList.FeatureRecord
        scripts = {s.ScriptTag: s.Script for s in table.table.ScriptList.ScriptRecord}
        check({"DFLT", "egyp"} <= set(scripts), f"{tag}: egyp or DFLT is not declared")
        stacking = {"rlig", "calt"} if tag == "GSUB" else set()
        for script_tag, script in scripts.items():
            tags = {records[i].FeatureTag for i in script.DefaultLangSys.FeatureIndex}
            check(script_tag in ("DFLT", "egyp") or not tags & {"rlig", "calt"},
                  f"{tag}: rlig or calt is registered for {script_tag}")
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


# Enclosures and sign modifiers together (layout sections 10 and 11): golden
# lines in the form of ENCLOSURE_WORDS, written here, and seeded random text
# that mixes enclosures (with modified delimiters too), literals, groups,
# insertions, plain words and stray characters, compared glyph by glyph.
COMBINED_WORDS = {
    # Khufu, the first chick mirrored, the viper damaged at top start and bottom end
    f"V11A{B}Aa1-G43<13440>-I9<1344F>-G43{E}V11B": (
        5000, [("_0.u1340D", 964, 0), ("_0m.u13171", 1748, 0), ("_0.u13191", 2847, 315), ("_ht.1.14.5", 2847, 540),
               ("_ht.8.14.5", 2847, 540), ("_0.u13171", 3946, 0)],
        [("u13379.ring", 0, 0), ("_el.p.512.s", 617, 0), ("_el.p.512.e", 1311, 0), ("_el.p.512.s", 1311, 0),
         ("_el.p.512.e", 2185, 0), ("_el.p.1024.s", 2185, 0), ("_el.p.1024.e", 3509, 0), ("_el.p.512.s", 3509, 0),
         ("_el.p.512.e", 4383, 0), ("u1337A.ring", 4383, 0)]),
    # a damaged sign in a stacked group inside a walled enclosure
    f"O36C{BW}D21<13450>:N35{EW}O36D": (
        2514, [("_0.u1308B", 1257, 599), ("_ht.2.13.4", 1257, 779), ("_ht.8.13.4", 1257, 779), ("_0.u13216", 1257, 121)],
        [("u13288.ring", 0, 0), ("_el.w.1024.s", 640, 0), ("_el.w.1024.e", 1874, 0), ("_em.w.8", 1257, 0),
         ("u13289.ring", 1874, 0)]),
    # modifiers on the delimiters: the enclosure forms, they draw nothing
    f"V11A<13440>{B}Aa1{E}V11B<13455>": (
        1928, [("_0.u1340D", 964, 0)],
        [("u13379.ring", 0, 0), ("_el.p.512.s", 617, 0), ("_el.p.512.e", 1311, 0), ("u1337A.ring", 1311, 0)]),
    # the chick mirrored and damaged, the bread in its (swapped) corner: the
    # block moved up by 13, the shading with it
    f"V11A{B}G43<13440><13449><13432>X1{E}V11B": (
        2094, [("u13171.shrink1.m", 617, 13), ("_ht.1.8.10", 1047, 462), ("_ht.2.8.10", 1047, 462),
               ("_3.u133CF", 846, 782)],
        [("u13379.ring", 0, 0), ("_el.p.512.s", 617, 0), ("_el.p.512.e", 1477, 0), ("u1337A.ring", 1477, 0)]),
}


def combined_texts(rng, count):
    """Seeded random text with enclosures and modifiers (see above)."""
    hieroglyphs = [c for c in sorted(SIGNS) if c in L.HIEROGLYPHS]
    small = [c for c in hieroglyphs if L.insertable(SIGNS[c])]
    birds = [c for c in L.BIRDS if c in SIGNS]
    known = sorted({c for key in TABLE for c in key if c not in (L.START, L.END)})

    def literal(sign):
        r = rng.random()
        return [sign] + [MIR] * (r < 0.35) + [rng.choice(L.DAMAGE)] * (0.25 < r < 0.6)

    def part():
        r = rng.random()
        if r < 0.3:
            return literal(rng.choice(hieroglyphs))
        if r < 0.55:
            out = []
            for i in range(rng.randint(1, 3)):
                out += [V] * bool(i)
                for j in range(rng.randint(1, 2)):
                    out += [H] * bool(j) + literal(rng.choice(hieroglyphs))
            return out
        if r < 0.7:
            return literal(rng.choice(birds + small)) + [rng.choice(list(L.CORNERS))] + literal(rng.choice(small))
        if r < 0.88:  # plain text the automatic layer stacks
            return [c for _ in range(rng.randint(2, 4)) for c in literal(rng.choice(known))]
        return [rng.choice((V, H, 0x13437, 0x20, 0x200D, MIR, rng.choice(L.DAMAGE), 0x1343C, 0x1343D, 0xFE00))]
    texts = []
    for _ in range(count):
        text = [c for _ in range(rng.randint(0, 1)) for c in part()]
        plain = rng.random() < 0.6
        if rng.random() < 0.85:
            text += literal(rng.choice(L.OPENINGS)) if rng.random() < 0.3 else [rng.choice(L.OPENINGS)]
        text.append(0x1343C if plain else 0x1343E)
        for _ in range(rng.randint(1, 5)):
            text += part()
        text.append(0x1343D if plain or rng.random() < 0.05 else 0x1343F)
        if rng.random() < 0.85:
            text += literal(rng.choice(L.CLOSINGS)) if rng.random() < 0.3 else [rng.choice(L.CLOSINGS)]
        texts.append(text + [c for _ in range(rng.randint(0, 1)) for c in part()])
    return texts


def test_combined(shaper):
    """Enclosures with modified signs: the golden lines; the font equals
    the reference on seeded random text, with calt on and off; modified
    delimiters join and draw nothing; the automatic layer stacks a modified
    word inside a cartouche as it stacks the word with its controls."""
    for mdc, expected in COMBINED_WORDS.items():
        shaped = shaper.shape(encode(mdc))
        found = (sum(g[4] for g in shaped), [(g[0], g[2], g[3]) for g in shaped if shaper.drawn(g[0])],
                 [(g[0], g[2], g[3]) for g in shaped if g[0] in shaper.frames])
        check(found == expected, f"{mdc}: {found}, expected {expected}")
    texts = [encode(mdc) for mdc in COMBINED_WORDS]
    for d in (*L.OPENINGS, *L.CLOSINGS):  # every delimiter mirrored and damaged, joined and apart
        texts += [[d, MIR, DMG["all"], 0x1343C, gardiner("A1"), 0x1343D], [0x1343C, gardiner("A1"), 0x1343D, d, MIR],
                  [d, MIR, 0x200D, 0x1343E, gardiner("A1"), 0x1343F, d, DMG["ts"]]]
    texts += combined_texts(random.Random(37), 1500)
    compared, failed = compare_all(shaper, texts)
    formed = sum(any(c.frame for c in L.layout(t, SIGNS, TABLE)) for t in texts)
    off = Shaper(shaper.path, table=None, features={"calt": False})
    off_count, off_failed = compare_all(off, texts[:300])
    for plain, explicit in ((f"V11A{B}D21<13450>-N35-G43<13440>{E}V11B", f"V11A{B}D21<13450>:N35-G43<13440>{E}V11B"),
                            (f"O36C{BW}R4<13447>-X1-Q3<13440>{EW}O36D", f"O36C{BW}R4<13447>:X1*Q3<13440>{EW}O36D")):
        found = [(g[0], g[2], g[3]) for g in shaper.shape(encode(plain)) if shaper.drawn(g[0]) or g[0] in shaper.frames]
        reference = [(g[0], g[2], g[3]) for g in shaper.shape(encode(explicit))
                     if shaper.drawn(g[0]) or g[0] in shaper.frames]
        check(found == reference, f"{plain} typed plainly: {found}, typed with controls: {reference}")
    print(f"  enclosures with modifiers: {compared} texts compared, {failed} differ ({formed} with an enclosure); "
          f"with calt off {off_count}, {off_failed} differ")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fonts/ttf/Thoth-Regular.ttf"
    shaper = Shaper(path)
    tests = (test_cmap, test_lone_signs, test_controls, test_glyphs, test_golden, test_words,
             test_groups, test_insertion, test_malformed, test_mixed, test_automatic, test_nesting,
             test_side_insertion, test_enclosures, test_modifiers, test_combined, test_all_controls,
             test_lookups, test_budget)
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
