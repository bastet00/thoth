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
Z16, D12 = 0x13404, 0x13082  # the lowest cell (one unit), the pupil
FULL_BLANK, HALF_LOST = 0x13441, 0x13444

# Golden cases: text, and for each cluster its advance and its glyphs as
# (code point, x, y, level, scale). The numbers are written here, not read
# from layout.py, so a changed constant or rule fails.
GOLDEN = [
    (  # A1 : O1, figure 11-1 of the Unicode chapter: 20 units high, level 4
        [A1, V, O1],
        [(820, [(A1, 141, 432, 4, 0.598), (O1, 21, -62, 4, 0.564)])],
    ),
    (  # W24 * Z7, figure 11-1: one row with a high sign stands on the baseline
        [W24, H, Z7],
        [(1009, [(W24, 20, -151, 0, 1.0), (Z7, 461, 17, 0, 1.0)])],
    ),
    (  # D21 : N35 "name": two low signs, half the quadrat each
        [D21, V, N35],
        [(1234, [(D21, 28, 604, 0, 1.0), (N35, 18, 202, 0, 1.0)])],
    ),
    (  # F35, I9 : D21 "good": a lone tall sign, then viper over mouth
        [F35, I9, V, D21],
        [(359, [(F35, 0, 0, 0, 1.0)]), (1324, [(I9, 7, 564, 0, 0.872), (D21, 73, 81, 0, 1.0)])],
    ),
    (  # R4 : X1 * Q3 "offering": 7 half units free, bread and stool justified
        [R4, V, X1, H, Q3],
        [(1324, [(R4, 1, 509, 0, 0.99), (X1, 7, -171, 0, 1.0), (Q3, 910, 55, 0, 1.0)])],
    ),
    (  # N35 : N33 * D12: 12 half units free, the most that is justified
        [N35, V, N33, H, D12],
        [(1234, [(N35, 18, 793, 0, 1.0), (N33, 5, 179, 0, 1.0), (D12, 785, 159, 0, 1.0)])],
    ),
    (  # N35 : Q3 * N33: 13 half units free, packed and centred
        [N35, V, Q3, H, N33],
        [(1234, [(N35, 18, 793, 0, 1.0), (Q3, 303, 122, 0, 1.0), (N33, 658, 179, 0, 1.0)])],
    ),
    (  # N35 : N35 : N35 "water": three rows packed, the block centred
        [N35, V, N35, V, N35],
        [(1234, [(N35, 18, 756, 0, 1.0), (N35, 18, 486, 0, 1.0), (N35, 18, 216, 0, 1.0)])],
    ),
    (  # X1 : N35 : X1 : N35: four rows, 14 units, level 1
        [X1, V, N35, V, X1, V, N35],
        [(1052, [(X1, 255, 598, 1, 0.855), (N35, 14, 609, 1, 0.855), (X1, 255, 59, 1, 0.855), (N35, 14, 70, 1, 0.855)])],
    ),
    (  # X1 * Z1: a low row is centred
        [X1, H, Z1],
        [(829, [(X1, 7, 113, 0, 1.0), (Z1, 602, 315, 0, 1.0)])],
    ),
    (  # D58 : N35: a sign higher than the quadrat is reduced first
        [D58, V, N35],
        [(922, [(D58, 194, 423, 2, 0.595), (N35, 16, 87, 2, 0.744)])],
    ),
    (  # two half lost signs over N35, a blank over N35
        [HALF_LOST, H, HALF_LOST, V, N35, FULL_BLANK, V, N35],
        [(1204, [(HALF_LOST, 20, 358, 1, 0.855), (HALF_LOST, 590, 358, 1, 0.855), (N35, 90, 135, 1, 0.855)]),
         (922, [(FULL_BLANK, 26, 412, 2, 0.627), (N35, 16, 87, 2, 0.744)])],
    ),
    (  # the narrowest sign at level 6: rule 5 takes its whole quarter
        [A1, V, A1, V, A1, H, Z15],
        [(379, [(A1, 48, 720, 6, 0.313), (A1, 48, 360, 6, 0.313), (A1, 33, 0, 6, 0.313), (Z15, 317, 0, 6, 0.25)])],
    ),
    (  # the height cap: 36 units, level 6, and 37 units, unstacked
        [A1, V, A1, V, A1, A1, V, A1, V, A1, V, Z16],
        [(349, [(A1, 33, 720, 6, 0.313), (A1, 33, 360, 6, 0.313), (A1, 33, 0, 6, 0.313)]),
         (898, [(A1, 0, 0, 0, 1.0)]), (698, [(V, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)]),
         (698, [(V, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)]), (698, [(V, 0, 0, 0, 1.0)]),
         (513, [(Z16, 0, 316, 0, 1.0)])],
    ),
    (  # the width cap: 64 half units, level 6, and 65, unstacked
        [A1, H, A1, H, A1, H, F35, A1, H, A1, H, A1, H, Q3],
        [(1024, [(A1, 33, 0, 6, 0.313), (A1, 318, 0, 6, 0.313), (A1, 603, 0, 6, 0.313), (F35, 890, 0, 6, 0.27)]),
         (898, [(A1, 0, 0, 0, 1.0)]), (698, [(H, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)]),
         (698, [(H, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)]), (698, [(H, 0, 0, 0, 1.0)]),
         (402, [(Q3, 0, 363, 0, 1.0)])],
    ),
    (  # A1 : Z2, man over plural strokes: 17 units, level 3
        [A1, V, Z2],
        [(634, [(A1, 18, 337, 3, 0.666), (Z2, 41, 23, 3, 0.639)])],
    ),
    (  # A1 : A1, two tall signs: 24 units, level 5
        [A1, V, A1],
        [(482, [(A1, 25, 540, 5, 0.48), (A1, 25, 0, 5, 0.48)])],
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
    [M17, H, SEGMENT, X1, V, N35, V, A1], [X1, OVERLAY, OVERLAY, O1, N35], [A1, INSERT, O1, V, X1],
    [I9, V, N35, V, 0x13113, 0x13433, A1], [*range(0x13430, 0x13441)],
    [A1, V, A1, V, A1, V, A1],  # 48 units high: over the cap
    [N35, H, N35, H, N35],  # 78 half units wide: over the cap
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
        if inserted(codepoints, cluster, signs):
            check_inserted(name, codepoints[cluster.start:cluster.end], cluster, signs)
        elif side_inserted(codepoints, cluster, signs):
            check_side_inserted(name, codepoints[cluster.start:cluster.end], cluster, signs)
        elif cluster.stacked:
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
            crossing = overlay_pairs(codepoints, cluster)  # an overlay's operands cross on purpose
            pairs = [(g, a, h, b) for i, (g, a) in enumerate(zip(cluster.glyphs, inks))
                     for j, (h, b) in enumerate(zip(cluster.glyphs[:i], inks[:i])) if (j, i) not in crossing]
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
    # an inserted sign is inside its base's box: check_inserted() keeps it
    # off the base's ink; here it is checked against everything else
    every = [(ink, overhangs(cluster, glyph), (n, inserted(codepoints, cluster, signs)
                                               or side_inserted(codepoints, cluster, signs), k))
             for n, (cluster, inks) in enumerate(laid) for k, (glyph, ink) in enumerate(zip(cluster.glyphs, inks))]
    crossing = {(n, pair) for n, (cluster, _) in enumerate(laid) for pair in overlay_pairs(codepoints, cluster)}
    check(all(apart(a, b) > 0 for i, (a, one, (n, ins, k)) in enumerate(every)
              for b, other, (m, _, j) in every[:i]
              if not (one or other or (ins and n == m) or (n == m and (n, (j, k)) in crossing))),
          f"{name}: two glyphs overlap")


def test_constants(signs):
    check([L.unit(level) for level in range(len(L.LEVEL_HEIGHTS))] == [90, 77, 67, 60, 54, 45, 30],
          "the seven levels changed")
    check([L.half_unit(level) for level in range(len(L.LEVEL_HEIGHTS))] == [45, 38, 33, 30, 27, 22, 15],
          "the half units changed")
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
    check(digest == "3dfbe9ff0256", f"the sign table changed: {digest}")
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
    fits = {  # (width in half units, height in units) -> level
        (28, 12): 0, (1, 1): 0, (28, 13): 1, (28, 14): 1, (33, 14): 1, (34, 14): 2, (28, 16): 2,
        (38, 1): 2, (39, 1): 3, (42, 1): 3, (43, 1): 4, (46, 1): 4, (47, 1): 5,
        (28, 17): 3, (28, 18): 3, (28, 19): 4, (28, 20): 4, (28, 21): 5, (28, 24): 5,
        (57, 24): 5, (58, 24): 6, (28, 25): 6, (28, 36): 6, (64, 36): 6,
        (65, 1): None, (1, 37): None, (28, 37): None,
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
        "UNIT": 91, "GAP": 33, "HEIGHT_LIMIT": 11, "WIDTH_LIMIT": 27, "SIDE_BEARING": 50,
        "MAX_WIDTH": 63, "MAX_HEIGHT": 35, "MAX_JUSTIFY": 11, "LOW_HEIGHT": 5, "MIDDLE": 524,
        "MOST_REDUCED": 0.7, "CONTROL_ADVANCE": 699,
    }
    changes.update({f"LEVEL_HEIGHTS[{level}]": level for level in range(1, len(L.LEVEL_HEIGHTS))})
    for name, value in changes.items():
        if name.startswith("LEVEL_HEIGHTS"):
            name, kept = "LEVEL_HEIGHTS", L.LEVEL_HEIGHTS
            value = tuple(h + 2 * (i == value) for i, h in enumerate(kept))
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
    # O4: rows of two are justified to the group's edges: on cells, so the
    # ink of each end is within a pixel at 40 pixels to the em (25 units) of
    # the ink of the widest row; single members and rows of three centred
    pixel = 1000 / 40
    for text in ([R4, V, X1, H, Q3], [D4, V, X1, H, Z1], [Q3, H, X1, V, N1], [N16, V, Z1, H, N23]):
        _, inks = stacked(text, signs)
        row = [i for i, c in enumerate(c for c in text if L.is_sign(c)) if c in (X1, Q3, Z1, N23)]
        first, last = inks[row[0]], inks[row[-1]]
        rest = [ink for i, ink in enumerate(inks) if i not in row]
        check(abs(first[0] - min(i[0] for i in rest)) <= pixel
              and abs(max(i[2] for i in rest) - last[2]) <= pixel,
              f"{label(text)}: the row of two is not flush with the edges")
    justified = 0
    for _ in range(3000):  # the same for any justified row against a widest row of one sign
        rows = [[rng.choice(sorted(signs)) for _ in range(rng.choice((1, 2)))] for _ in range(2)]
        parsed = tuple(map(tuple, rows))
        width, _, sizes = L.measure(parsed, signs)
        if L.fit_level(*L.measure(parsed, signs)[:2]) is None:
            continue
        _, inks = stacked(group(rows), signs)
        ends = [inks[:len(rows[0])], inks[len(rows[0]):]]
        for row, (row_width, _), mine, other, other_row in zip(rows, sizes, ends, ends[::-1], rows[::-1]):
            if L.slack(row, width, row_width) and len(other_row) == 1:
                justified += 1
                check(abs(mine[0][0] - other[0][0]) <= pixel and abs(mine[-1][2] - other[0][2]) <= pixel,
                      f"{label(group(rows))}: a justified row is more than a pixel off the edges")
    check(justified > 50, f"only {justified} justified rows")
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
    half units from half the group less half its row (each half rounded
    down); a row stands on its cell bottoms."""
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
        step = L.half_unit(level)  # cells are whole half units wide
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


# --- corner insertion (layout section 6) ---------------------------------------

G1, G7, G17, G25, G39, G43 = 0x1313F, 0x13146, 0x13153, 0x1315C, 0x1316D, 0x13171
M23, D31, D46, I10, AA1 = 0x131D3, 0x13096, 0x130A7, 0x13193, 0x1340D
TS, BS, TE, BE = 0x13432, 0x13433, 0x13434, 0x13435
BIRDS = [c for c in range(0x1313F, 0x1317F)]  # Gardiner G1 to G54

# The owner's cases, as golden lines: for each cluster its advance and its
# glyphs (code point, x, y, level, scale). Written here, not read from
# layout.py. The vulture of mwt and the quail chick shrink to level 1 so
# that the bread reaches level 2 and 3 instead of 5 (half size).
INSERT_GOLDEN = [
    ([G14, TE, X1, B1],  # mwt: vulture with t in its corner, then the woman
     [(1055, [(G14, 76, 0, 1, 0.855), (X1, 547, 649, 2, 0.738)]), (677, [(B1, 0, 0, 0, 1.0)])]),
    ([G43, TE, X1],  # quail chick with t
     [(860, [(G43, 62, -2, 1, 0.855), (X1, 421, 635, 3, 0.665)])]),
    ([G1, TE, X1],  # vulture G1 with t: no shrink, level 3
     [(985, [(G1, 0, 0, 0, 1.0), (X1, 547, 702, 3, 0.665)])]),
    ([G17, TE, X1],  # owl with t
     [(1116, [(G17, 0, 0, 0, 1.0), (X1, 608, 602, 2, 0.738)])]),
    ([G39, TE, Z1],  # sꜣ: the stroke over the duck's tail
     [(1248, [(G39, 0, 0, 0, 1.0), (Z1, 966, 431, 2, 0.723)])]),
    ([M23, G14, TE, X1, N35, G17, D21, D31],  # the TLA's M23-G14-X1:N35-G17-D21-D31
     [(668, [(M23, 0, 0, 0, 1.0)]), (1055, [(G14, 76, 0, 1, 0.855), (X1, 547, 649, 2, 0.738)]),
      (1197, [(N35, 0, 506, 0, 1.0)]), (1116, [(G17, 0, 0, 0, 1.0)]), (1177, [(D21, 0, 385, 0, 1.0)]),
      (740, [(D31, 0, 0, 0, 1.0)])]),
    ([G25, BE, AA1],  # figure 11-2's G25 bottom end: no room, side by side (rule I6)
     [(1318, [(G25, 14, 5, 2, 0.744), (AA1, 805, 61, 2, 0.74)])]),
]

# What v1 does with everything else (rule I1): drawn unstacked, the control
# as its box. A text, and the clusters it must have as (start, end).
INSERT_UNSTACKED = [
    [N35, V, G14, TE, X1], [G14, TE, X1, V, N35], [A1, H, G14, TE, X1],  # base in a group
    [G14, TE, X1, H, Z1], [G14, TE, X1, V, Z1],  # an inserted group
    [G14, TE, X1, BS, Z1], [G14, TE, X1, TE, Z1], [G14, TE, Z1, TE, X1],  # a second insertion
    [TE, X1], [G14, TE], [TE], [G14, TE, TE, X1], [G14, TE, BS, X1],  # malformed
    [G14, TE, 0x200D, X1], [G14, 0x200D, TE, X1], [G14, TE, 0x20, X1],  # broken by other characters
    [G14, TE, X1, OVERLAY, Z1], [SEGMENT, G14, TE, X1, END],  # unsupported controls
]


def inserted(codepoints, cluster, signs):
    """Whether a cluster is a sign inserted into a corner of another."""
    run = codepoints[cluster.start:cluster.end]
    return L.is_insertion(run) and L.insertion(*run, signs) is not None


def base_envelope(glyph, signs):
    """(high, low) of a drawn base (lone or shrunk), in the strips of its
    full-size frame, without its lift."""
    sign = signs[glyph.codepoint]
    transform = L.shrink(sign.box, glyph.level) if glyph.level else (1, 0, 0)
    frame = (sign.box[0], sign.box[1], sign.box[2], max(sign.box[3], L.FRAME_TOP))
    return L._envelope(SOURCE, SOURCE[sign.name], frame, transform)


def check_inserted(name, run, cluster, signs):
    """Rules I1 to I5, said as properties of one insertion."""
    base, control, sign = run
    top, end = L.CORNERS[control]
    b, i = cluster.glyphs
    lift = signs[base].lift
    check(cluster.advance == signs[base].advance, f"{name}: the insertion changes the advance")
    check(i.level in L.INSERT_LEVELS and i.scale == signs[sign].scales[i.level]
          and L.insertable(signs[sign]), f"{name}: the inserted sign is not one of its variants")
    full = L.insert_level(signs[base].corners[control][0][L.shape_of(signs[sign])], signs[sign])
    if b.level:  # I4: a bird that would hold the sign only at half size
        check(base in L.BIRDS and b.level in L.SHRINK_LEVELS and full == L.INSERT_LEVELS[-1]
              and i.level <= L.WANTED_LEVEL, f"{name}: a base shrinks that may not")
        box, scaled = signs[base].box, L.ink_box(b, signs)
        check(abs(scaled[1] - lift - box[1]) <= 1 and abs(scaled[0] + scaled[2] - box[0] - box[2]) <= 2,
              f"{name}: the shrunk base moved")
        smaller = [k for k in L.SHRINK_LEVELS if k < b.level]
        check(all(L.insert_level(signs[base].corners[control][k][L.shape_of(signs[sign])],
                                 signs[sign]) not in range(L.WANTED_LEVEL + 1) for k in smaller),
              f"{name}: the base shrinks more than it must")
    else:
        check(b == L.Glyph(base, 0, lift, 0, 1.0) and i.level == full, f"{name}: the base is not the lone sign")
    ink = L.ink_box(i, signs)
    check(0 <= ink[0] and ink[2] <= cluster.advance, f"{name}: the inserted sign leaves the block")
    check(ink[3] - lift <= max(signs[base].box[3], L.FRAME_TOP) + 2, f"{name}: the inserted sign is above the frame")
    # never on the base's ink; in a top corner seated GAP above it, in a
    # bottom corner on the base's line
    high, low = base_envelope(b, signs)

    def strips(margin):  # the strips within `margin` of the inserted ink
        return [s for s in range(len(high)) if signs[base].box[0] + (s + 1) * L.STRIP > ink[0] - margin
                and signs[base].box[0] + s * L.STRIP < ink[2] + margin]

    if top:  # its width is counted in whole units: up to a STEP more on each side
        near = max((high[s] for s in strips(L.GAP - 2) if high[s] > -1e9), default=None)
        wide = max((high[s] for s in strips(L.GAP + L.STEP + L.STRIP) if high[s] > -1e9), default=None)
        check(near is None or ink[1] - lift - near >= L.GAP - 2, f"{name}: the inserted sign touches the base")
        check(wide is None or ink[1] - lift - wide <= L.GAP + 2,
              f"{name}: the inserted sign floats {ink[1] - lift - (wide or 0):.0f} above the ink under it")
    else:
        over = min((low[s] for s in strips(L.GAP - 2) if low[s] < 1e9), default=None)
        check(over is None or over - (ink[3] - lift) >= L.GAP - 2, f"{name}: the inserted sign touches the base")
        check(abs(ink[1] - lift - signs[base].box[1]) <= 1 or b.level, f"{name}: the inserted sign is off the line")


def test_insertion(signs):
    for codepoints, expected in INSERT_GOLDEN:
        got = result(codepoints, signs)
        check(got == expected, f"{label(codepoints)}:\n  got      {got}\n  expected {expected}")
    for codepoints in INSERT_UNSTACKED:
        clusters = L.layout(codepoints, signs)
        check(not any(cluster.stacked for cluster in clusters), f"{label(codepoints)}: stacked")
        check_visible(codepoints, signs)
    # rule I6: no room, or a sign too large, is the horizontal joiner
    for codepoints in ([D21, TE, X1], [G14, TE, A1], [G25, BE, AA1], [I10, BS, D46], [N35, TS, X1]):
        flat = L.layout([codepoints[0], H, codepoints[2]], signs)
        check(L.insertion(*codepoints, signs) is None and L.layout(codepoints, signs) == flat,
              f"{label(codepoints)}: not side by side")
    outcomes = {}
    rng = random.Random(13)
    small = [c for c in sorted(signs) if L.insertable(signs[c])]
    texts = [[bird, TE, sign] for bird in BIRDS for sign in (X1, Z1)]
    texts += [[base, control, sign] for base in (A1, D21, G1, G17, G43, I10, N35, O1, M17, Q3)
              for control in L.CORNERS for sign in (X1, Z1, Z4, N35, Q3)]
    texts += [[rng.choice(sorted(signs)), rng.choice(list(L.CORNERS)), rng.choice(small)] for _ in range(1500)]
    texts += [[rng.choice(BIRDS), rng.choice(list(L.CORNERS)), rng.choice(small)] for _ in range(500)]
    for text in texts:
        check_visible(text + [0x20, B1], signs)
        found = L.insertion(*text, signs)
        key = "side by side" if found is None else f"base {found[0]}, sign {found[1]}"
        outcomes[key] = outcomes.get(key, 0) + 1
        check(L.layout(text, signs) == L.layout(text, signs), f"{label(text)}: not deterministic")
    check(L.insertion(G14, TE, X1, signs) == (1, 2) and L.insertion(G43, TE, X1, signs) == (1, 3),
          "mwt and the quail chick no longer shrink to level 1")
    check(all(outcomes.get(f"base 0, sign {k}") for k in L.INSERT_LEVELS) and outcomes.get("side by side")
          and all(any(key.startswith(f"base {k},") for key in outcomes) for k in L.SHRINK_LEVELS),
          f"the insertion texts miss an outcome: {outcomes}")
    print(f"  insertions: {len(texts)} texts, " + ", ".join(f"{k}: {n}" for k, n in sorted(outcomes.items())))


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


# --- automatic stacking (layout section 7) ----------------------------------

TE = L.TOP_END
S34, ZWNJ, ZWJ, SPACE = 0x132F9, 0x200C, 0x200D, 0x20
O34, D19, A2, AA1, G43 = 0x13283, 0x13089, 0x13001, 0x1340D, 0x13171  # bolt, nose, man, placenta, quail chick
N37, Y1, V31, F32, D46, A17 = 0x13219, 0x133DB, 0x133A1, 0x13121, 0x130A7, 0x13014
D36, N41 = 0x1309D, 0x1321E  # arm, well

# Plain text, and the text with controls that it must lay out as.
AUTOMATIC = [
    ([R4, X1, Q3], [R4, V, X1, H, Q3]),  # ḥtp "offering"
    ([F35, I9, D21], [F35, I9, V, D21]),  # nfr "good"
    ([S34, N35, 0x1340D], [S34, N35, V, 0x1340D]),  # ꜥnḫ "life"
    ([D21, N35], [D21, V, N35]),  # rn "name"
    ([G14, X1, B1], [G14, TE, X1, B1]),  # mwt "mother": t in the vulture's corner (O5)
    ([R8, M17, X1], [R8, M17, X1]),  # the owner's lone signs (O6): nothing stacks, X1 centred
    ([M17, X1], [M17, X1]),  # jt "father" without its viper: a tall and a low sign stay apart
    ([A1, B1], [A1, B1]),  # two tall signs never stack
    ([F35, F35, F35], [F35, F35, F35]),  # three tall narrow signs
    ([D21, ZWNJ, N35], [D21, ZWNJ, N35]),  # ZWNJ keeps two signs apart
    ([D21, SPACE, N35], [D21, SPACE, N35]),  # and so does a space
    ([D21, ZWJ, N35], [D21, ZWJ, N35]),  # and any other character
    ([R4, X1, Q3, SPACE, F35, I9, D21], [R4, V, X1, H, Q3, SPACE, F35, I9, V, D21]),
    # explicit controls win (rule A5): nothing starts at a sign after a
    # control, and a block that reaches a sign before a control is not formed
    ([R4, V, X1, Q3], [R4, V, X1, Q3]),
    ([F35, I9, D21, V, N35], [F35, I9, D21, V, N35]),
    ([R4, X1, Q3, H, Z1], [R4, X1, Q3, H, Z1]),
    ([F35, I9, V, D21, SPACE, R4, X1, Q3], [F35, I9, V, D21, SPACE, R4, V, X1, H, Q3]),
    # a word typed right after a group, with no space, does not begin a word:
    # rn (a whole word only) is not taken from the list there, but its two
    # half-block signs stack by shape (rule A8); ḥtp also holds where a word
    # ends, so it stacks
    ([F35, I9, V, D21, D21, N35], [F35, I9, V, D21, D21, V, N35]),
    ([F35, I9, V, D21, R4, X1, Q3], [F35, I9, V, D21, R4, V, X1, H, Q3]),
    # inside a run without spaces: nfr holds where a word ends, rn.f too
    ([M17, X1, F35, I9, D21], [M17, X1, F35, I9, V, D21]),
    ([D21, N35, I9], [D21, V, N35, I9]),
    # the owner's bird corners (O5) hold as whole words only
    ([G43, X1], [G43, TE, X1]),
    ([G1, X1], [G1, TE, X1]),
    ([G17, X1], [G17, TE, X1]),
    ([G39, Z1], [G39, TE, Z1]),
    ([D21, G43, X1], [D21, G43, X1]),
    ([G1, X1, N35], [G1, X1, N35]),
    ([G17, X1, SPACE, G39, Z1, D21], [G17, TE, X1, SPACE, G39, Z1, D21]),
    ([G14, TE, X1, D21, N35], [G14, TE, X1, D21, N35]),
    # the shape rule (A7 to A9): two half-block signs in a row, one above the
    # other. The owner's two cases: O34 I9 D19 A2 is the bolt over the viper,
    # then the nose and the man; the dictionary word of his screenshot, O34
    # I9 Aa1 G43 and seven strokes, the same pair and the rest as it is
    ([O34, I9, D19, A2], [O34, V, I9, D19, A2]),
    ([O34, I9, AA1, G43, *[Z1] * 7], [O34, V, I9, AA1, G43, *[Z1] * 7]),
    ([O34, I9, N37], [O34, V, I9, N37]),  # three: a pair and a lone sign
    ([O34, I9, N37, Y1], [O34, V, I9, N37, V, Y1]),  # four: two pairs
    ([N35, N35], [N35, V, N35]),  # a sign doubled is a pair like any other
    ([N35, N35, N35], [N35, V, N35, N35]),  # tripled: a pair and a lone sign
    ([Z2, D21], [Z2, V, D21]),  # the plural strokes are wide: a half-block sign
    ([A1, O34, I9, A1], [A1, O34, V, I9, A1]),  # between tall signs
    # not half-block: narrow low signs, low and tall, two tall wide signs
    ([X1, Z1], [X1, Z1]), ([Q3, X1], [Q3, X1]), ([Z4, X1], [Z4, X1]),
    ([D21, A1], [D21, A1]), ([A1, D21], [A1, D21]), ([G43, G43], [G43, G43]),
    ([X1, N35], [X1, N35]), ([AA1, D21], [AA1, D21]),
    # a run right after a lower sign that is not taken stays as it is (p over n)
    ([Q3, N35, D36], [Q3, N35, D36]),
    ([X1, O34, I9, N37], [X1, O34, I9, N37]),
    ([D19, O34, I9], [D19, O34, I9]),
    ([A2, O34, I9], [A2, O34, V, I9]),  # after a full-height sign it stacks
    # the word list wins: its entries take their signs first (ḥtp, nfr, the
    # owner's ḥjmt), also where they keep two half-block signs apart
    ([R4, X1, Q3, SPACE, O34, I9], [R4, V, X1, H, Q3, SPACE, O34, V, I9]),
    ([R4, X1, Q3, O34, I9], [R4, X1, Q3, O34, I9]),  # ḥtp is a whole word; after Q3 the run stays
    ([F35, I9, D21, N35, SPACE, N35, N35], [F35, I9, V, D21, N35, SPACE, N35, V, N35]),
    ([N41, X1, B1], [N41, V, X1, B1]),
    # the owner, 2026-11-25: ḥtp keeps its p in the block inside a name too
    # (Ptahhotep: p over t, ḥ, the altar over t and p, the man)
    ([Q3, X1, 0x1339B, R4, X1, Q3, A1], [Q3, V, X1, 0x1339B, R4, V, X1, H, Q3, A1]),
    ([R4, X1, Q3, A1], [R4, V, X1, H, Q3, A1]),
    ([F32, D21, D46, G43, A17, Z2], [F32, V, D21, D46, G43, A17, Z2]),
    ([D21, AA1, Y1, V31], [D21, V, AA1, Y1, V31]),
    # explicit controls win; ZWNJ and a space keep signs apart
    ([F35, V, O34, I9, N37], [F35, V, O34, I9, V, N37]),  # nothing starts right after a control
    ([O34, I9, V, N35], [O34, I9, V, N35]),  # a block reaching a control is not formed
    ([O34, I9, N37, H, X1], [O34, V, I9, N37, H, X1]),
    ([O34, H, I9], [O34, H, I9]),
    ([O34, ZWNJ, I9], [O34, ZWNJ, I9]),
    ([O34, SPACE, I9], [O34, SPACE, I9]),
    ([O34, ZWNJ, I9, N37], [O34, ZWNJ, I9, V, N37]),
]


def automatic_text(codepoints, table):
    return L.automatic(codepoints, table)[0]


def test_automatic(signs):
    table = L.automatic_table()
    problems = L.check_table(table, signs)
    check(not problems, f"automatic table: {problems[:5]}")
    for key, arrangement in table.items():  # the notation reads back
        check(L.parse_entry(L.write_entry(key, arrangement)) == (key, arrangement),
              f"{L.write_entry(key, arrangement)} does not read back")
    for plain, expected in AUTOMATIC:
        text, origin = L.automatic(plain, table)
        check(text == expected, f"{label(plain)}: {label(text)}, expected {label(expected)}")
        found = L.layout(plain, signs, table)
        reference = [(c.advance, c.glyphs, c.stacked) for c in L.layout(expected, signs)]
        check([(c.advance, c.glyphs, c.stacked) for c in found] == reference,
              f"{label(plain)}: laid out unlike {label(expected)}")
        # one cluster per group, covering the plain characters it stands for
        check([i for c in found for i in range(c.start, c.end)]
              == [i for i, c in enumerate(plain) if L.is_sign(c) or c in L.CONTROLS],
              f"{label(plain)}: clusters {[(c.start, c.end) for c in found]}")
        check_visible(text, signs)
    # rule A6: every entry, typed plainly as a word, is stacked as its
    # arrangement says and draws no control box
    stacked = 0
    for key, arrangement in table.items():
        plain = [c for c in key if c not in (L.START, L.END)]
        clusters = L.layout(plain, signs, table)
        boxes_ = [g for c in clusters for g in c.glyphs if g.codepoint in L.CONTROLS]
        expected = [c for block in arrangement for c in block]
        check(not boxes_ and automatic_text(plain, table) == expected,
              f"{L.write_entry(key, arrangement)}: {label(automatic_text(plain, table))}")
        stacked += sum(c.stacked for c in clusters)
    # off: without the table, plain text is never stacked
    check(not any(c.stacked for plain, _ in AUTOMATIC if not set(plain) & set(L.CONTROLS)
                  for c in L.layout(plain, signs)),
          "plain text stacked without the table")
    # random plain text and plain text next to controls: deterministic, and
    # everything stays visible
    rng = random.Random(7)
    known = sorted({c for key in table for c in key if c not in (L.START, L.END)})
    others = (V, H, TE, ZWNJ, ZWJ, SPACE, 0x13432, 0x13433, 0x13435)
    for _ in range(1500):
        text = [rng.choice(known) if rng.random() < 0.85 else rng.choice(others)
                for _ in range(rng.randint(1, 12))]
        once, origin = L.automatic(text, table)
        check(once == automatic_text(text, table), f"{label(text)}: not deterministic")
        kept = [i for i in range(len(once)) if i == 0 or origin[i] != origin[i - 1]]
        check([once[i] for i in kept] == text and all(once[i] in L.CONTROLS for i in range(len(once))
                                                      if i not in kept), f"{label(text)}: characters changed")
        check_visible(once, signs)
    # the shape rule (A7 to A9): the owner's case as numbers, the class of
    # half-block signs, and random plain text rich in half-block signs
    found = [(c.advance, list(c.glyphs)) for c in L.layout([O34, I9, D19, A2], signs, table)]
    check(found == [(1324, [(O34, 2, 748, 0, 0.973), (I9, 7, 108, 0, 0.872)]), (794, [(D19, 0, 0, 0, 1.0)]),
                    (859, [(A2, 0, 0, 0, 1.0)])], f"O34 I9 D19 A2: {found}")
    half = [c for c in sorted(signs) if L.half_block(c, signs)]
    check(len(half) == 157 and all(c in L.HIEROGLYPHS and signs[c].cell[1] <= 6 and signs[c].cell[0] >= 14
                                   for c in half), f"{len(half)} half-block signs")
    check(all(L.fit_level(*L.measure(((a,), (b,)), signs)[:2]) == 0 for a in half[::7] for b in half[::5]),
          "a pair of half-block signs is not at level 0")
    lower = [c for c in sorted(signs) if c not in half and signs[c].cell[1] < L.HEIGHT_LIMIT]
    tall = [c for c in sorted(signs) if signs[c].cell[1] >= L.HEIGHT_LIMIT]
    pairs = 0
    for _ in range(1500):
        text = []
        for _ in range(rng.randint(1, 12)):
            r = rng.random()
            text.append(rng.choice(half) if r < 0.6 else rng.choice(lower) if r < 0.72 else rng.choice(tall)
                        if r < 0.82 else rng.choice(known) if r < 0.9 else rng.choice(others))
        once, origin = L.automatic(text, table)
        check(once == L.automatic(list(text), table)[0], f"{label(text)}: not deterministic")
        check_visible(once, signs)
        alone, origin = L.automatic(text, {})  # the shape rule alone: blocks of two half-block signs
        implied = [i for i in range(1, len(alone)) if origin[i] == origin[i - 1]]
        check(all(alone[i] == V and L.half_block(alone[i - 1], signs) and L.half_block(alone[i + 1], signs)
                  and i + 2 not in implied for i in implied), f"{label(text)}: {label(alone)}")
        pairs += len(implied)
    check(pairs > 500, f"random half-block text formed only {pairs} pairs")
    print(f"  automatic: {len(table)} entries, {stacked} groups when typed as words, "
          f"{len(AUTOMATIC)} golden texts; shape rule: {len(half)} half-block signs, {pairs} pairs in random text")


# --- segments and overlay (layout section 8) --------------------------------

SB, SE, OV = L.SEGMENT_START, L.SEGMENT_END, L.OVERLAY
G17, D36, G20, V28, A40 = 0x13153, 0x1309D, 0x13156, 0x1339B, 0x1302D


def box_layers(tree):
    """[(glyph indices of the first operand, of the second)] of each overlay
    of a parsed group, glyphs counted in text order."""
    found, at = [], [0]

    def walk(rows):
        for row in rows:
            for member in row:
                if not isinstance(member, L.Box):
                    at[0] += 1
                elif member.kind == "segment":
                    walk(member.layers[0])
                else:
                    first = sum(len(r) for r in member.layers[0])
                    second = sum(len(r) for r in member.layers[1])
                    found.append((range(at[0], at[0] + first), range(at[0] + first, at[0] + first + second)))
                    at[0] += first + second
    walk(tree)
    return found


def overlay_pairs(codepoints, cluster):
    """{(j, i)}: glyph indices of a stacked cluster that are the two
    operands of one overlay (they cross on purpose, rule N4)."""
    if not cluster.stacked:
        return set()
    tree = L.parse_nested(codepoints[cluster.start:cluster.end])
    if tree is None:
        return set()
    found, at = set(), [0]

    def walk(rows):
        for row in rows:
            for member in row:
                if not isinstance(member, L.Box):
                    at[0] += 1
                elif member.kind == "segment":
                    walk(member.layers[0])
                else:
                    first = sum(len(r) for r in member.layers[0])
                    second = sum(len(r) for r in member.layers[1])
                    found.update((at[0] + j, at[0] + first + i) for j in range(first) for i in range(second))
                    at[0] += first + second
    walk(tree)
    return found


# MdC-like texts for this section: "(" and ")" the segment controls, "##"
# the overlay, ":" and "*" the joiners.
def nested(text):
    codes = {"(": SB, ")": SE, ":": V, "*": H, "#": OV}
    out, token = [], ""
    for char in text.replace("##", "#") + " ":
        if char.isalnum():
            token += char
            continue
        if token:
            out.append(L.code_point(token))
            token = ""
        if char in codes:
            out.append(codes[char])
    return out


NEST_PARSES = [  # text: tree, or None if not well formed (the syntax of section 8)
    ("(Q3:X1)*V28", (((L.Box("segment", (((0x132AA,), (X1,)),)), V28),))),
    ("V28*(Q3:X1)", (((V28, L.Box("segment", (((0x132AA,), (X1,)),))),))),
    ("G17##D36", ((L.Box("overlay", (((G17,),), ((D36,),))),),)),
    ("A1*G17##D36", ((A1, L.Box("overlay", (((G17,),), ((D36,),)))),)),
    ("(Q3*X1)##N35", ((L.Box("overlay", (((0x132AA, X1),), ((N35,),))),),)),
    ("N35##(Q3:X1)", ((L.Box("overlay", (((N35,),), ((0x132AA,), (X1,)))),),)),
    ("((Q3:X1)*Z1:N35)*A1", None),  # a segment as the first of two: fine, and depth 2
    ("(Q3:X1)", None), ("(Q3*X1)*A1", None), ("((Q3:X1):N35)*A1", None),  # not a vertical group in a row
    ("(Q3:X1", None), ("Q3:X1)", None), ("()*A1", None), ("(Q3:)*A1", None),
    ("G17##D36##N35", None), ("(G17:D36)##N35", None), ("N35##(Q3*X1)", None), ("##N35", None), ("N35##", None),
    ("(((Q3:X1)*Z1:N35)*A1:N35)*A1", None),  # three deep: beyond MAX_DEPTH
    ("((Q3##X1)*Z1:N35)*A1", None),  # an overlay three deep
    ("Q3:X1", None),  # no segment or overlay control: section 4's parse
]
if L.MAX_DEPTH >= 2:  # a segment in a segment
    NEST_PARSES[6] = ("((Q3:X1)*Z1:N35)*A1", ((L.Box("segment", ((
        (L.Box("segment", (((0x132AA,), (X1,)),)), Z1), (N35,)),)), A1),))
    NEST_PARSES.append(("(Q3##X1:N35)*A1", ((L.Box("segment", (((L.Box("overlay", (((0x132AA,),), ((X1,),))),),
                                                                (N35,)),)), A1),)))
else:
    NEST_PARSES.append(("(Q3##X1:N35)*A1", None))  # an overlay in a segment: depth 2

NEST_GOLDEN = [  # text: [(advance, [(code point, x, y, level, scale)])], checked by eye on the proof sheets
    ("(Q3:X1)*V28", [(1054, [(0x132AA, 122, 578, 0, 1.0), (X1, 7, -126, 0, 1.0), (V28, 600, 3, 0, 1.0)])]),
    ("G17##D36", [(1324, [(G17, 104, 18, 0, 1.0), (D36, 7, 270, 0, 0.87)])]),
    ("M17*(Y5:N35)", [(1318, [(M17, 19, 0, 1, 0.855), (0x133E0, 277, 281, 1, 0.855), (N35, 280, 154, 1, 0.855)])]),
    ("N35##(Q3:X1)", [(1234, [(N35, 18, 351, 0, 1.0), (0x132AA, 415, 384, 0, 1.0), (X1, 300, -202, 0, 1.0)])]),
    ("(Q3*X1)##N35", [(1234, [(0x132AA, 123, 339, 0, 1.0), (X1, 480, 113, 0, 1.0), (N35, 18, 486, 0, 1.0)])]),
    ("A1*G17##D36", [(1098, [(A1, 25, 0, 5, 0.48), (G17, 487, 9, 5, 0.485), (D36, 452, 135, 5, 0.406)])]),
]

NEST_UNSTACKED = [  # well formed, but a box or the group is too large (rule N2)
    "(G17:D36)*A1", "A1*(N35:N35:N35:N35:N35*N35)", "(A1*A1*A1:X1)*Z1",
]


def test_nesting(signs):
    for text, expected in NEST_PARSES:
        found = L.parse_nested(nested(text))
        check(found == expected, f"parse_nested {text}: {found}")
    for text, expected in NEST_GOLDEN:
        got = result(nested(text), signs)
        check(got == expected, f"{text}:\n  got      {got}\n  expected {expected}")
    for text in [t for t, tree in NEST_PARSES if tree is None and any(c in L.NESTING for c in nested(t))] + NEST_UNSTACKED:
        clusters = L.layout(nested(text), signs)
        check(not any(c.stacked for c in clusters), f"{text}: stacked although malformed or too large")
        check_visible(nested(text), signs)
    # Ptah, the owner's example: p over t beside the tall h, all full size
    (ptah,) = L.layout(nested("(Q3:X1)*V28"), signs)
    p, t, h = ptah.glyphs
    inks = [L.ink_box(g, signs) for g in ptah.glyphs]
    check({g.level for g in ptah.glyphs} == {0}, "Ptah: not at full size")
    check(inks[0][1] - inks[1][3] >= L.GAP and inks[0][3] <= inks[2][3] + 2 and inks[1][1] >= inks[2][1] - 2,
          "Ptah: p is not over t, within the height of h")
    check(abs((inks[0][0] + inks[0][2]) - (inks[1][0] + inks[1][2])) <= 2, "Ptah: p and t are not centred on each other")
    check(inks[2][0] - max(inks[0][2], inks[1][2]) >= L.GAP - 2, "Ptah: h is not beside p and t")
    margins = (TOP - (inks[0][3] + 0), inks[1][1])
    # N3: two rows share the free height as in the quadrat: as much room above p as below t (cells)
    # G17 + D36 is arranged like the ready-made sign G20: the arm across the owl, both full size
    (owl,) = L.layout(nested("G17##D36"), signs)
    a, b = (L.ink_box(g, signs) for g in owl.glyphs)
    check(owl.glyphs[0].level == 0 and owl.glyphs[0].scale == 1.0, "G17 + D36: the owl is not full size")
    check(a[1] < b[1] < b[3] < a[3] and a[0] < (b[0] + b[2]) / 2 < a[2], "G17 + D36: the arm does not cross the owl")
    # N4: the cells of two operands share their centre
    for text in ("G17##D36", "N35##(Q3:X1)", "(Q3*X1)##N35", "A1*X1##Z1:N35", "(Q3:X1)*A1##D21"):
        (cluster,) = [c for c in L.layout(nested(text), signs) if c.stacked]
        k = cluster.glyphs[0].level
        step, up = L.half_unit(k), L.unit(k)
        for first, second in box_layers(L.parse_nested(nested(text))):
            centres = []
            for part in (first, second):
                cells = []
                for g in (cluster.glyphs[j] for j in part):
                    dx, dy = L.sign_offset(signs[g.codepoint], k)
                    a, b = signs[g.codepoint].cell
                    left, line = g.x - dx - L.half(a, step), g.y - dy
                    cells.append((left, line, left + a * step, line + b * up))
                centres.append(((min(c[0] for c in cells) + max(c[2] for c in cells)) / 2,
                                (min(c[1] for c in cells) + max(c[3] for c in cells)) / 2))
            check(abs(centres[0][0] - centres[1][0]) <= 1 and abs(centres[0][1] - centres[1][1]) <= up / 2 + 1,
                  f"{text}: the operands are not centred on each other: {centres}")
    # random well-formed and broken nested groups: everything stays visible,
    # a well-formed one that fits is one group at one level
    rng = random.Random(29)
    codepoints = sorted(signs)
    small = [c for c in codepoints if signs[c].cell[1] <= 6]
    narrow = [c for c in small if signs[c].cell[0] <= 14]  # two of them fit a box
    outcomes = {}

    def sign(depth=1):
        r = rng.random()
        return rng.choice(narrow if depth and r < 0.7 else small if r < 0.8 else codepoints)

    def member(depth):  # now and then one deeper than the font goes
        r = rng.random()
        if (depth < L.MAX_DEPTH or rng.random() < 0.1) and depth <= L.MAX_DEPTH and r < 0.25:
            rows = [row(depth + 1) for _ in range(rng.choice((2, 2, 3)))]
            return [SB] + sum(([V] + x for x in rows[1:]), rows[0]) + [SE]
        if (depth < L.MAX_DEPTH or rng.random() < 0.1) and depth <= L.MAX_DEPTH and r < 0.4:
            left = [sign()] if rng.random() < 0.6 else [SB, sign(), H, sign(), SE]
            right = [sign()] if rng.random() < 0.6 else [SB, sign(), V, sign(), SE]
            return left + [OV] + right
        return [sign(depth)]

    def row(depth):
        members = [member(depth) for _ in range(rng.choice((1, 2, 2, 3) if depth else (1, 2, 2)))]
        return sum(([H] + m for m in members[1:]), members[0])

    for n in range(1500):
        rows = [row(0) for _ in range(rng.choice((1, 1, 2)))]
        text = sum(([V] + r for r in rows[1:]), rows[0])
        if n % 3 == 0:  # broken: a control added or taken away
            i = rng.randrange(len(text) + 1)
            if rng.random() < 0.5 and len(text) > 1:
                del text[min(i, len(text) - 1)]
            else:
                text.insert(i, rng.choice((SB, SE, OV, V, H)))
        check_visible(text, signs)
        tree = L.parse_nested(text)
        clusters = L.layout(text, signs)
        if tree is not None and L.boxes_fit(tree, signs) and L.fit_level(*L._rows_size(tree, signs)[:2]) is not None:
            check(len(clusters) == 1 and clusters[0].stacked and len({g.level for g in clusters[0].glyphs}) == 1,
                  f"{label(text)}: not one group at one level")
            outcomes["stacked"] = outcomes.get("stacked", 0) + 1
        elif any(c in L.NESTING for c in text):
            outcomes["unstacked"] = outcomes.get("unstacked", 0) + 1
    check(outcomes.get("stacked", 0) > 150 and outcomes.get("unstacked", 0) > 300, f"random nested: {outcomes}")
    print(f"  segments and overlay: {len(NEST_PARSES)} parses, {len(NEST_GOLDEN)} golden, random {outcomes}")


# --- insertion at middle, top and bottom (layout section 9) ------------------

def side_inserted(codepoints, cluster, signs):
    """Whether a cluster is a sign inserted at the middle, top or bottom of another."""
    run = codepoints[cluster.start:cluster.end]
    return L.is_side_insertion(run) and L.side_insertion(*run, signs) is not None


def check_side_inserted(name, run, cluster, signs):
    """Rules S1 to S4, said as properties of one insertion."""
    base, control, sign = run
    b, i = cluster.glyphs
    lift = signs[base].lift
    check(cluster.advance == signs[base].advance and b == L.Glyph(base, 0, lift, 0, 1.0),
          f"{name}: the base is not the lone sign")
    check(i.level in L.SIDE_LEVELS and i.scale == signs[sign].scales[i.level], f"{name}: not a variant")
    ink = L.ink_box(i, signs)
    box = signs[base].box
    check(box[0] - 1 <= ink[0] and ink[2] <= box[2] + 1 and box[1] - 1 <= ink[1] - lift and ink[3] - lift <= box[3] + 1,
          f"{name}: the inserted sign leaves the base's ink box")
    # never on the base's ink (measured on lines LINE apart: up to LINE closer)
    ys = [y for y in range(box[1], box[3]) if ink[1] - lift - L.GAP + L.LINE + 2 <= y <= ink[3] - lift + L.GAP - L.LINE - 2]
    pen = L._Lines(SOURCE, ys or [box[1]])
    SOURCE[signs[base].name].draw(pen)
    lines = pen.ink() if ys else {}
    near = [(y, a, c) for y, found in lines.items() for a, c in found
            if a < ink[2] + L.GAP - 2 and c > ink[0] - L.GAP + 2]
    check(not near, f"{name}: the inserted sign comes within GAP of the base's ink")
    zone = signs[base].corners[control][0][L.shape_of(signs[sign])]
    check(abs((ink[0] + ink[2]) / 2 - zone.x) <= 1, f"{name}: the inserted sign is not centred on its zone")
    if control == L.MIDDLE_INSERT:
        check(abs((ink[1] + ink[3]) / 2 - lift - zone.y) <= L.STEP / 2 + 1, f"{name}: not in the middle of its zone")
    elif control == L.BOTTOM_INSERT:
        check(abs(ink[1] - lift - box[1]) <= 1, f"{name}: not on the base's line")


O6, O1, D28 = 0x13257, 0x13250, 0x13093
SIDE_GOLDEN = [  # checked by eye on the proof sheets
    ([O6, 0x13439, R8], [(839, [(O6, 0, 0, 0, 1.0), (R8, 295, 434, 5, 0.425)])]),  # the house of the god
    ([O1, 0x13439, X1], [(1377, [(O1, 0, 0, 0, 1.0), (X1, 455, 194, 2, 0.738)])]),
    ([D28, 0x1343A, Z1], [(703, [(D28, 0, 0, 0, 1.0), (Z1, 276, 135, 2, 0.723)])]),
    ([0x132DE, 0x1343B, X1], [(1306, [(0x132DE, 0, 0, 0, 1.0), (X1, 443, -120, 3, 0.665)])]),
]


def test_side_insertion(signs):
    for codepoints, expected in SIDE_GOLDEN:
        got = result(codepoints, signs)
        check(got == expected, f"{label(codepoints)}:\n  got      {got}\n  expected {expected}")
    m, t, b = L.SIDES
    unstacked = [[m, X1], [O6, m], [m], [O6, m, m, X1], [O6, m, X1, V, N35], [O6, m, X1, m, Z1],
                 [O6, 0x200D, m, X1], [O6, m, 0x20, X1], [SB, O6, m, X1, SE], [O6, m, X1, OV, Z1]]
    for codepoints in unstacked:
        check(not any(c.stacked for c in L.layout(codepoints, signs)), f"{label(codepoints)}: stacked")
        check_visible(codepoints, signs)
    rng = random.Random(31)
    codepoints = sorted(signs)
    small = [c for c in codepoints if L.insertable(signs[c])]
    outcomes = {}
    for _ in range(3000):
        control = rng.choice(L.SIDES)
        having = [c for c in codepoints if signs[c].corners[control][0]["flat"].width]
        text = [rng.choice(having if rng.random() < 0.7 else codepoints), control,
                rng.choice(small if rng.random() < 0.7 else codepoints)]
        check_visible(text, signs)
        found = L.side_insertion(*text, signs)
        key = f"{'mtb'[L.SIDES.index(text[1])]} " + ("side by side" if found is None else "inserted")
        outcomes[key] = outcomes.get(key, 0) + 1
    zones = {c: sum(bool(signs[x].corners[c][0]["flat"].width) for x in signs) for c in L.SIDES}
    check(all(outcomes.get(f"{k} inserted", 0) > 20 for k in "mtb"), f"side insertions: {outcomes}")
    print(f"  side insertions: bases with a zone (flat) m/t/b {list(zones.values())}, random {outcomes}")


# --- enclosures (layout section 10) ------------------------------------------

BEGIN, END_ENC, BEGIN_W, END_W = 0x1343C, 0x1343D, 0x1343E, 0x1343F
V11A, V11B, V11D, O6A, O6D, O36A, O36B, O36C, O36D = (
    0x13379, 0x1337A, 0x1342F, 0x13258, 0x1325B, 0x13286, 0x13287, 0x13288, 0x13289)
AA1, G43, G38, N5 = 0x1340D, 0x13171, 0x1316C, 0x131F3
KHUFU = [V11A, BEGIN, AA1, G43, I9, G43, END_ENC, V11B]
ENCLOSURE_GOLDEN = [  # text, and per cluster (start, end, advance, glyphs, frame); written here
    (KHUFU, [
        (0, 2, 617, [], [(("piece", V11A), 0, 0)]),
        (2, 3, 694, [(AA1, 9, 83, 0, 1.0)], [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 694, 0)]),
        (3, 4, 874, [(G43, 7, 13, 0, 1.0)], [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 874, 0)]),
        (4, 5, 1324, [(I9, 7, 325, 0, 0.872)],
         [(("line", "plain", 1024, "start"), 0, 0), (("line", "plain", 1024, "end"), 1324, 0)]),
        (5, 6, 874, [(G43, 7, 13, 0, 1.0)], [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 874, 0)]),
        (6, 8, 617, [], [(("piece", V11B), 0, 0)]),
    ]),
    ([BEGIN_W, D21, V, N35, END_W], [  # no delimiters: the lines alone, the controls empty clusters
        (0, 1, 0, [], []),
        (1, 4, 1234, [(D21, 28, 604, 0, 1.0), (N35, 18, 202, 0, 1.0)],
         [(("line", "walled", 1024, "start"), 0, 0), (("line", "walled", 1024, "end"), 1234, 0),
          (("merlons", "walled", 8), 617, 0)]),
        (4, 5, 0, [], []),
    ]),
]
ENCLOSURE_UNFORMED = [  # rule E1: nothing forms; every control a box, every delimiter a lone sign
    [V11A, BEGIN, AA1, G43], [BEGIN, AA1], [AA1, END_ENC, V11B], [V11A, END_ENC, AA1, BEGIN, V11B],
    [V11A, BEGIN, END_ENC, V11B], [BEGIN, END_ENC], [V11A, BEGIN, AA1, END_W, V11B],
    [V11A, BEGIN, AA1, 0x20, G43, END_ENC, V11B], [V11A, BEGIN, AA1, 0x200D, G43, END_ENC, V11B],
    [V11A, BEGIN, 0x200C, AA1, END_ENC, V11B], [O36C, BEGIN_W, AA1, BEGIN_W, END_W, O36D],
    [V11A, BEGIN, G38, 0x13434, X1, END_ENC, V11B],  # rule E5: the pintail with t is too tall
]


def enclosure_text(rng, codepoints):
    text = [rng.choice(codepoints) for _ in range(rng.randint(0, 2))]
    plain = rng.random() < 0.7
    if rng.random() < 0.85:
        text.append(rng.choice(L.OPENINGS))
    text.append(BEGIN if plain else BEGIN_W)
    for _ in range(rng.randint(1, 6)):
        r = rng.random()
        if r < 0.4:
            text.append(rng.choice(codepoints))
        elif r < 0.75:
            text += group([[rng.choice(codepoints) for _ in range(rng.randint(1, 2))] for _ in range(rng.randint(1, 3))])
        elif r < 0.9:
            text += [rng.choice(codepoints), rng.choice(list(L.CORNERS)), rng.choice(codepoints)]
        else:
            text.append(rng.choice((V, H, 0x13437, 0x20, BEGIN, END_ENC)))
    text.append(END_ENC if plain else END_W)
    if rng.random() < 0.85:
        text.append(rng.choice(L.CLOSINGS))
    return text


def check_enclosed(codepoints, signs, table=None):
    """Rules E1 to E7 as properties of a laid-out text; returns whether an
    enclosure formed."""
    name = label(codepoints)
    clusters = L.layout(codepoints, signs, table)
    check([i for c in clusters for i in range(c.start, c.end)]
          == [i for i, c in enumerate(codepoints) if L.is_sign(c) or c in L.CONTROLS],
          f"{name}: the clusters do not cover the text in order")
    drawn = sorted([g.codepoint for c in clusters for g in c.glyphs if L.is_sign(g.codepoint)]
                   + [f.part[1] for c in clusters for f in c.frame if f.part[0] == "piece"])
    check(drawn == sorted(c for c in codepoints if L.is_sign(c)), f"{name}: a sign is lost or doubled")
    formed = False
    for c in clusters:
        lines = [f for f in c.frame if f.part[0] == "line"]
        if not lines:
            continue
        formed = True
        (start, end) = sorted(lines, key=lambda f: f.part[3] != "start")
        length = start.part[2]
        check(start.x == 0 and end.x == c.advance and length <= c.advance <= 2 * length,
              f"{name}: the lines under the cluster at {c.start} leave a gap")
        merlons = [f for f in c.frame if f.part[0] == "merlons"]
        check(len(merlons) == (start.part[1] == "walled" and L.merlon_count(c.advance) > 0),
              f"{name}: merlons at {c.start}")
        inks = [L.ink_box(g, signs) for g in c.glyphs]
        check(all(-2 <= ink[1] and ink[3] <= L.ENCLOSED_TOP + 2 for ink in inks),
              f"{name}: the ink of the cluster at {c.start} leaves the inside of the ring")
        check(all(g.level is not None and (c.stacked or g.codepoint not in signs) for g in c.glyphs),
              f"{name}: a lone sign inside an enclosure")
    return formed


def test_enclosures(signs):
    check(L.band_edges("plain") == (-106, -86, -53, -34, 1080, 1099, 1132, 1152)
          and L.band_edges("walled") == (-123, -100, -58, -34, 1080, 1105, 1147, 1171)
          and L.merlon_size() == (105, 42, 63), "the ring changed")
    rings = L.default_rings()
    check([rings[c].advance for c in (V11A, O6A, O36A, O36C)] == [617, 617, 881, 640]
          and all(r.bands[3] * r.scale + r.dy == L.INNER[0] for r in rings.values()), "the delimiters changed")
    for text, expected in ENCLOSURE_GOLDEN:
        got = [(c.start, c.end, c.advance, [tuple(g) for g in c.glyphs], [tuple(f) for f in c.frame])
               for c in L.layout(text, signs)]
        check(got == expected, f"{label(text)}:\n  got      {got}\n  expected {expected}")
        check(check_enclosed(text, signs), f"{label(text)}: no enclosure")
    for text in ENCLOSURE_UNFORMED:
        clusters = L.layout(text, signs)
        check(not any(c.frame for c in clusters), f"{label(text)}: an enclosure formed")
        check(all(c.glyphs == (L.Glyph(text[c.start], 0, 0, 0, 1.0),) for c in clusters if text[c.start] in L.ENCLOSURE),
              f"{label(text)}: a control is not its box")
        check_enclosed(text, signs)
    # nested: the inner pair forms, the outer one does not
    nested = [V11A, BEGIN, N5, BEGIN_W, AA1, END_W, G43, END_ENC, V11B]
    frames = [f.part[1] for c in L.layout(nested, signs) for f in c.frame if f.part[0] == "line"]
    check(frames == ["walled", "walled"], f"nested: {frames}")
    # rule E2: no group and no word reaches across an enclosure control or a delimiter
    for text in ([X1, V, BEGIN, N35, END_ENC], [V11A, V, BEGIN, X1, END_ENC], [BEGIN, X1, END_ENC, H, V11B]):
        check(not any(c.stacked and len(c.glyphs) > 1 for c in L.layout(text, signs)), f"{label(text)}: joined across")
    table = L.automatic_table()
    word = [c for c in next(iter(sorted(table, key=str))) if c not in (L.START, L.END)]
    inside = L.layout([V11A, BEGIN, *word, END_ENC, V11B], signs, table)
    alone = L.layout(word, signs, table)
    check([len(c.glyphs) for c in inside[1:-1]] == [len(c.glyphs) for c in alone],
          f"a word of the table is stacked differently inside a cartouche")
    # a group inside is the group outside; a lone sign is a group of one
    for text in ([X1, V, N35], [R4, V, X1, H, Q3], [A1]):
        inside = L.layout([BEGIN, *text, END_ENC], signs)[1]
        outside = L.layout(text, signs)[0] if len(text) > 1 else L._stacked(0, 1, ((A1,),), 0, signs)
        check(inside.glyphs == outside.glyphs and inside.advance == outside.advance, f"{label(text)} inside")
    rng = random.Random(41)
    codepoints = sorted(signs)
    formed = sum(check_enclosed(enclosure_text(rng, codepoints), signs, table if n % 2 else None)
                 for n in range(800))
    check(formed > 300, f"only {formed} random texts formed an enclosure")
    print(f"  enclosures: {len(ENCLOSURE_GOLDEN)} golden, {len(ENCLOSURE_UNFORMED)} unformed, 800 random texts "
          f"({formed} with an enclosure)")


# --- sign modifiers: mirroring and damage (layout section 11) ---------------

MIR, DAMAGED = 0x13440, 0x13455  # the mirror control; damage at all four quarters
TOP_START_D, BOTTOM_D, BS_TE_D = 0x13447, 0x13450, 0x1344C  # 1; 2 + 8; 2 + 4
G1_, VS1 = 0x1313F, 0xFE00


def piece(quarter, across, up):
    return L.HATCH + (quarter << 12) + (across << 6) + up


# Golden cases, written here: (code point, x, y, level, scale) per glyph; a
# negative scale is a sign mirrored across the middle of its ink.
MODIFIER_GOLDEN = [
    ([A1, MIR],  # a lone sign mirrored: ink 49..849, so moved by 898
     [(898, [(A1, 898, 0, 0, -1.0)])]),
    ([A1, DAMAGED],  # all four quarters of A1's cell (19 x 12): 10 by 12 tiles from its middle
     [(898, [(A1, 0, 0, 0, 1.0), (piece(1, 10, 12), 449, 540, 0, 1.0), (piece(2, 10, 12), 449, 540, 0, 1.0),
             (piece(4, 10, 12), 449, 540, 0, 1.0), (piece(8, 10, 12), 449, 540, 0, 1.0)])]),
    ([X1, BS_TE_D],  # bottom start and top end of the bread's cell (13 x 4), lifted with the bread
     [(633, [(X1, 0, 189, 0, 1.0), (piece(2, 7, 4), 316, 571, 0, 1.0), (piece(4, 7, 4), 316, 571, 0, 1.0)])]),
    ([D21, BOTTOM_D, V, N35],  # rn with the mouth damaged at the bottom: in its cell in the group
     [(1234, [(D21, 28, 604, 0, 1.0), (piece(2, 13, 4), 617, 779, 0, 1.0), (piece(8, 13, 4), 617, 779, 0, 1.0),
              (N35, 18, 202, 0, 1.0)])]),
    ([D21, MIR, V, N35],  # the mouth is symmetric: drawn as it is, the control draws nothing
     [(1234, [(D21, 28, 604, 0, 1.0), (N35, 18, 202, 0, 1.0)])]),
    ([A1, MIR, V, O1],  # level 4 has no mirrored variants: the sign as it is, the small box over its middle
     [(820, [(A1, 141, 432, 4, 0.598), (MIR, 323, 631, 0, 0.25), (O1, 21, -62, 4, 0.564)])]),
    ([G1_, MIR, TS, X1],  # the vulture turned, the bread on its back at the line's start (rule M5)
     [(985, [(G1_, 986, 0, 0, -1.0), (X1, 19, 702, 3, 0.665)])]),
    ([A1, MIR, TE, X1],  # a corner after another mirrored sign: unsupported, unstacked
     [(898, [(A1, 898, 0, 0, -1.0)]), (698, [(MIR, 0, 0, 0, 1.0)]), (633, [(X1, 0, 189, 0, 1.0)])]),
    ([A1, TOP_START_D, MIR],  # the mirror after the damage: a stray control
     [(898, [(A1, 0, 0, 0, 1.0), (piece(1, 10, 12), 449, 540, 0, 1.0)]), (698, [(MIR, 0, 0, 0, 1.0)])]),
    ([TOP_START_D, A1],  # a damage modifier with no sign before it: its box
     [(698, [(TOP_START_D, 0, 0, 0, 1.0)]), (898, [(A1, 0, 0, 0, 1.0)])]),
]


def strip(text):
    """The text without the modifiers that follow a hieroglyph (no
    ignorables in these texts), corner controls after a mirrored sign as
    rule M5 reads them (and side controls after one): what the stacking
    rules must see."""
    out, after, turned = [], None, None
    for c in text:
        if c in L.MODIFIERS and after is not None and (c == MIR and after == "sign" or c in L.DAMAGE and after
                                                         in ("sign", "mirror")):
            after = "mirror" if c == MIR else "done"
            if c == MIR and not L.symmetric(out[-1]):
                turned = out[-1]
            continue
        if c in L.SWAPPED and turned is not None:
            c = L.SWAPPED[c] if turned in L.BIRDS else MIR
        elif c in L.SIDES and turned is not None:
            c = MIR
        after, turned = ("sign" if c in L.HIEROGLYPHS else None), None
        out.append(L.STRAY if c in L.DAMAGE else c)
    return out


def test_modifiers(signs):
    for codepoints, expected in MODIFIER_GOLDEN:
        got = result(codepoints, signs)
        check(got == expected, f"{label(codepoints)}:\n  got      {got}\n  expected {expected}")
    # rule M1: what belongs to a sign
    lits = {
        (A1, MIR, TOP_START_D): {0: (1, 2)}, (A1, TOP_START_D, MIR): {0: (None, 1)}, (A1, MIR, MIR): {0: (1, None)},
        (A1, VS1, MIR): {0: (2, None)}, (A1, 0x200D, MIR): {}, (A1, MIR, 0x200C, TOP_START_D): {0: (1, None)},
        (FULL_BLANK, MIR): {}, (MIR, A1): {}, (A1, V, MIR): {}, (A1, MIR, VS1, TOP_START_D): {0: (1, 3)},
    }
    for text, expected in lits.items():
        check(L.literals(list(text)) == expected, f"literals {label(text)}: {L.literals(list(text))}")
    hieroglyphs = [c for c in sorted(signs) if c in L.HIEROGLYPHS]
    symmetric = [c for c in hieroglyphs if L.symmetric(c)]
    check(len(symmetric) == 254 and N35 in symmetric and D21 in symmetric and A1 not in symmetric,
          f"{len(symmetric)} symmetric signs")
    # random text: the modifiers change nothing but the drawing (rule M2),
    # a mirrored sign keeps its ink box (M4), the pieces of a damaged sign
    # meet at the middle of its cell and stay near it (M6, M7), each
    # literal is in one cluster, and nothing is hidden
    rng = random.Random(31)
    tall = [c for c in hieroglyphs if signs[c].cell[1] == 12]
    small = [c for c in hieroglyphs if L.insertable(signs[c])]
    pool = (MIR, MIR, *L.DAMAGE, V, H, TE, TS, 0x20)
    counts = {"mirrored": 0, "pieces": 0, "boxes": 0}
    for n in range(2500):
        text = []
        for _ in range(rng.randint(1, 7)):
            r = rng.random()
            if r < 0.6:
                text.append(rng.choice(tall if r < 0.15 else small if r < 0.3 else hieroglyphs))
                text += [MIR] * (rng.random() < 0.3) + [rng.choice(L.DAMAGE)] * (rng.random() < 0.3)
            else:
                text.append(rng.choice(pool))
        laid = L.layout(text, signs)
        plain = L.layout(strip(text), signs, modifiers=False)
        kept = [[g for g in c.glyphs if not L.is_hatch(g.codepoint) and not (g.codepoint == MIR and
                                                                              g.scale == L.MIRROR_BOX)]
                for c in laid]
        unturned = [[g._replace(x=g.x - L._round(-g.scale * (signs[g.codepoint].box[0] + signs[g.codepoint].box[2])),
                                scale=-g.scale) if g.scale < 0 else g for g in glyphs] for glyphs in kept]
        boxes_ = [(c.advance, tuple(g)) for c, g in zip(laid, unturned) if c.glyphs[0].codepoint not in L.DAMAGE]
        check(boxes_ == [(c.advance, c.glyphs) for c in plain], f"{label(text)}: the modifiers move a sign")
        for c in laid:
            for g in c.glyphs:
                if g.scale < 0:
                    counts["mirrored"] += 1
                    flipped, unflipped = L.ink_box(g, signs), L.ink_box(L.mirrored_glyph(g, signs)._replace(
                        x=g.x - L._round(-g.scale * (signs[g.codepoint].box[0] + signs[g.codepoint].box[2]))), signs)
                    check(all(abs(a - b) <= 1 for a, b in zip(flipped, unflipped)), f"{label(text)}: a mirror moved the ink")
            counts["boxes"] += sum(g.codepoint == MIR and g.scale == L.MIRROR_BOX for g in c.glyphs)
            runs_, quarters = [], []  # the pieces after each sign
            for g in c.glyphs:
                if L.is_hatch(g.codepoint):
                    quarters.append((L.hatch_piece(g.codepoint)[0], g.x, g.y))
                elif not (g.codepoint == MIR and g.scale == L.MIRROR_BOX):
                    runs_.append(quarters)
                    quarters = []
            runs_.append(quarters)
            for quarters in runs_:
                counts["pieces"] += len(quarters)
                check([q for q, _, _ in quarters] == sorted({q for q, _, _ in quarters})
                      and len({(x, y) for _, x, y in quarters}) <= 1,
                      f"{label(text)}: the pieces of a sign are doubled, out of order or apart")
        # each literal is inside the cluster of its sign; a stray modifier is a box of its own
        for index, (mirror, damage) in L.literals(text).items():
            (owner,) = [c for c in laid if c.start <= index < c.end]
            check(all(i is None or owner.start <= i < owner.end for i in (mirror, damage)),
                  f"{label(text)}: a modifier is not in its sign's cluster")
        taken = {i for pair in L.literals(text).values() for i in pair if i is not None}
        for index, c in enumerate(text):
            if c in L.MODIFIERS and index not in taken:
                check(any(cl.start == index and cl.glyphs[0].codepoint == c for cl in laid),
                      f"{label(text)}: a stray modifier at {index} has no box")
    check(counts["mirrored"] > 500 and counts["pieces"] > 1000 and counts["boxes"] > 10,
          f"random modified text reaches too few cases: {counts}")
    # the pieces of a damaged sign: from the middle of its cell, within half a
    # tile (or the one tile at least) of the cell's edges
    for c in hieroglyphs[::3]:
        sign = signs[c]
        for k in range(len(L.LEVEL_HEIGHTS)):
            across, up, middle = L.damage_size(sign, k)
            width, height = sign.cell[0] * L.half_unit(k), sign.cell[1] * L.unit(k)
            slack = L.HATCH_TILE / 2 + 1
            check(abs(across * L.HATCH_TILE - width / 2) <= max(slack, L.HATCH_TILE - width / 2)
                  and abs(up * L.HATCH_TILE - height / 2) <= max(slack, L.HATCH_TILE - height / 2)
                  and middle == height // 2, f"U+{c:X} at level {k}: quarters {across} x {up} tiles, cell {width} x {height}")
    print(f"  modifiers: {len(MODIFIER_GOLDEN)} golden cases, 2500 random texts ({counts})")


# --- enclosures and sign modifiers together (sections 10 and 11) -----------

COMBINED_GOLDEN = [  # text, and per cluster (start, end, advance, glyphs, frame); written here
    # Khufu with the first chick mirrored and the viper damaged at top start and
    # bottom end: each drawn as the sign of its group of one, in its place
    ([V11A, BEGIN, AA1, G43, MIR, I9, 0x1344F, G43, END_ENC, V11B], [
        (0, 2, 617, [], [(("piece", V11A), 0, 0)]),
        (2, 3, 694, [(AA1, 9, 83, 0, 1.0)], [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 694, 0)]),
        (3, 5, 874, [(G43, 867, 13, 0, -1.0)],
         [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 874, 0)]),
        (5, 7, 1324, [(I9, 7, 325, 0, 0.872), (piece(1, 14, 5), 662, 540, 0, 1.0), (piece(8, 14, 5), 662, 540, 0, 1.0)],
         [(("line", "plain", 1024, "start"), 0, 0), (("line", "plain", 1024, "end"), 1324, 0)]),
        (7, 8, 874, [(G43, 7, 13, 0, 1.0)], [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 874, 0)]),
        (8, 10, 617, [], [(("piece", V11B), 0, 0)]),
    ]),
    # the mouth damaged at the bottom in rn, in a walled enclosure: the group
    # and its shading as outside (MODIFIER_GOLDEN), the lines as without damage
    ([BEGIN_W, D21, BOTTOM_D, V, N35, END_W], [
        (0, 1, 0, [], []),
        (1, 5, 1234, [(D21, 28, 604, 0, 1.0), (piece(2, 13, 4), 617, 779, 0, 1.0), (piece(8, 13, 4), 617, 779, 0, 1.0),
                      (N35, 18, 202, 0, 1.0)],
         [(("line", "walled", 1024, "start"), 0, 0), (("line", "walled", 1024, "end"), 1234, 0),
          (("merlons", "walled", 8), 617, 0)]),
        (5, 6, 0, [], []),
    ]),
    # the chick mirrored and damaged with the bread in its corner (the control
    # read as its mirror image, rule M5): the block moved up by 13 (rule E4),
    # the shading of the chick with it (449 outside)
    ([V11A, BEGIN, G43, MIR, 0x13449, TS, X1, END_ENC, V11B], [
        (0, 2, 617, [], [(("piece", V11A), 0, 0)]),
        (2, 7, 860, [(G43, 797, 11, 1, -0.855), (piece(1, 8, 10), 430, 462, 0, 1.0), (piece(2, 8, 10), 430, 462, 0, 1.0),
                     (X1, 19, 648, 3, 0.665)],
         [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 860, 0)]),
        (7, 9, 617, [], [(("piece", V11B), 0, 0)]),
    ]),
    # modifiers on the delimiters: they join, and draw nothing (rule M9)
    ([V11A, MIR, BEGIN, AA1, END_ENC, V11B, DAMAGED], [
        (0, 3, 617, [], [(("piece", V11A), 0, 0)]),
        (3, 4, 694, [(AA1, 9, 83, 0, 1.0)], [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 694, 0)]),
        (4, 7, 617, [], [(("piece", V11B), 0, 0)]),
    ]),
    # a stray damage modifier inside is content, a box with its lines (rule E1)
    ([BEGIN, A1, TOP_START_D, 0x13448, END_ENC], [
        (0, 1, 0, [], []),
        (1, 3, 919, [(A1, 10, 0, 0, 1.0), (piece(1, 10, 12), 459, 540, 0, 1.0)],
         [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 919, 0)]),
        (3, 4, 698, [(0x13448, 0, 0, 0, 1.0)], [(("line", "plain", 512, "start"), 0, 0), (("line", "plain", 512, "end"), 698, 0)]),
        (4, 5, 0, [], []),
    ]),
]
COMBINED_UNFORMED = [  # rule E1: a variation selector inside, even inside a literal (rule M1)
    [V11A, BEGIN, A1, VS1, MIR, END_ENC, V11B], [BEGIN, VS1, A1, END_ENC],
    [V11A, MIR, 0x200D, BEGIN, A1, END_ENC, V11B],  # ZWJ: V11A is a mirrored sign apart, the rest forms
]


def combined_text(rng, codepoints, small):
    """Seeded random text: enclosures, maybe with modified delimiters, around
    literals, groups, insertions, plain words and stray characters."""
    def literal(sign):
        r = rng.random()
        return [sign] + [MIR] * (r < 0.35) + [rng.choice(L.DAMAGE)] * (0.25 < r < 0.6)

    def part():
        r = rng.random()
        if r < 0.3:
            return literal(rng.choice(codepoints))
        if r < 0.55:
            rows = [[rng.choice(codepoints) for _ in range(rng.randint(1, 2))] for _ in range(rng.randint(1, 3))]
            out = []
            for i, row in enumerate(rows):
                out += [V] * bool(i)
                for j, sign in enumerate(row):
                    out += [H] * bool(j) + literal(sign)
            return out
        if r < 0.75:
            return literal(rng.choice(L.BIRDS if rng.random() < 0.5 else small)) + [rng.choice(list(L.CORNERS))] \
                + literal(rng.choice(small))
        if r < 0.9:
            return [c for _ in range(rng.randint(2, 4)) for c in literal(rng.choice(codepoints))]
        return [rng.choice((V, H, 0x13437, 0x20, MIR, TOP_START_D, BEGIN, END_ENC, VS1))]
    text = [c for _ in range(rng.randint(0, 1)) for c in part()]
    plain = rng.random() < 0.6
    if rng.random() < 0.85:
        text += literal(rng.choice(L.OPENINGS)) if rng.random() < 0.3 else [rng.choice(L.OPENINGS)]
    text.append(BEGIN if plain else BEGIN_W)
    for _ in range(rng.randint(1, 5)):
        text += part()
    text.append(END_ENC if plain else END_W)
    if rng.random() < 0.85:
        text += literal(rng.choice(L.CLOSINGS)) if rng.random() < 0.3 else [rng.choice(L.CLOSINGS)]
    return text + [c for _ in range(rng.randint(0, 1)) for c in part()]


def test_combined(signs):
    """Enclosures with modified signs: golden cases; and, on seeded random
    text, the modifiers make, break and move no enclosure, change no sign
    but its drawing, and the shading stays on its sign wherever the
    enclosure puts it (rules M2, M9)."""
    for text, expected in COMBINED_GOLDEN:
        got = [(c.start, c.end, c.advance, [tuple(g) for g in c.glyphs], [tuple(f) for f in c.frame])
               for c in L.layout(text, signs)]
        check(got == expected, f"{label(text)}:\n  got      {got}\n  expected {expected}")
    for text in COMBINED_UNFORMED[:2]:
        check(not any(c.frame for c in L.layout(text, signs)), f"{label(text)}: an enclosure formed")
    laid = L.layout(COMBINED_UNFORMED[2], signs)
    parts = [f.part[:2] for c in laid for f in c.frame]
    check(parts == [("line", "plain")] * 2 + [("piece", V11B)] and laid[0].glyphs[0].scale == -1.0,
          f"{label(COMBINED_UNFORMED[2])}: {parts}")
    # the automatic layer inside an enclosure ignores the modifiers
    table = L.automatic_table()
    word = [c for c in next(iter(sorted(table, key=str))) if c not in (L.START, L.END)]
    modified = [x for c in word for x in (c, MIR, TOP_START_D)]
    inside = L.layout([V11A, BEGIN, *modified, END_ENC, V11B], signs, table)
    plain = L.layout([V11A, BEGIN, *word, END_ENC, V11B], signs, table)
    check([(c.advance, c.frame) for c in inside] == [(c.advance, c.frame) for c in plain]
          and [len([g for g in c.glyphs if not L.is_hatch(g.codepoint)]) for c in inside]
          == [len(c.glyphs) for c in plain], "a modified word of the table is stacked differently in a cartouche")
    rng = random.Random(43)
    codepoints = [c for c in sorted(signs) if c in L.HIEROGLYPHS]
    small = [c for c in codepoints if L.insertable(signs[c])]
    counts = {"formed": 0, "mirrored": 0, "pieces": 0}
    for n in range(1500):
        text = combined_text(rng, codepoints, small)
        use = table if n % 2 else None
        laid = L.layout(text, signs, use)
        bare = L.layout(strip(text), signs, use, modifiers=False)
        counts["formed"] += any(c.frame for c in laid)
        # the modifiers move nothing but the drawing: drop the strays' boxes,
        # the shading and the small mirror box, and turn mirrored signs back
        kept = [c for c in laid if c.glyphs[:1] == () or c.glyphs[0].codepoint not in L.DAMAGE]
        ref = [c for c in bare if c.glyphs[:1] == () or c.glyphs[0].codepoint != L.STRAY]
        unturned = [[g._replace(x=g.x - L._round(-g.scale * (signs[g.codepoint].box[0] + signs[g.codepoint].box[2])),
                                scale=-g.scale) if g.scale < 0 else g
                     for g in c.glyphs if not L.is_hatch(g.codepoint)
                     and not (g.codepoint == MIR and g.scale == L.MIRROR_BOX)] for c in kept]
        for c, glyphs in zip(kept, unturned):  # rule M5: the inserted sign stands in the mirrored zone
            if c.stacked and len(glyphs) == 2 and c.glyphs[0].scale < 0 and glyphs[1].level != glyphs[0].level:
                box, dx = signs[glyphs[0].codepoint].box, L.sign_offset(signs[glyphs[1].codepoint], glyphs[1].level)[0]
                glyphs[1] = glyphs[1]._replace(x=box[0] + box[2] - glyphs[1].x + 2 * dx)
        unturned = [tuple(glyphs) for glyphs in unturned]
        check([(c.advance, c.frame) for c in kept] == [(c.advance, c.frame) for c in ref]
              and unturned == [c.glyphs for c in ref], f"{label(text)}: the modifiers change the layout")
        # each piece of shading on the sign before it: at the middle of its
        # ink across and the middle of its cell above the bottom of its ink
        for c in laid:
            sign = None
            for g in c.glyphs:
                if g.codepoint == MIR and g.scale == L.MIRROR_BOX:  # rule M8, over the sign before
                    continue
                if not L.is_hatch(g.codepoint):
                    sign = g if g.codepoint in signs else None
                    counts["mirrored"] += g.scale < 0
                    continue
                counts["pieces"] += 1
                ink = L.ink_box(sign, signs)
                middle = L.damage_size(signs[sign.codepoint], sign.level)[2]
                check(abs(g.x - (ink[0] + ink[2]) / 2) <= 1.5 and abs(g.y - ink[1] - middle) <= 1.5,
                      f"{label(text)}: shading at {(g.x, g.y)} off its sign {tuple(sign)}")
    check(counts["formed"] > 1000 and counts["mirrored"] > 1000 and counts["pieces"] > 1000,
          f"random combined text reaches too few cases: {counts}")
    print(f"  enclosures with modifiers: {len(COMBINED_GOLDEN)} golden, {len(COMBINED_UNFORMED)} unformed, "
          f"1500 random texts ({counts['formed']} with an enclosure, {counts['mirrored']} mirrored signs, "
          f"{counts['pieces']} pieces of shading)")


# --- all the controls together (sections 8 to 11) ---------------------------

ALL_GOLDEN = [  # text, and per cluster (start, end, advance, glyphs, frame); written here
    # Ptah in a cartouche, the stool in the segment damaged in full
    ([V11A, BEGIN, SB, Q3, DAMAGED, V, X1, SE, H, V28, END_ENC, V11B], [
        (0, 2, 617, [], [(("piece", V11A), 0, 0)]),
        (2, 10, 1054, [(Q3, 122, 578, 0, 1.0), (piece(1, 4, 5), 324, 779, 0, 1.0), (piece(2, 4, 5), 324, 779, 0, 1.0),
                       (piece(4, 4, 5), 324, 779, 0, 1.0), (piece(8, 4, 5), 324, 779, 0, 1.0), (X1, 7, -126, 0, 1.0),
                       (V28, 600, 3, 0, 1.0)],
         [(("line", "plain", 1024, "start"), 0, 0), (("line", "plain", 1024, "end"), 1054, 0)]),
        (10, 12, 617, [], [(("piece", V11B), 0, 0)]),
    ]),
    # an overlay, its second operand mirrored (one member with its modifier)
    ([G17, OV, D36, MIR], [(0, 4, 1324, [(G17, 104, 18, 0, 1.0), (D36, 1317, 270, 0, -0.87)], [])]),
    # the flag in the middle of the house, mirrored: level 5 has no mirrored
    # variant, so the small box over it (rule M8)
    ([O1, L.MIDDLE_INSERT, R8, MIR], [(0, 4, 1377, [(O1, 0, 0, 0, 1.0), (R8, 564, 224, 5, 0.425), (MIR, 602, 278, 0, 0.25)],
                                       [])]),
    # the same in a cartouche, damaged at top end: the block moved down by
    # 110 (rule E4), the box and the shading with it
    ([V11A, BEGIN, O1, L.MIDDLE_INSERT, R8, MIR, 0x1344A, END_ENC, V11B], [
        (0, 2, 617, [], [(("piece", V11A), 0, 0)]),
        (2, 7, 1377, [(O1, 0, -110, 0, 1.0), (R8, 564, 114, 5, 0.425), (MIR, 602, 168, 0, 0.25),
                      (piece(4, 3, 6), 689, 293, 0, 1.0)],
         [(("line", "plain", 1024, "start"), 0, 0), (("line", "plain", 1024, "end"), 1377, 0)]),
        (7, 9, 617, [], [(("piece", V11B), 0, 0)]),
    ]),
    # a side control after a mirrored sign is not supported (rule M5): unstacked
    ([0x13010, MIR, L.MIDDLE_INSERT, X1], [
        (0, 2, 1371, [(0x13010, 1371, 0, 0, -1.0)], []), (2, 3, 698, [(MIR, 0, 0, 0, 1.0)], []),
        (3, 4, 633, [(X1, 0, 189, 0, 1.0)], []),
    ]),
]


def all_controls_text(rng, codepoints, small):
    """Seeded random text: literals in segments, overlays, side and corner
    insertions, plain words and groups, most of it in enclosures."""
    low = [c for c in codepoints if signs_table[c].cell[1] <= 6]
    narrow = [c for c in codepoints if signs_table[c].cell[0] <= 10]
    having = {c: [b for b in codepoints if signs_table[b].corners[c][0]["flat"].width] for c in L.SIDES}

    def literal(sign):
        r = rng.random()
        return [sign] + [MIR] * (r < 0.3) + [rng.choice(L.DAMAGE)] * (0.2 < r < 0.5)

    def part():
        r = rng.random()
        if r < 0.15:
            return literal(rng.choice(codepoints))
        if r < 0.35:  # a segment beside a sign
            box = [SB, *literal(rng.choice(low)), V, *literal(rng.choice(low)), SE]
            other = literal(rng.choice(narrow))
            return box + [H] + other if rng.random() < 0.5 else other + [H] + box
        if r < 0.5:  # an overlay, maybe the first row of a column
            left = literal(rng.choice(codepoints)) if rng.random() < 0.7 else \
                [SB, *literal(rng.choice(narrow)), H, *literal(rng.choice(narrow)), SE]
            out = left + [OV] + literal(rng.choice(codepoints))
            return out + [V] + literal(rng.choice(low)) if rng.random() < 0.3 else out
        if r < 0.65:  # middle, top, bottom
            control = rng.choice(L.SIDES)
            return literal(rng.choice(having[control])) + [control] + literal(rng.choice(small if rng.random() < 0.6
                                                                                           else codepoints))
        if r < 0.72:
            return literal(rng.choice(list(L.BIRDS) + small)) + [rng.choice(list(L.CORNERS))] + literal(rng.choice(small))
        if r < 0.9:
            out = []
            for i in range(rng.randint(1, 3)):
                out += [V] * bool(i)
                for j in range(rng.randint(1, 2)):
                    out += [H] * bool(j) + literal(rng.choice(codepoints))
            return out
        return [rng.choice((V, H, SB, SE, OV, L.MIDDLE_INSERT, 0x20, MIR, TOP_START_D, BEGIN, END_ENC))]
    text = [c for _ in range(rng.randint(0, 1)) for c in part()]
    if rng.random() < 0.8:
        plain = rng.random() < 0.6
        if rng.random() < 0.85:
            text += literal(rng.choice(L.OPENINGS)) if rng.random() < 0.2 else [rng.choice(L.OPENINGS)]
        text.append(BEGIN if plain else BEGIN_W)
        for _ in range(rng.randint(1, 4)):
            text += part()
        text.append(END_ENC if plain else END_W)
        if rng.random() < 0.85:
            text += literal(rng.choice(L.CLOSINGS)) if rng.random() < 0.2 else [rng.choice(L.CLOSINGS)]
    else:
        text += [c for _ in range(rng.randint(1, 3)) for c in part()]
    return text + [c for _ in range(rng.randint(0, 1)) for c in part()]


signs_table = {}


def test_all_controls(signs):
    """Segments, overlay, side insertion, enclosures and modifiers together:
    golden cases; on seeded random text the modifiers change nothing but
    the drawing (rule M2, with rule M5), the shading stays on its sign, the
    enclosure keeps its content in the ring (rules E4, E5, M9)."""
    signs_table.update(signs)
    for text, expected in ALL_GOLDEN:
        got = [(c.start, c.end, c.advance, [tuple(g) for g in c.glyphs], [tuple(f) for f in c.frame])
               for c in L.layout(text, signs)]
        check(got == expected, f"{label(text)}:\n  got      {got}\n  expected {expected}")
    table = L.automatic_table()
    rng = random.Random(47)
    codepoints = [c for c in sorted(signs) if c in L.HIEROGLYPHS]
    small = [c for c in codepoints if L.insertable(signs[c])]
    counts = {"formed": 0, "boxes": 0, "boxes in a ring": 0, "sides": 0, "sides in a ring": 0, "modified": 0}
    for n in range(1500):
        text = all_controls_text(rng, codepoints, small)
        use = table if n % 2 else None
        laid = L.layout(text, signs, use)
        bare = L.layout(strip(text), signs, use, modifiers=False)
        counts["formed"] += any(c.frame for c in laid)
        kept = [c for c in laid if c.glyphs[:1] == () or c.glyphs[0].codepoint not in L.DAMAGE]
        ref = [c for c in bare if c.glyphs[:1] == () or c.glyphs[0].codepoint != L.STRAY]
        unturned = [[g._replace(x=g.x - L._round(-g.scale * (signs[g.codepoint].box[0] + signs[g.codepoint].box[2])),
                                scale=-g.scale) if g.scale < 0 else g
                     for g in c.glyphs if not L.is_hatch(g.codepoint)
                     and not (g.codepoint == MIR and g.scale == L.MIRROR_BOX)] for c in kept]
        for c, glyphs in zip(kept, unturned):  # rule M5: a corner's sign stands in the mirrored zone
            if c.stacked and len(glyphs) == 2 and c.glyphs[0].scale < 0 and glyphs[1].level != glyphs[0].level:
                box, dx = signs[glyphs[0].codepoint].box, L.sign_offset(signs[glyphs[1].codepoint], glyphs[1].level)[0]
                glyphs[1] = glyphs[1]._replace(x=box[0] + box[2] - glyphs[1].x + 2 * dx)
        check([(c.advance, c.frame) for c in kept] == [(c.advance, c.frame) for c in ref]
              and [tuple(g) for g in unturned] == [c.glyphs for c in ref], f"{label(text)}: the modifiers change the layout")
        for c in laid:
            run = [x for x in text[c.start:c.end] if L.is_sign(x) or x in L.CONTROLS]
            boxed = c.stacked and any(x in L.NESTING for x in run)
            side = c.stacked and any(x in L.SIDES for x in run)
            counts["boxes"] += boxed
            counts["boxes in a ring"] += boxed and bool(c.frame)
            counts["sides"] += side
            counts["sides in a ring"] += side and bool(c.frame)
            counts["modified"] += (boxed or side) and any(g.scale < 0 or L.is_hatch(g.codepoint) for g in c.glyphs)
            if c.frame and any(f.part[0] == "line" for f in c.frame):  # rule E4: the ink inside the ring
                inks = [L.ink_box(g, signs) for g in c.glyphs if g.codepoint in signs]
                check(all(-2 <= ink[1] and ink[3] <= L.ENCLOSED_TOP + 2 for ink in inks),
                      f"{label(text)}: the ink of the cluster at {c.start} leaves the inside of the ring")
            sign = None
            for g in c.glyphs:  # each piece of shading on the sign before it
                if g.codepoint == MIR and g.scale == L.MIRROR_BOX:
                    continue
                if not L.is_hatch(g.codepoint):
                    sign = g if g.codepoint in signs else None
                    continue
                ink = L.ink_box(sign, signs)
                middle = L.damage_size(signs[sign.codepoint], sign.level)[2]
                check(abs(g.x - (ink[0] + ink[2]) / 2) <= 1.5 and abs(g.y - ink[1] - middle) <= 1.5,
                      f"{label(text)}: shading at {(g.x, g.y)} off its sign {tuple(sign)}")
    check(counts["boxes in a ring"] > 150 and counts["sides in a ring"] > 60 and counts["modified"] > 300,
          f"random text with all controls reaches too few cases: {counts}")
    print(f"  all controls: {len(ALL_GOLDEN)} golden, 1500 random texts ({counts})")


def main():
    signs = L.sign_table(SOURCE)
    tests = (test_constants, test_signs, test_grammar, test_golden, test_golden_notices_constants,
             test_owner_rules, test_rounding, test_insertion, test_malformed, test_random,
             test_automatic, test_nesting, test_side_insertion, test_enclosures, test_modifiers, test_combined,
             test_all_controls)
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
