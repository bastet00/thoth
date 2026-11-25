"""Tests for the reference layout (scripts/stack/layout.py), run by "make test".

    python3 tests/test_layout.py

The reference decides where the signs of a group go; the font is to follow
it. These tests pin the reference itself, without the built font: the
owner's rules said as properties, the rounding the font can follow, a small
set of golden cases, the grammar, and the rule that no input may hide a
sign or draw one over another. Exits with status 1 if any check fails.
"""

import hashlib
import random
import sys
from pathlib import Path

import ufoLib2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "stack"))
sys.dont_write_bytecode = True  # a cache in scripts/stack would make "make" rebuild the font

import glyphs  # noqa: E402  (the generator, only to compare the fallback box)
import layout as L  # noqa: E402

SOURCE = ufoLib2.Font.open(ROOT / "sources/Thoth-Regular.ufo")
V, H = L.VERTICAL_JOINER, L.HORIZONTAL_JOINER  # written ":" and "*" below
TOP = L.HEIGHT_LIMIT * L.UNIT  # the top of the quadrat's cells

# Signs used below, by their Gardiner numbers.
A1, A40, B1 = 0x13000, 0x1302D, 0x13050  # seated man, seated god, woman
D4, D21, D58 = 0x13079, 0x1308B, 0x130C0  # eye, mouth, foot
F35, G14, I9 = 0x13124, 0x13150, 0x13191  # nfr, vulture, viper
M17, N1, N16 = 0x131CB, 0x131EF, 0x131FE  # reed, sky, land
N23, N33, N35 = 0x13207, 0x13212, 0x13216  # canal, pellet, water
O1, O29, Q1, Q3 = 0x13250, 0x1327B, 0x132A8, 0x132AA  # house, column, seat, stool
R4, R8, W24 = 0x132B5, 0x132B9, 0x133CC  # offering table, flag, pot
X1, Z1, Z2, Z4, Z7, Z15 = 0x133CF, 0x133E4, 0x133E5, 0x133ED, 0x133F2, 0x133FA
FULL_BLANK, HALF_LOST = 0x13441, 0x13444

# Golden cases: text, and for each cluster its advance and its glyphs as
# (code point, x, y, level, scale). The numbers are written here, not read
# from layout.py, so a changed constant or rule fails.
GOLDEN = [
    (  # A1 : O1, figure 11-1 of the Unicode chapter: 20 units high, level 4
        [A1, V, O1],
        [(820, [(A1, 141, 432, 4, 0.6), (O1, 21, -62, 4, 0.564)])],
    ),
    (  # W24 * Z7, figure 11-1: one row with a high sign stands on the baseline
        [W24, H, Z7],
        [(1054, [(W24, 20, -151, 0, 1.0), (Z7, 484, 17, 0, 1.0)])],
    ),
    (  # D21 : N35 "name": two low signs, half the quadrat each
        [D21, V, N35],
        [(1234, [(D21, 28, 604, 0, 1.0), (N35, 18, 202, 0, 1.0)])],
    ),
    (  # F35, I9 : D21 "good": a lone tall sign, then viper over mouth
        [F35, I9, V, D21],
        [(359, [(F35, 0, 0, 0, 1.0)]), (1324, [(I9, 7, 564, 0, 0.872), (D21, 73, 81, 0, 1.0)])],
    ),
    (  # R4 : X1 * Q3 "offering": 3 units free, bread and stool justified
        [R4, V, X1, H, Q3],
        [(1324, [(R4, 1, 509, 0, 0.99), (X1, 30, -171, 0, 1.0), (Q3, 910, 55, 0, 1.0)])],
    ),
    (  # N35 : Q3 * N33: 6 units free, the most that is justified
        [N35, V, Q3, H, N33],
        [(1234, [(N35, 18, 793, 0, 1.0), (Q3, 10, 122, 0, 1.0), (N33, 928, 179, 0, 1.0)])],
    ),
    (  # N35 : Q3 * Z1: 7 units free, packed and centred
        [N35, V, Q3, H, Z1],
        [(1234, [(N35, 18, 793, 0, 1.0), (Q3, 325, 122, 0, 1.0), (Z1, 692, 98, 0, 1.0)])],
    ),
    (  # N35 : N35 : N35 "water": three rows packed, the block centred
        [N35, V, N35, V, N35],
        [(1234, [(N35, 18, 756, 0, 1.0), (N35, 18, 486, 0, 1.0), (N35, 18, 216, 0, 1.0)])],
    ),
    (  # X1 : N35 : X1 : N35: four rows, 14 units, level 1
        [X1, V, N35, V, X1, V, N35],
        [(1065, [(X1, 261, 598, 1, 0.855), (N35, 20, 609, 1, 0.855), (X1, 261, 59, 1, 0.855), (N35, 20, 70, 1, 0.855)])],
    ),
    (  # X1 * Z1: a low row is centred
        [X1, H, Z1],
        [(874, [(X1, 30, 113, 0, 1.0), (Z1, 647, 315, 0, 1.0)])],
    ),
    (  # D58 : N35: a sign higher than the quadrat is reduced first
        [D58, V, N35],
        [(935, [(D58, 200, 423, 2, 0.595), (N35, 22, 87, 2, 0.744)])],
    ),
    (  # two half lost signs over N35, a blank over N35
        [HALF_LOST, H, HALF_LOST, V, N35, FULL_BLANK, V, N35],
        [(1296, [(HALF_LOST, 43, 358, 1, 0.855), (HALF_LOST, 659, 358, 1, 0.855), (N35, 136, 135, 1, 0.855)]),
         (935, [(FULL_BLANK, 32, 412, 2, 0.627), (N35, 22, 87, 2, 0.744)])],
    ),
    (  # the narrowest sign at level 6: rule 5 takes its whole quarter
        [A1, V, A1, V, A1, H, Z15],
        [(394, [(A1, 51, 720, 6, 0.325), (A1, 51, 360, 6, 0.325), (A1, 36, 0, 6, 0.325), (Z15, 332, 0, 6, 0.25)])],
    ),
    (  # the height cap: 40 units, level 7, and 41 units, unstacked
        [A1, V, A1, V, A1, V, X1, A1, V, A1, V, A1, V, Z1],
        [(284, [(A1, 39, 716, 7, 0.229), (A1, 39, 452, 7, 0.229), (A1, 39, 188, 7, 0.229), (X1, 77, 59, 7, 0.204)]),
         (898, [(A1, 0, 0, 0, 1.0)]), (698, [(V, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)]),
         (698, [(V, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)]), (698, [(V, 0, 0, 0, 1.0)]),
         (209, [(Z1, 0, 315, 0, 1.0)])],
    ),
    (  # the width cap: 32 units, level 6, and 33 units, unstacked
        [A1, H, A1, H, A1, H, Z1, A1, H, A1, H, A1, H, Z1, H, Z15],
        [(1024, [(A1, 36, 0, 6, 0.325), (A1, 336, 0, 6, 0.325), (A1, 636, 0, 6, 0.325), (Z1, 936, 0, 6, 0.25)]),
         (898, [(A1, 0, 0, 0, 1.0)]), (698, [(H, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)]),
         (698, [(H, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)]), (698, [(H, 0, 0, 0, 1.0)]),
         (209, [(Z1, 0, 315, 0, 1.0)]), (698, [(H, 0, 0, 0, 1.0)]), (117, [(Z15, 0, 315, 0, 1.0)])],
    ),
    (  # A1 : Z2, man over plural strokes: 17 units, level 3
        [A1, V, Z2],
        [(664, [(A1, 33, 337, 3, 0.666), (Z2, 56, 23, 3, 0.639)])],
    ),
    (  # A1 : A1, two tall signs: 24 units, level 5
        [A1, V, A1],
        [(514, [(A1, 32, 540, 5, 0.5), (A1, 32, 0, 5, 0.5)])],
    ),
    (  # R8, M17, X1 alone (the owner's picture) and R4 (6 units): X1 and R4 lifted
        [R8, M17, X1, R4],
        [(587, [(R8, 0, 0, 0, 1.0)]), (342, [(M17, 0, 0, 0, 1.0)]),
         (633, [(X1, 0, 189, 0, 1.0)]), (1336, [(R4, 0, 293, 0, 1.0)])],
    ),
    (  # a trailing joiner: the whole run is unstacked, the joiner shows its box
        [X1, V, N35, V],
        [(633, [(X1, 0, 189, 0, 1.0)]), (698, [(V, 0, 0, 0, 1.0)]),
         (1197, [(N35, 0, 506, 0, 1.0)]), (698, [(V, 0, 0, 0, 1.0)])],
    ),
]

# Every malformed input of the review corpus. None is a well-formed group.
SEGMENT, END, OVERLAY, INSERT, MIRROR = 0x13437, 0x13438, 0x13436, 0x13432, 0x13440
MALFORMED = [
    [V], [V, N35], [H, A1, A1], [X1, V, N35, V], [X1, V, V, N35], [X1, V, V, N35, A1],
    [X1, V, H, N35], [X1, V, 0x20, N35], [X1, 0x200D, V, N35],
    [SEGMENT, X1, V, N35], [X1, V, N35, END], [SEGMENT, X1, V, N35, END],
    [M17, H, SEGMENT, X1, V, N35, V, A1], [X1, OVERLAY, O1, N35], [A1, INSERT, O1, X1],
    [A1, MIRROR], [I9, V, N35, V, 0x13113, 0x13433, A1], [*range(0x13430, 0x13441)],
    [A1, V, A1, V, A1, V, A1],  # 48 units high: over the cap
    [N35, H, N35, H, N35],  # 39 units wide: over the cap
    [D58, V, D58, V, D58, V, D58, V, N35],  # 51 units high
]

failures = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def label(codepoints):
    return " ".join(f"{c:04X}" for c in codepoints)


def result(codepoints, signs):
    """The layout in the form of the golden cases."""
    return [(cluster.advance, [tuple(glyph) for glyph in cluster.glyphs])
            for cluster in L.layout(codepoints, signs)]


def group(rows):
    """Text for a group given as rows of code points."""
    text = []
    for row in rows:
        text += [V] * bool(text)
        for member in row:
            text += [H] * bool(text and text[-1] != V) + [member]
    return text


def boxes(codepoints, signs):
    """[(cluster, [ink box in line coordinates])] for a line of text."""
    pen, out = 0, []
    for cluster in L.layout(codepoints, signs):
        inks = [L.ink_box(glyph, signs) for glyph in cluster.glyphs]
        out.append((cluster, [(pen + a, b, pen + c, d) for a, b, c, d in inks]))
        pen += cluster.advance
    return out


def stacked(codepoints, signs):
    """The one group of a text: (cluster, ink boxes)."""
    (found,) = [(c, inks) for c, inks in boxes(codepoints, signs) if c.stacked]
    return found


def apart(one, other):
    """The distance between two boxes along the axis that separates them."""
    return max(other[0] - one[2], one[0] - other[2], other[1] - one[3], one[1] - other[3])


def at_floor(glyph, signs):
    """Rule 5 took its whole quarter: the sign may come closer than GAP."""
    sign = signs[glyph.codepoint]
    return glyph.scale < sign.scales[0] * L.unit(glyph.level) / L.UNIT * 0.76


def check_visible(codepoints, signs):
    """Nothing hidden, nothing overlapping, nothing outside its advance."""
    name = label(codepoints)
    laid = boxes(codepoints, signs)
    drawn = [glyph.codepoint for cluster, _ in laid for glyph in cluster.glyphs]
    joined = {i for cluster, _ in laid if cluster.stacked for i in range(cluster.start, cluster.end)}
    expected = [c for i, c in enumerate(codepoints)
                if L.is_sign(c) or (c in L.CONTROLS and i not in joined)]
    check(drawn == expected, f"{name}: drawn {label(drawn)}")  # only joiners that join are hidden
    pen = 0
    for cluster, inks in laid:
        check(cluster.advance > 0, f"{name}: a cluster has no advance")
        if cluster.stacked:
            check(all(pen <= ink[0] and ink[2] <= pen + cluster.advance for ink in inks),
                  f"{name}: a sign leaves the advance of its group")
            check(all(glyph.scale == signs[glyph.codepoint].scales[glyph.level]
                      for glyph in cluster.glyphs), f"{name}: a sign has the wrong scale")
            bearing = [L.SIDE_BEARING - (L.GAP // 2 if at_floor(g, signs) else 1)
                       for g in cluster.glyphs]  # a floored sign may fill its cell
            check(all(pen + b <= ink[0] and ink[2] <= pen + cluster.advance - b
                      for b, ink in zip(bearing, inks)),
                  f"{name}: a group is closer to its neighbour than the side bearing")
            check(all(-1 <= ink[1] and ink[3] <= TOP - L.GAP + 2 for ink in inks),
                  f"{name}: a group leaves the quadrat")
            pairs = [(g, a, h, b) for i, (g, a) in enumerate(zip(cluster.glyphs, inks))
                     for h, b in zip(cluster.glyphs[:i], inks[:i])]
            check(all(apart(a, b) >= L.GAP - 2 for g, a, h, b in pairs  # 2 for rounding
                      if not (at_floor(g, signs) or at_floor(h, signs))),
                  f"{name}: two signs of a group are closer than the gap")
        pen += cluster.advance
    # Lone signs are drawn as the source has them, and a few source signs
    # reach beyond their advance into their neighbour (U+1339C by 346): that
    # overlap is the source's, not this file's.
    def overhangs(cluster, glyph):
        sign = signs.get(glyph.codepoint)
        return not cluster.stacked and sign and not 0 <= sign.box[0] <= sign.box[2] <= sign.advance
    every = [(ink, overhangs(cluster, glyph))
             for cluster, inks in laid for glyph, ink in zip(cluster.glyphs, inks)]
    check(all(apart(a, b) > 0 for i, (a, one) in enumerate(every) for b, other in every[:i]
              if not (one or other)), f"{name}: two glyphs overlap")


def test_constants(signs):
    check([L.unit(level) for level in range(len(L.LEVEL_HEIGHTS))] == [90, 77, 67, 60, 54, 45, 30, 22],
          "the eight levels changed")
    check(L.MIDDLE == 523, "the middle line changed")
    # the fallback box is drawn by the generator; the reference repeats its size
    check(L.CONTROL_ADVANCE == glyphs.BOX + 2 * glyphs.SIDE_BEARING
          and L.CONTROL_BOX == (glyphs.SIDE_BEARING, glyphs.BOTTOM,
                                glyphs.SIDE_BEARING + glyphs.BOX, glyphs.BOTTOM + glyphs.BOX)
          and L.SIDE_BEARING == glyphs.SIDE_BEARING and [*L.CONTROLS] == [*glyphs.CONTROLS],
          "layout.py and glyphs.py disagree about the fallback box")


def test_signs(signs):
    """The size classes, scales and lifts of all 1,078 signs, by checksum."""
    check(len(signs) == 1078, f"{len(signs)} signs, expected 1,078")
    table = repr([(c, s.cell, s.scales, s.lift) for c, s in sorted(signs.items())])
    digest = hashlib.sha1(table.encode()).hexdigest()[:12]
    check(digest == "4f347f7f60d2", f"the sign table changed: {digest}")
    # every sign fits a cell on its own: the font needs no larger classes
    check(max(s.cell[0] for s in signs.values()) == L.WIDTH_LIMIT, "a cell is wider than the quadrat")
    check(max(s.cell[1] for s in signs.values()) == L.HEIGHT_LIMIT, "a cell is higher than the quadrat")
    check(L.sign_table(ufoLib2.Font.open(ROOT / "sources/Thoth-Regular.ufo")) == signs,
          "the sign table is not deterministic")


def test_grammar(signs):
    parses = [
        ([A1], ((A1,),)),
        ([A1, V, O1], ((A1,), (O1,))),
        ([W24, H, Z7], ((W24, Z7),)),
        ([A1, V, O1, H, X1], ((A1,), (O1, X1))),  # the horizontal joiner binds tighter
        ([A1, H, O1, V, X1, H, Z1, V, N35], ((A1, O1), (X1, Z1), (N35,))),
        ([FULL_BLANK, V, HALF_LOST], ((FULL_BLANK,), (HALF_LOST,))),
        ([], None), ([V], None), ([V, A1], None), ([A1, V], None), ([A1, V, V, O1], None),
        ([A1, V, H, O1], None), ([A1, H], None), ([A1, O1], None),
        ([A1, SEGMENT, O1], None), ([SEGMENT, A1, V, O1, END], None), ([A1, MIRROR], None),
    ]
    for run, expected in parses:
        check(L.parse(run) == expected, f"parse {label(run)}: {L.parse(run)}")
    text = [A1, O1, V, X1, 0x20, V, N35, 0x72, A1, V, V, O1, X1]
    check(L.runs(text) == [(0, 1), (1, 4), (5, 7), (8, 12), (12, 13)], f"runs: {L.runs(text)}")
    fits = {  # (width, height) in units -> level
        (14, 12): 0, (1, 1): 0, (14, 13): 1, (14, 14): 1, (16, 14): 1, (17, 14): 2, (14, 16): 2,
        (14, 17): 3, (14, 18): 3, (14, 19): 4, (14, 20): 4, (14, 21): 5, (14, 24): 5,
        (28, 24): 5, (29, 24): 6, (14, 25): 6, (14, 36): 6, (14, 37): 7, (32, 40): 7,
        (33, 1): None, (1, 41): None,
    }
    for size, level in fits.items():
        check(L.fit_level(*size) == level, f"fit_level{size}: {L.fit_level(*size)}")


def test_golden(signs):
    for codepoints, expected in GOLDEN:
        got = result(codepoints, signs)
        check(got == expected, f"{label(codepoints)}:\n  got      {got}\n  expected {expected}")


def test_golden_notices_constants(signs):
    """Changing any constant of the layout must break a golden case."""
    changes = {
        "UNIT": 91, "GAP": 33, "HEIGHT_LIMIT": 11, "WIDTH_LIMIT": 13, "SIDE_BEARING": 50,
        "MAX_WIDTH": 31, "MAX_HEIGHT": 39, "MAX_JUSTIFY": 5, "LOW_HEIGHT": 5, "MIDDLE": 524,
        "MOST_REDUCED": 0.7, "CONTROL_ADVANCE": 699,
    }
    changes.update({f"LEVEL_HEIGHTS[{level}]": level for level in range(1, len(L.LEVEL_HEIGHTS))})
    for name, value in changes.items():
        if name.startswith("LEVEL_HEIGHTS"):
            name, kept = "LEVEL_HEIGHTS", L.LEVEL_HEIGHTS
            value = tuple(h - 2 * (i == value) for i, h in enumerate(kept))
        kept = getattr(L, name)
        setattr(L, name, value)
        try:
            changed = L.sign_table(SOURCE)
            broken = any(result(c, changed) != expected for c, expected in GOLDEN)
        finally:
            setattr(L, name, kept)
        check(broken, f"no golden case notices {name} = {value}")


def test_owner_rules(signs):
    """The owner's rules O1 to O4 and O6 (decision 004), said without numbers."""
    rng = random.Random(5)
    words = [  # the famous words of the proof, as groups
        [F35], [I9, V, D21], [R4, V, X1, H, Q3], [D21, V, N35], [G14, V, X1, H, B1],
        [D4, V, Q1, H, A40], [N16, V, Z1, H, N23], [D4, V, X1, H, Z1], [Q3, H, X1, V, N1],
        [O29, V, O1, H, O1], [0x13193, V, X1, H, Z1], [0x131F3, V, Z1], [0x131A3, V, D21],
        [N35, V, Z1, H, Z1], [N35, V, X1, H, Z4], [X1, H, Z1], [M17, H, X1], [N33, H, N33, H, N33],
    ]
    # O1: the signs of a row stand on one line
    for _ in range(300):
        rows = [[rng.choice(sorted(signs)) for _ in range(rng.choice((1, 2, 3)))]
                for _ in range(rng.choice((1, 2, 3)))]
        text = group(rows)
        if len(text) == 1 or L.fit_level(*L.measure(tuple(map(tuple, rows)), signs)[:2]) is None:
            continue
        cluster, inks = stacked(text, signs)
        start = 0
        for row in rows:
            bottoms = [ink[1] for ink in inks[start:start + len(row)]]
            start += len(row)
            check(max(bottoms) - min(bottoms) <= 1, f"{label(text)}: a row does not stand on one line")
    # O2: nfr, viper over mouth: each takes half the block, at full size
    cluster, (viper, mouth) = stacked([I9, V, D21], signs)
    check(cluster.glyphs[0].level == 0 and 0 <= mouth[1] and mouth[3] < L.MIDDLE < viper[1]
          and viper[3] <= TOP - L.GAP, "I9 : D21 does not take half the quadrat each")
    # O3: a group with a wide sign on top is not shrunken: level 0, as wide
    # as the quadrat and nearly as high as a tall sign; tall signs side by
    # side keep their size and stand on the baseline
    cluster, inks = stacked([R4, V, X1, H, Q3], signs)
    width = max(i[2] for i in inks) - min(i[0] for i in inks)
    height = max(i[3] for i in inks) - min(i[1] for i in inks)
    check(cluster.glyphs[0].level == 0 and width > 1200 and height > 900,
          f"R4 : X1 * Q3 is {width:.0f} by {height:.0f} at level {cluster.glyphs[0].level}")
    for tall in (A1, M17, 0x13171, 0x1339B, 0x132F9):  # man, reed, chick, wick, ankh
        cluster, inks = stacked([tall, H, M17], signs)
        check(cluster.glyphs[0].scale == 1.0 and inks[0][1] == 0 and inks[1][1] == 0,
              f"U+{tall:X} * M17: the tall sign shrank or left the baseline")
    # O4: rows of two are justified to the group's edges (on cells: the ink
    # may be up to half a unit in); single members and rows of three centred
    for text in ([R4, V, X1, H, Q3], [D4, V, X1, H, Z1], [Q3, H, X1, V, N1], [N16, V, Z1, H, N23]):
        _, inks = stacked(text, signs)
        row = [i for i, c in enumerate(c for c in text if L.is_sign(c)) if c in (X1, Q3, Z1, N23)]
        first, last = inks[row[0]], inks[row[-1]]
        rest = [ink for i, ink in enumerate(inks) if i not in row]
        check(0 <= first[0] - min(i[0] for i in rest) <= L.UNIT / 2
              and 0 <= max(i[2] for i in rest) - last[2] <= L.UNIT / 2,
              f"{label(text)}: the row of two is not flush with the edges")
    for text in ([N35, V, Z1, H, Z1], [N35, V, Z1, H, Z1, H, Z1], [N35, V, Z1], [R4, V, X1]):
        cluster, inks = stacked(text, signs)
        left, right = inks[1][0] - inks[0][0], inks[0][2] - inks[-1][2]
        check(abs(left - right) <= 2 and left > L.UNIT, f"{label(text)}: the row is not centred")
    # O6: a lone low sign is centred on the middle line, a high one is not moved
    for codepoint, sign in signs.items():
        (cluster,) = L.layout([codepoint], signs)
        bottom, top = sign.box[1] + cluster.glyphs[0].y, sign.box[3] + cluster.glyphs[0].y
        if sign.cell[1] <= L.LOW_HEIGHT:
            check(abs((bottom + top) / 2 - L.MIDDLE) <= 1, f"U+{codepoint:X} alone is not centred")
        else:
            check(cluster.glyphs[0].y == 0, f"U+{codepoint:X} alone has moved")
    check(sum(sign.lift != 0 for sign in signs.values()) == 185, "the number of lifted signs changed")
    # the owner's picture: R8 M17 X1, the bread on the middle line
    flag, reed, bread = [ink for _, (ink,) in boxes([R8, M17, X1], signs)]
    check(flag[1] == signs[R8].box[1] and reed[1] == signs[M17].box[1]
          and abs((bread[1] + bread[3]) / 2 - L.MIDDLE) <= 1, "R8 M17 X1 is not as the owner set it")
    # a one-row group lower than the quadrat is centred like a lone sign
    for text in ([X1, H, Z1], [N33, H, N33, H, N33], [D21, H, Z1], [Z1, H, Z1, H, Z1]):
        _, inks = stacked(text, signs)
        middle = (min(i[1] for i in inks) + max(i[3] for i in inks)) / 2
        check(abs(middle - L.MIDDLE) <= L.UNIT / 2, f"{label(text)}: the low row is not centred")
    for text in ([M17, H, X1], [W24, H, Z7]):
        _, inks = stacked(text, signs)
        check(min(i[1] for i in inks) <= 0, f"{label(text)}: a high row left the baseline")
    # rule 7: two rows are centred together, and rn is no more spread than in
    # round 1 (288 units of air)
    for text in words:
        if text.count(V) == 1:
            _, inks = stacked(text, signs) if len(text) > 1 else (None, None)
            middle = (min(i[1] for i in inks) + max(i[3] for i in inks)) / 2
            check(abs(middle - L.MIDDLE) <= L.UNIT, f"{label(text)}: two rows are not centred")
    _, (mouth, water) = stacked([D21, V, N35], signs)
    check(mouth[1] - water[3] <= 288, "D21 : N35 is more spread than in round 1")
    for text in words:
        check_visible(text, signs)


def test_rounding(signs):
    """Every position is a sum of whole numbers each glyph can carry (the
    rounding contract): a sign is centred in its cell by its own offset, and
    its cell starts flush with an edge of the group, or a whole number of
    units from half the group less half its row (each half rounded down); a
    row stands on its cell bottoms."""
    rng = random.Random(7)
    codepoints = sorted(signs)
    edge = L.SIDE_BEARING - L.GAP // 2
    for _ in range(500):
        rows = [[rng.choice(codepoints) for _ in range(rng.choice((1, 2, 2, 3)))]
                for _ in range(rng.choice((1, 2, 2, 3)))]
        parsed = tuple(map(tuple, rows))
        width, height, sizes = L.measure(parsed, signs)
        level = L.fit_level(width, height)
        if level is None or len(group(rows)) == 1:
            continue
        step = L.unit(level)
        (cluster,) = L.layout(group(rows), signs)
        glyph_iter = iter(cluster.glyphs)
        for row, (row_width, _) in zip(rows, sizes):
            for member in row:
                glyph = next(glyph_iter)
                sign = signs[member]
                left = glyph.x + L._round(glyph.scale * (sign.box[0] + sign.box[2]) / 2) - edge \
                    - sign.cell[0] * step // 2
                centred = left - (width * step // 2 - row_width * step // 2)
                check(left in (0, width * step - sign.cell[0] * step) or centred % step == 0,
                      f"{label(group(rows))}: a cell starts off the grid")
                check(isinstance(glyph.x, int) and isinstance(glyph.y, int),
                      f"{label(group(rows))}: a position is not whole")


def test_malformed(signs):
    for codepoints in MALFORMED:
        clusters = L.layout(codepoints, signs)
        check(not any(cluster.stacked for cluster in clusters),
              f"{label(codepoints)}: stacked although malformed or too large")
        for cluster in clusters:
            codepoint = codepoints[cluster.start]
            sign = signs.get(codepoint)
            advance, lift = (sign.advance, sign.lift) if sign else (L.CONTROL_ADVANCE, 0)
            check(cluster.glyphs == (L.Glyph(codepoint, 0, lift, 0, 1.0),)
                  and cluster.advance == advance and cluster.end == cluster.start + 1,
                  f"{label(codepoints)}: U+{codepoint:X} is not drawn as a lone glyph")
        check_visible(codepoints, signs)
    for codepoints, _ in GOLDEN:
        check_visible(codepoints, signs)


def test_random(signs):
    """Random groups and random text: whatever it is, everything stays visible."""
    rng = random.Random(3)
    codepoints = sorted(signs)
    tall = [c for c in codepoints if signs[c].cell[1] == 12]
    levels = {}
    for n in range(1200):  # well-formed groups of one to four rows
        pool = tall if n % 4 == 0 else codepoints
        rows = [[rng.choice(pool) for _ in range(rng.choice((1, 1, 2, 2, 3, 4)))]
                for _ in range(rng.choice((1, 2, 2, 3, 4)))]
        text = group(rows)
        check_visible(text, signs)
        clusters = L.layout(text, signs)
        width, height, _ = L.measure(tuple(map(tuple, rows)), signs)
        level = L.fit_level(width, height)
        if len(text) > 1 and level is not None:
            check(len(clusters) == 1 and clusters[0].stacked
                  and {glyph.level for glyph in clusters[0].glyphs} == {level},
                  f"{label(text)}: not one group at level {level}")
        else:
            check(not any(cluster.stacked for cluster in clusters), f"{label(text)}: stacked")
        levels[level] = levels.get(level, 0) + 1
    check(all(levels.get(level, 0) >= 10 for level in [*range(len(L.LEVEL_HEIGHTS)), None]),
          f"random groups do not reach every level and the caps: {levels}")
    for _ in range(1000):  # any mixture of signs, joiners and other characters
        text = []
        for _ in range(rng.randint(1, 9)):
            kind = rng.random()
            if kind < 0.55:
                text.append(rng.choice(codepoints))
            elif kind < 0.95:
                text.append(rng.choice((V, H)))
            else:
                text.append(rng.choice((0x13432, 0x13436, 0x13437, 0x13438, 0x20)))
        check_visible(text, signs)


def main():
    signs = L.sign_table(SOURCE)
    tests = (test_constants, test_signs, test_grammar, test_golden, test_golden_notices_constants,
             test_owner_rules, test_rounding, test_malformed, test_random)
    for test in tests:
        try:
            test(signs)
        except Exception as error:  # a test that stops is a failure, not a pass
            check(False, f"{test.__name__} stopped: {error!r}")
    for failure in failures[:40]:
        print("FAIL", failure)
    print(f"layout test: {checks} checks, {len(failures)} failed "
          f"({len(GOLDEN)} golden cases, {len(MALFORMED)} malformed inputs)")
    sys.exit(1 if failures else 0)


main()
