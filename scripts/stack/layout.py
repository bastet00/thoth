"""Reference layout: where every sign of a group goes.

This file is the one place where the geometry of stacked signs is decided.
It is plain arithmetic on the outlines of the source font, read top to
bottom: constants, characters, signs, groups, layout. The OpenType tables
of the font are to be a compiled form of the same rules, and the tests
compare the two.

    signs = sign_table(ufoLib2.Font.open("sources/Thoth-Regular.ufo"))
    for cluster in layout([0x1308B, 0x13430, 0x13216], signs):
        print(cluster.advance, cluster.glyphs)

The rules, each stated once:

 1. A sign that is not joined to anything is drawn as the source has it,
    with one change: a low sign, one whose cell (rule 2) is at most
    LOW_HEIGHT units high, is moved up so that the middle of its ink is on
    the middle line of the quadrat, MIDDLE (Sign.lift).
 2. A sign's cell is its ink plus GAP, rounded up to whole units in
    height and to half units in width. A sign larger than the quadrat is
    first reduced, on its own, to fit it.
 3. A row (signs joined horizontally) is as wide as its cells together and
    as high as its highest cell. A group (rows joined vertically) is as
    wide as its widest row and as high as its rows together.
 4. The whole group is drawn at one level: the largest of seven at which it
    is at most WIDTH_LIMIT half units by HEIGHT_LIMIT units of full size.
    Most groups fit at level 0, so their signs are as large as the lone
    signs next to them.
 5. At every level the ink of a sign leaves GAP in its cell, so neighbours
    never come closer than GAP. Where the scale of the level alone would
    leave less, the sign is reduced a little more, on its own, by a quarter
    at most (Sign.scales).
 6. Across: the cells of a row touch, each sign is centred in the width of
    its cell, and a row narrower than its group is centred in it. But a row
    of exactly two signs whose cells leave at most MAX_JUSTIFY half units
    of the group's width free is justified: the first cell flush with the
    left edge of the group, the second with its right edge.
 7. Up: the signs of a row stand on one line, the bottom of their cells.
    The rows of a group are centred in the height of the quadrat. One row
    is centred if it is low (as in rule 1) and stands on the baseline if it
    is not. Two rows share the height they leave free: each is kept from
    its edge of the quadrat by a quarter of that height plus GAP, the upper
    row hanging from the top, the lower standing on the bottom, so two low
    rows take half the quadrat each; never so far in that their cells
    overlap. Three and more rows are packed one under the other.
 8. The advance of a group is its width less one gap, plus the side
    bearings of a sign.
 9. A run of signs and controls that is not a well-formed group, or whose
    group is wider than MAX_WIDTH half units or higher than MAX_HEIGHT
    units, is drawn unstacked: every sign as a lone sign, every control as
    its fallback box.
10. A sign, a corner insertion control and a sign put the second sign into
    a corner of the first (section 6, rules I1 to I6).
11. Plain text, signs with no control between them, is stacked as if the
    controls of a table of known sign sequences were there, and two
    half-block signs in a row (low and wide) stack one above the other
    (section 7, rules A1 to A9). Explicit controls always win.
12. A begin and an end enclosure control draw a ring or a wall around the
    groups between them, at full size (section 8, rules E1 to E7).
13. A sign may be mirrored and damaged by the modifiers that follow it
    (section 9, rules M1 to M8); a modified sign takes part in all of the
    above exactly as the sign does, inside an enclosure too.

Rounding. The font can only add whole numbers that its glyphs carry, so
every position here is such a sum, rounded as the font rounds it: a unit
and a half unit are whole numbers of font units at each level (unit(),
half_unit()); each glyph's share of a position is rounded on its own, from
what that one glyph knows: a cell's width (whole half units), half of its
row and half of the group (rounded down), the margins of rule 7 (rounded
down, from the group's height and level), a sign's offset in its cell (to
the nearest, baked into its variant); then the shares are added. The font
and this file therefore agree exactly. Only the outline of a scaled
component may differ from ink_box(), by its own rounding: at most 2.
"""

import math
import re
import unicodedata
from collections import namedtuple
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen

# --- 1. Constants -----------------------------------------------------------
# Lengths are in font units (1000 to the em) unless they are called units.
# Heights are counted in units, widths in half units.

UNIT = 90  # the grid: cells are whole units high and whole half units wide
GAP = 34  # least distance between the ink of two neighbours, at every level
HEIGHT_LIMIT = 12  # units the quadrat is high
WIDTH_LIMIT = 28  # half units the quadrat is wide
LEVEL_HEIGHTS = (12, 14, 16, 18, 20, 24, 36)  # one scale level for each:
# the height in units that the level brings down to HEIGHT_LIMIT
MAX_WIDTH, MAX_HEIGHT = 64, 36  # half units, units: a larger group is not stacked
MAX_JUSTIFY = 12  # half units: the most a justified row of two may leave free
LOW_HEIGHT = 6  # units: a lone sign or a single row up to this high is centred
MIDDLE = (HEIGHT_LIMIT * UNIT - GAP) // 2  # the middle line of the quadrat: 523
MOST_REDUCED = 0.75  # rule 5 takes at most a quarter off a sign
SIDE_BEARING = 49  # the side bearing of the signs in the source

# Why these values.
# - Twelve units hold the tall signs of the source (1001 to 1035 high, the
#   seated man to the ankh) and one gap: 12 * 90 = 1046 + 34. A full group
#   is therefore as high as a tall lone sign, and tall signs side by side
#   are not reduced. The ink of a group is centred on 523, the middle of
#   those 1046, and so is the ink of a low lone sign.
# - Fourteen units of width (28 half units), against twelve of height, let
#   the two commonest wide signs (mouth 1079, water 1099) keep their size in
#   a group. In a square quadrat they would be smaller than the lone signs
#   next to them.
# - A gap of 34 is about one pixel at the smallest size the signs are read
#   at (26 pixels to the em); with less, neighbours run together there. It
#   is the same at every level because the pixel is. With a unit of 90 it
#   is also the largest gap that leaves the stroke (416 high) in five units.
# - Seven levels from 1.0 to 0.333: halves and thirds for two and three
#   full rows, and 14, 16, 18 and 20 units because that is where real
#   groups are. An eighth level (48 units, a quarter) was used by no group
#   of the dictionary and cost 1,078 glyphs, about 46 KB of the font
#   (milestone 3b). The price: the level of a group inside a group
#   (a later milestone) comes from a table of products rounded down to a
#   level, not from a sum.
# - Widths in half units: the ink of a sign is centred in its cell, so the
#   ink edges of a justified row and of the row above it can differ by half
#   the rounding of the cells. With whole units that was up to 1.75 pixels
#   at 40 pixels to the em, with half units it is under one (milestone 4).
#   Heights stay in whole units: the signs of a row stand on the bottom of
#   their cells, so there is no centring up and down to round.
# - The caps are the largest group of the owner's dictionary (9,330 groups
#   in 10,224 words), 29 units wide and 36 high: three units more across,
#   and as high as the lowest level, three full rows, allows. The font
#   needs no state for sizes beyond them.
# - Six units (12 half units) free let the bread and the stool of
#   "offering" reach the ends of the table above them, and keep two strokes
#   under a water sign (nine units free) together.
# - Low is half the quadrat: bread, mouth, water and stool are centred when
#   alone; figures, birds, staffs and lying animals stand on the baseline.


def unit(level):
    """The unit at a level, in font units: 90, 77, 67, 60, 54, 45, 30."""
    return HEIGHT_LIMIT * UNIT // LEVEL_HEIGHTS[level]


def half_unit(level):
    """The half unit at a level, in font units: 45, 38, 33, 30, 27, 22, 15."""
    return unit(level) // 2


# --- 2. Characters ----------------------------------------------------------

VERTICAL_JOINER = 0x13430
HORIZONTAL_JOINER = 0x13431
CONTROLS = range(0x13430, 0x13441)  # the format controls the font has
PLACEHOLDERS = range(0x13441, 0x13447)  # blanks and lost signs
HIEROGLYPHS = range(0x13000, 0x13430)

# A blank has no outline. It takes the box of the lost sign of its size.
BLANK_BOX = {0x13441: 0x13443, 0x13442: 0x13444}

# A control that no rule consumes shows the fallback box of the generator
# (glyphs.py): a square of 600 on the centre of the line.
CONTROL_ADVANCE = 698
CONTROL_BOX = (49, 200, 649, 800)


def is_sign(codepoint):
    """Signs are the members of groups: hieroglyphs, blanks and lost signs."""
    return codepoint in HIEROGLYPHS or codepoint in PLACEHOLDERS


# --- 3. Signs ---------------------------------------------------------------

# name: glyph name in the source; advance: its advance; box: ink box
# (xMin, yMin, xMax, yMax); cell: (width, height) in half units and units,
# the size class;
# scales: the scale of the sign in a group, one for each level; lift: how
# far the lone sign is moved up (rule 1); corners: its free corners, for
# insertion (section 6). The font bakes scales into the variants of the
# sign and lift into its lone glyph.
Sign = namedtuple("Sign", "name advance box cell scales lift corners")


def sign_table(font):
    """{code point: Sign} for every sign of the source font (a ufoLib2 Font)."""
    glyphs = {}
    for glyph in font:
        for codepoint in glyph.unicodes:
            if is_sign(codepoint):
                glyphs[codepoint] = glyph
    boxes = {}
    for codepoint, glyph in glyphs.items():
        pen = BoundsPen(font)
        glyph.draw(pen)
        if pen.bounds:
            x_min, y_min, x_max, y_max = pen.bounds
            boxes[codepoint] = (
                math.floor(x_min), math.floor(y_min), math.ceil(x_max), math.ceil(y_max)
            )
    table = {}
    for codepoint in sorted(glyphs):
        glyph = glyphs[codepoint]
        box = boxes[BLANK_BOX.get(codepoint, codepoint)]
        cell = sign_cell(box)
        scales = tuple(sign_scale(box, cell, level) for level in range(len(LEVEL_HEIGHTS)))
        table[codepoint] = Sign(glyph.name, glyph.width, box, cell, scales,
                                sign_lift(box, cell), sign_corners(font, glyph, box, codepoint))
    return table


def _fit(box):
    """Rule 2: 1, or the scale that brings a large sign inside the quadrat."""
    sizes = (box[2] - box[0], box[3] - box[1])
    limits = (WIDTH_LIMIT * UNIT / 2, HEIGHT_LIMIT * UNIT)
    return min(1, *((limit - GAP) / size for size, limit in zip(sizes, limits)))


def sign_cell(box):
    """Rule 2: the cell of a sign, (width in half units, height in units)."""
    fit = _fit(box)
    return tuple(math.ceil(round(size * fit + GAP, 6) / step)
                 for size, step in zip((box[2] - box[0], box[3] - box[1]), (UNIT / 2, UNIT)))


def sign_scale(box, cell, level):
    """Rules 2 and 5: the scale of a sign in a group at a level."""
    sizes = (box[2] - box[0], box[3] - box[1])
    scale = _fit(box) * unit(level) / UNIT
    steps = (half_unit(level), unit(level))
    clear = min((cells * step - GAP) / size for size, cells, step in zip(sizes, cell, steps))
    scale = max(min(scale, clear), MOST_REDUCED * scale)
    return math.floor(scale * 1000) / 1000  # rounded down: it must still fit


def sign_lift(box, cell):
    """Rule 1: how far a lone sign is moved up, 0 unless it is low."""
    if cell[1] > LOW_HEIGHT:
        return 0
    return MIDDLE - (box[1] + box[3]) // 2


# --- 4. Groups --------------------------------------------------------------
#
# The syntax is that of the Unicode proposal L2/21-248 (Glass, Grotenhuis,
# Nederhof, Polis, Rosmorduc, Werning: "Additional control characters for
# Ancient Egyptian hieroglyphic texts", 2021), tables 1 and 3, which restate
# and extend L2/17-112R. The Unicode core specification (chapter 11, section
# "Egyptian Hieroglyphs", "Egyptian Hieroglyph Format Controls") describes
# what each control does and shows the examples (figures 11-1, 11-2, 11-5)
# but gives no grammar. Writing ":" for the vertical joiner and "*" for the
# horizontal joiner, the part implemented here is
#
#     group            ::= vertical_group | horizontal_group | basic_group
#     vertical_group   ::= ver_subgroup (":" ver_subgroup)+
#     ver_subgroup     ::= horizontal_group | basic_group
#     horizontal_group ::= basic_group ("*" basic_group)+
#     basic_group      ::= sign | placeholder
#
# so the horizontal joiner binds tighter than the vertical joiner:
# A : B * C is A above the row B C. In the proposal a member of a horizontal
# group is also a vertical group between the segment controls, and a basic
# group is also an overlay or a sign with insertions. Those controls are
# unsupported here.
#
# A parsed group is a tuple of rows, a row is a tuple of the code points of
# its signs.
#
# The proposal does not say what to draw for text outside the grammar.
# Rule 9 is ours: text is cut into runs, a run being a longest stretch of
# signs and controls in which no two signs touch. Two signs with nothing
# between them are never one group, so they end one run and start the next.
# A run is one sign, or a well-formed group, or it is drawn unstacked as a
# whole. A leading, trailing or doubled joiner and any unsupported control
# make the run they are in not well formed.


def runs(codepoints):
    """Cut text into runs: [(start, end)], other characters left out."""
    found, start = [], None
    for index, codepoint in enumerate(codepoints):
        sign = is_sign(codepoint)
        if start is not None and (
            not (sign or codepoint in CONTROLS)  # other text ends a run
            or (sign and is_sign(codepoints[index - 1]))  # so do two signs
        ):
            found.append((start, index))
            start = None
        if start is None and (sign or codepoint in CONTROLS):
            start = index
    if start is not None:
        found.append((start, len(codepoints)))
    return found


def parse(run):
    """The group a run spells, or None if the run is not well formed."""
    joiners = run[1::2]
    if len(run) % 2 == 0 or not all(map(is_sign, run[::2])) or not all(
        joiner in (VERTICAL_JOINER, HORIZONTAL_JOINER) for joiner in joiners
    ):
        return None  # a well-formed run is sign (joiner sign)*
    rows = [[run[0]]]
    for joiner, sign in zip(joiners, run[2::2]):
        if joiner == VERTICAL_JOINER:
            rows.append([sign])
        else:
            rows[-1].append(sign)
    return tuple(map(tuple, rows))


# --- 5. Layout --------------------------------------------------------------

# One drawn glyph: the outline of the code point, scaled by `scale` about
# its origin and then moved by (x, y) from the start of its cluster.
# A lone sign has x 0, y Sign.lift, level 0 and scale 1.0.
Glyph = namedtuple("Glyph", "codepoint x y level scale")

# A stretch of the text, codepoints[start:end], that advances as one:
# a group (stacked is True), a lone sign or a control.
Cluster = namedtuple("Cluster", "start end advance glyphs stacked frame", defaults=((),))
# frame: the lines and end pieces an enclosure draws for the cluster (section 8)


def measure(group, signs):
    """Rule 3: (width, height) of a group, and of each row: (half units, units)."""
    rows = []
    for row in group:
        cells = [signs[member].cell for member in row]
        rows.append((sum(cell[0] for cell in cells), max(cell[1] for cell in cells)))
    return max(row[0] for row in rows), sum(row[1] for row in rows), rows


def fit_level(width, height):
    """Rules 4 and 9: the level of a group of this size (half units wide,
    units high), or None.

    Width and height are fitted on their own; the group takes the smaller
    of the two scales, which is the larger level."""
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        return None
    return max(_fit_one(width, half_unit, WIDTH_LIMIT * UNIT // 2),
               _fit_one(height, unit, HEIGHT_LIMIT * UNIT))


def _fit_one(size, step, limit):
    return next(level for level in range(len(LEVEL_HEIGHTS)) if size * step(level) <= limit)


def layout(codepoints, signs, table=None, modifiers=True):
    """Lay out text: [Cluster] for its signs and controls, in text order.

    Characters that are neither (letters, spaces) get no cluster: the font
    shapes them as usual. table: the automatic stacking table (section 7,
    automatic_table()), or None for the font with the automatic layer
    switched off. modifiers: False once section 9 has taken them out.
    """
    if modifiers and any(c in MODIFIERS for c in codepoints):  # section 9, which calls this again
        return modified_layout(codepoints, signs, table)
    if any(codepoint in ENCLOSURE for codepoint in codepoints):  # section 8
        return _with_enclosures(codepoints, signs, table)
    if table is not None:
        text, origin = automatic(codepoints, table, signs)
        return [cluster._replace(start=origin[cluster.start], end=origin[cluster.end - 1] + 1)
                for cluster in layout(text, signs, modifiers=False)]
    clusters = []
    for start, end in runs(codepoints):
        run = codepoints[start:end]
        if is_insertion(run):  # section 6
            clusters.append(_inserted(start, end, run, signs))
            continue
        group = parse(run)
        level = fit_level(*measure(group, signs)[:2]) if group else None
        if level is not None and len(run) > 1:
            clusters.append(_stacked(start, end, group, level, signs))
        else:  # rules 1 and 9
            clusters += [_unstacked(start + i, c, signs) for i, c in enumerate(run)]
    return clusters


def _unstacked(index, codepoint, signs):
    if codepoint in signs:
        advance, lift = signs[codepoint].advance, signs[codepoint].lift
    else:
        advance, lift = CONTROL_ADVANCE, 0
    return Cluster(index, index + 1, advance, (Glyph(codepoint, 0, lift, 0, 1.0),), False)


# The shares a position is made of (see Rounding above). Each is a whole
# number that one glyph of the font can carry, and the font adds them up
# exactly as _stacked() does; the generator calls these same functions.

def advance(width, step):
    """Rule 8: the advance of a group `width` half units wide, `step` the
    half unit of its level."""
    return width * step - GAP + 2 * SIDE_BEARING


def centre(width, step):
    """The axis of a group, from its start: its cells begin half a gap left
    of the side bearing."""
    return SIDE_BEARING - GAP // 2 + half(width, step)


def half(units, step):
    """Half of a length in (half) units, rounded down."""
    return units * step // 2


def slack(row, width, row_width):
    """Rule 6: the half units a row of two leaves free when it is justified, else 0."""
    free = width - row_width
    return free if len(row) == 2 and 0 < free <= MAX_JUSTIFY else 0


def span(count, height, step):
    """Rule 7: (top, bottom) of a group of `count` rows `height` units high.

    The first row hangs from top, each further row hangs under the one
    before it, and the last row stands on bottom."""
    top = HEIGHT_LIMIT * UNIT
    spare = top - height * step
    if count == 1:
        bottom = spare // 2 if height <= LOW_HEIGHT else 0
        return bottom + height * step, bottom
    if count == 2:
        margin = min((spare + GAP) // 4, spare // 2)
        return top - margin, margin
    return top - spare // 2, spare - spare // 2


def sign_offset(sign, level):
    """Rule 6: where a sign's outline goes from the centre of the bottom of
    its cell (x to the nearest, y so that its ink stands on the bottom).
    The font bakes it into the variant of the sign."""
    scale = sign.scales[level]
    x_min, y_min, x_max, _ = sign.box
    return -_round(scale * (x_min + x_max) / 2), -_round(scale * y_min)


def _stacked(start, end, group, level, signs):
    """Rules 6 to 8: place the signs of a group that fits at this level.

    Each row starts at its left edge, half its width (or, justified, half
    the group's width) left of the group's axis; each cell starts where the
    one before it ends, a justified second cell its slack further on; each
    sign stands at the centre of the bottom of its cell.
    """
    width, height, rows = measure(group, signs)
    step = half_unit(level)  # across; up, unit(level)
    glyphs = []
    for row, (row_width, _), line in zip(group, rows, _lines(rows, height, unit(level))):
        free = slack(row, width, row_width)
        x = centre(width, step) - half(width if free else row_width, step)
        for index, member in enumerate(row):
            sign = signs[member]
            x += free * step * (index == 1)
            dx, dy = sign_offset(sign, level)
            glyphs.append(Glyph(member, x + half(sign.cell[0], step) + dx, line + dy,
                                level, sign.scales[level]))
            x += sign.cell[0] * step
    return Cluster(start, end, advance(width, step), tuple(glyphs), True)


def _lines(rows, height, step):
    """Rule 7: the line each row stands on, from the baseline."""
    top, bottom = span(len(rows), height, step)
    lines = []
    for _, row_height in rows[:-1]:
        top -= row_height * step
        lines.append(top)
    return lines + [bottom]


def _round(value):
    return math.floor(value + 0.5)


def ink_box(glyph, signs):
    """The ink box of a drawn glyph, relative to the start of its cluster.
    A negative scale mirrors the outline across (section 9)."""
    if is_hatch(glyph.codepoint):
        x0, y0, x1, y1 = hatch_rect(glyph.codepoint)
        return glyph.x + x0, glyph.y + y0, glyph.x + x1, glyph.y + y1
    box = signs[glyph.codepoint].box if glyph.codepoint in signs else CONTROL_BOX
    across = sorted((glyph.x + glyph.scale * box[0], glyph.x + glyph.scale * box[2]))
    return (
        across[0], glyph.y + abs(glyph.scale) * box[1],
        across[1], glyph.y + abs(glyph.scale) * box[3],
    )


# --- 6. Corner insertion ----------------------------------------------------
#
# The controls U+13432..13435 put the sign after them into a corner of the
# sign before them, "within the frame of the preceding hieroglyph" (Unicode
# core specification, chapter 11, "Egyptian Hieroglyph Format Controls",
# figure 11-2; grammar in L2/21-248, table 1). Start is the side where the
# line starts, the left in left-to-right text, where the signs of the code
# charts face; end is the right, where a bird has its back and tail. The
# base comes first in the text even where the inserted sign is read first.
# The owner's rule (O5, decisions 004 and 005): a bird takes at most one
# small sign, inside its own block at the top end, over its back, and the
# bird may shrink a little to give that sign room.
#
# The rules, each stated once:
#
# I1. A run (section 4) that is exactly a sign, a corner control and a sign
#     is an insertion, drawn as one block with the advance of the base as
#     the source has it: an insertion never widens the line. Any other run
#     with a corner control is not well formed and is drawn unstacked, the
#     control as its box (rule 9): a base inside a joiner group, an inserted
#     group, a second insertion on the same base, a control without a sign
#     on both sides, two corner controls in a row. Like every stacked group,
#     an insertion is one cluster for text engines.
# I2. Each sign has, for each corner and each shape of inserted sign (flat:
#     ink at least as wide as high; tall), a zone: a free rectangle in the
#     sign's frame with one corner on the corner of the frame. The frame is
#     the ink box, but a sign that is not low and whose ink reaches TALL or
#     higher reaches up to FRAME_TOP, the height of the tallest signs (a
#     bird's quadrat). The highest ink (top corners) or the lowest ink
#     (bottom corners) in vertical strips of STRIP gives the free depth of
#     each strip; of the rectangles this allows, the one holding the largest
#     box of the shape (2:1 flat, 1:2 tall) is taken, the larger one of
#     equals. A zone keeps GAP from the ink, is at most a quarter block
#     (ZONE_CAP) and is counted in whole STEPs, rounded down. Its anchor is
#     the middle of its bottom edge.
# I3. A sign whose cell (rule 2) is at most INSERT_CELL can be inserted. It
#     is drawn as its variant (its scale in a group) at the largest of
#     INSERT_LEVELS at which its ink fits the zone of its shape. Its size
#     class is its ink at each of those levels, in STEPs, rounded up; it
#     fits where both are at most the zone's.
# I4. A bird may shrink: if the inserted sign fits a bird only at the last
#     of INSERT_LEVELS (half size), the bird is drawn at the scale of the
#     first of SHRINK_LEVELS at which the inserted sign reaches WANTED_LEVEL
#     or a larger level, its ink centred where it was and its ink bottom
#     where it was; its zones are found again from the shrunk outline, in
#     the frame of the full-size sign. If no shrink reaches WANTED_LEVEL,
#     the bird keeps its size. The block keeps the full-size advance. A
#     sign that fits the full-size bird at no level is not a reason to
#     shrink it (rule I6).
# I5. The inserted sign is centred on the middle of the zone. In a top
#     corner it stands GAP above the highest ink under it, its width counted
#     in whole units (at most the zone's) and widened by GAP on both sides,
#     so that it sits on the bird's back and not up in the zone (never above
#     the zone's bottom, which is GAP above the highest ink under the whole
#     zone). In a bottom corner it stands on the base's line, the bottom of
#     its ink. The font has one anchor per base, corner, shape and width.
# I6. Where the inserted sign is larger than INSERT_CELL, or the base has
#     no zone in that corner, or the sign fits it at no level, the control
#     is a horizontal joiner: the two signs stand side by side as a flat
#     group (rules 2 to 8).
#
# Why these values.
# - Strips of 15 follow the slope of a bird's back; half units (45) as the
#   step keep the bread over the vulture one level larger than whole units.
# - The cap is the owner's "quarter block", half the quadrat each way; without
#   it an empty corner (the right half of the reed) would take a full sign.
# - Inserted levels 2 to 5 (0.75 to 0.5): larger, the sign on a big bird's
#   back reads as a second sign; smaller, two strokes are a blot at 26 px.
# - A bird shrinks to level 1 (0.86) or 2 (0.74) only, and only when the
#   inserted sign would otherwise be at half size, to reach level 4 (0.6):
#   the owner's answer to decision 005. Other signs never shrink: a tall
#   sign drawn smaller has room on top for anything, which is a stack, not
#   an insertion, and each shrunk sign is one more glyph in the font.
# - Cells up to 9 by 9 units (18 half units wide): the small signs the owner's dictionary puts
#   into a bird's corner (X1, Z1, Z4, W24, N29, O49, V31...); larger ones
#   would only fit at half size into the largest corners, and each
#   insertable sign costs anchors in the font.
# - FRAME_TOP and TALL: only signs that nearly fill the quadrat get the room
#   up to it; over a short sign (Aa1, N5) a "zone" would be a stack.

TOP_START, BOTTOM_START, TOP_END, BOTTOM_END = 0x13432, 0x13433, 0x13434, 0x13435
CORNERS = {  # control: (top, end)
    TOP_START: (True, False), BOTTOM_START: (False, False),
    TOP_END: (True, True), BOTTOM_END: (False, True),
}
SHAPES = {"flat": (2, 1), "tall": (1, 2)}
STRIP = 15  # the width of the strips in which an outline is measured
STEP = UNIT // 2  # zones and size classes are counted in half units: 45
ZONE_CAP = (WIDTH_LIMIT * STEP // 2 // STEP, HEIGHT_LIMIT * UNIT // 2 // STEP)  # 14 by 12 steps
FRAME_TOP = 1035  # a top corner of a tall sign reaches this high
TALL = 945
INSERT_CELL = (18, 9)  # half units, units: the largest cell an inserted sign may have
INSERT_LEVELS = (2, 3, 4, 5)
WANTED_LEVEL = 4
SHRINK_LEVELS = (1, 2)
BIRDS = range(0x1313F, 0x1317F)  # Gardiner G1 to G54: the signs that may shrink

# width, height: the zone in STEPs, (0, 0) if the corner has no room; x, y:
# its anchor, the middle of its bottom edge, in the coordinates of the sign
# as the source draws it (not lifted); seats: the height at which an
# inserted sign 1, 2, ... units wide stands (rule I5).
Zone = namedtuple("Zone", "width height x y seats")
NO_ZONE = Zone(0, 0, 0, 0, ())


def shrink(box, level):
    """Rule I4: (scale, x, y) of a base drawn smaller at a level: its ink
    centred where it was and its ink bottom where it was."""
    scale = math.floor(unit(level) / UNIT * 1000) / 1000
    return (scale, _round((box[0] + box[2]) / 2 * (1 - scale)), _round(box[1] * (1 - scale)))


def sign_corners(font, glyph, box, codepoint):
    """Rules I2 and I4: {control: ({shape: Zone} of the sign, and for a bird
    of the sign at each of SHRINK_LEVELS)}."""
    lift = sign_lift(box, sign_cell(box))
    top = max(box[3], FRAME_TOP) if box[3] >= TALL and not lift else box[3]
    frame = (box[0], box[1], box[2], top)
    corners = {control: [] for control in CORNERS}
    for level in (0, *SHRINK_LEVELS) if codepoint in BIRDS else (0,):
        high, low = _envelope(font, glyph, frame, shrink(box, level) if level else (1, 0, 0))
        for control, (at_top, end) in CORNERS.items():
            corners[control].append({shape: _zone(high, low, frame, at_top, end, ratio)
                                     for shape, ratio in SHAPES.items()})
    return {control: tuple(zones) for control, zones in corners.items()}


class _Envelope(BasePen):
    """The highest and the lowest ink of an outline in each strip of a frame."""

    def __init__(self, glyphset, x_min, count, transform):
        super().__init__(glyphset)
        self.x_min, self.transform = x_min, transform
        self.high, self.low = [-math.inf] * count, [math.inf] * count
        self.start = self.point = None

    def _moveTo(self, point):
        self.start = self.point = self._place(point)

    def _place(self, point):
        scale, dx, dy = self.transform
        return (point[0] * scale + dx, point[1] * scale + dy)

    def _segment(self, point):
        (x0, y0), (x1, y1) = sorted((self.point, point))
        self.point = point
        first = max(0, int((x0 - self.x_min) // STRIP))
        last = min(len(self.high) - 1, int((x1 - self.x_min) // STRIP))
        for strip in range(first, last + 1):
            left = max(x0, self.x_min + strip * STRIP)
            right = max(left, min(x1, self.x_min + (strip + 1) * STRIP))
            if x1 == x0:
                ends = (y0, y1)
            else:
                ends = tuple(y0 + (y1 - y0) * (x - x0) / (x1 - x0) for x in (left, right))
            self.high[strip] = max(self.high[strip], *ends)
            self.low[strip] = min(self.low[strip], *ends)

    def _lineTo(self, point):
        self._segment(self._place(point))

    def _curveToOne(self, a, b, c):
        p, a, b, c = self.point, self._place(a), self._place(b), self._place(c)
        for i in range(1, 17):  # sixteen chords are within a unit of the curve
            t, u = i / 16, 1 - i / 16
            self._segment(tuple(u ** 3 * p[n] + 3 * u * u * t * a[n] + 3 * u * t * t * b[n] + t ** 3 * c[n]
                                for n in (0, 1)))

    def _qCurveToOne(self, a, b):
        p, a, b = self.point, self._place(a), self._place(b)
        for i in range(1, 9):
            t, u = i / 8, 1 - i / 8
            self._segment(tuple(u * u * p[n] + 2 * u * t * a[n] + t * t * b[n] for n in (0, 1)))

    def _closePath(self):
        if self.point != self.start:
            self._segment(self.start)


_envelopes = {}  # measured outlines, by everything the measure depends on


def _envelope(font, glyph, frame, transform):
    """(high, low): the highest and lowest ink in each strip of the frame,
    counted from its left edge; -inf and inf where a strip has no ink."""
    outline = (tuple((p.x, p.y, p.segmentType) for contour in glyph.contours for p in contour),
               tuple((c.baseGlyph, tuple(c.transformation)) for c in glyph.components))
    key = (outline, frame, transform, STRIP)
    if outline[1] or key not in _envelopes:  # components: measured every time
        pen = _Envelope(font, frame[0], math.ceil((frame[2] - frame[0]) / STRIP), transform)
        glyph.draw(pen)
        _envelopes[key] = (tuple(pen.high), tuple(pen.low))
    return _envelopes[key]


def _zone(high, low, frame, top, end, ratio):
    """Rules I2 and I5: the zone of one corner for one shape."""
    x_min, y_min, x_max, y_top = frame
    width, height, count = x_max - x_min, y_top - y_min, len(high)
    # the ink each strip has under (over) the zone: y_min - GAP (y_top + GAP) if none
    if top:
        ink = [y_min - GAP if y == -math.inf else y for y in high]
        free = [y_top - y for y in ink]
    else:
        ink = [y_top + GAP if y == math.inf else y for y in low]
        free = [y - y_min for y in ink]
    order = range(count - 1, -1, -1) if end else range(count)
    best, best_key, depth = None, None, math.inf
    for strip in order:
        depth = min(depth, free[strip])
        if depth <= GAP:
            break
        covered = x_max - (x_min + strip * STRIP) if end else min(width, (strip + 1) * STRIP)
        # GAP on the inner sides; a side on the edge of the frame faces no ink
        zw = min(ZONE_CAP[0], (covered - (GAP if covered < width else 0)) // STEP)
        zh = min(ZONE_CAP[1], (depth - GAP) // STEP)
        if zw <= 0 or zh <= 0:
            continue
        key = (min(zw / ratio[0], zh / ratio[1]), zw * zh)
        if best_key is None or key > best_key:
            best, best_key = (int(zw), int(zh), depth), key
    if best is None:
        return NO_ZONE
    zw, zh, depth = best
    x = _round(x_max - zw * STEP / 2 if end else x_min + zw * STEP / 2)
    if not top:  # on the bottom of the frame, the base's line
        return Zone(zw, zh, x, y_min, (y_min,) * ((zw + 1) // 2))

    def seat(n):  # GAP above the highest ink under n STEPs, widened by GAP
        left, right = x - n * STEP / 2 - GAP, x + n * STEP / 2 + GAP
        under = [ink[s] for s in range(count)
                 if x_min + (s + 1) * STRIP > left and x_min + s * STRIP < right]
        return math.ceil(max(under, default=y_min - GAP)) + GAP

    # the zone itself stands GAP above the highest ink under it
    seats = tuple(seat(min(2 * units, zw)) for units in range(1, (zw + 1) // 2 + 1))
    return Zone(zw, zh, x, math.ceil(y_top - depth) + GAP, seats)


def is_insertion(run):
    """Rule I1: a sign, a corner control, a sign, and nothing else."""
    return len(run) == 3 and run[1] in CORNERS and is_sign(run[0]) and is_sign(run[2])


def shape_of(sign):
    """Flat if its ink is at least as wide as high, else tall."""
    return "flat" if sign.box[2] - sign.box[0] >= sign.box[3] - sign.box[1] else "tall"


def insert_size(sign, level):
    """Rule I3: the size class of an inserted sign at a level, (width,
    height) of its ink in STEPs, rounded up."""
    scale = sign.scales[level]
    return tuple(math.ceil(round(size * scale, 6) / STEP)
                 for size in (sign.box[2] - sign.box[0], sign.box[3] - sign.box[1]))


def seat_width(size):
    """Rule I5: the width of an inserted sign of this size class, in whole
    units: the width its seat is found for."""
    return (size[0] + 1) // 2


def insertable(sign):
    """Rule I3: a sign small enough to be inserted."""
    return sign.cell[0] <= INSERT_CELL[0] and sign.cell[1] <= INSERT_CELL[1]


def insert_level(zone, sign):
    """Rule I3: the largest of INSERT_LEVELS at which the sign fits the zone,
    or None."""
    for level in INSERT_LEVELS:
        width, height = insert_size(sign, level)
        if width <= zone.width and height <= zone.height:
            return level
    return None


def insertion(base, control, inserted, signs):
    """Rules I3, I4 and I6: (level of the base, level of the inserted sign),
    or None if the control is to be a horizontal joiner."""
    sign = signs[inserted]
    if not insertable(sign):
        return None
    full, *shrunk = (zones[shape_of(sign)] for zones in signs[base].corners[control])
    level = insert_level(full, sign)
    if level == INSERT_LEVELS[-1]:
        for base_level, zone in zip(SHRINK_LEVELS, shrunk):  # only birds have these
            found = insert_level(zone, sign)
            if found is not None and found <= WANTED_LEVEL:
                return base_level, found
    return None if level is None else (0, level)


def _inserted(start, end, run, signs):
    """Rules I1 to I6: the block of an insertion."""
    base, control, inserted = run
    found = insertion(base, control, inserted, signs)
    if found is None:  # I6
        group = ((base, inserted),)
        return _stacked(start, end, group, fit_level(*measure(group, signs)[:2]), signs)
    level, inner = found
    b, sign = signs[base], signs[inserted]
    zone = b.corners[control][(0, *SHRINK_LEVELS).index(level)][shape_of(sign)]
    if level:
        scale, x, y = shrink(b.box, level)
        drawn = Glyph(base, x, y + b.lift, level, scale)
    else:
        drawn = Glyph(base, 0, b.lift, 0, 1.0)
    dx, dy = sign_offset(sign, inner)
    seat = zone.seats[seat_width(insert_size(sign, inner)) - 1]
    glyph = Glyph(inserted, zone.x + dx, b.lift + seat + dy, inner, sign.scales[inner])
    return Cluster(start, end, b.advance, (drawn, glyph), True)


# --- 7. Automatic stacking --------------------------------------------------
#
# Almost no text carries the controls: word lists, web pages, course
# texts and hieroglyph keyboards give plain sign sequences. The automatic
# pass reads such text and adds the controls that a table of known sign
# sequences says belong there (automatic.txt, next to this file: what is in
# it and where it comes from is said in its header). Everything after that
# is the layout above, so a stacked group looks the same whether its
# controls were typed or implied.
#
# The rules, each stated once:
#
# A1. A stretch is a longest run of signs with nothing between them. Only
#     signs of one stretch are stacked together, so any other character
#     keeps two signs apart: a space, ZWNJ (U+200C), a letter, any default
#     ignorable.
# A2. A stretch that follows such a character, or the start of the text,
#     begins a word; one followed by such a character, or the end of the
#     text, ends a word. A stretch that touches a control on a side (the
#     controls of rules 9 and 10) does not begin or end a word there.
# A3. An entry of the table is a sign sequence, which may be marked to hold
#     only where a word begins (START before it) or ends (END after it),
#     and its arrangement: the sequence cut into blocks, each block a sign
#     or a group written with the controls (rules 3 and 10).
# A4. A stretch is read from its start. At a word start, the longest entry
#     marked START that the stretch begins with is taken, if any; elsewhere,
#     and if there is none, the longest unmarked entry that begins at that
#     sign (an entry marked END holds only if the word ends right after it).
#     An entry that is taken implies the controls of its arrangement and the
#     reading goes on after it; if none is taken, the sign stays alone and
#     the reading goes on at the next sign. An entry may be all single
#     signs: it then only keeps a known sequence apart.
# A5. Explicit controls win. A sign right after a control never starts an
#     entry; a block of an entry that reaches the sign right before a
#     control is not formed (its signs stay alone), and the other blocks of
#     that entry are.
# A6. Every arrangement in the table is a group the layout stacks (rule 9
#     never applies to it), so the automatic pass never draws a control box.
#
# Then a rule by shape alone (the owner, 2026-11-25: two low, wide signs in
# a row share one block, one above the other), for the signs no entry took:
#
# A7. A half-block sign is a hieroglyph whose cell (rule 2) is at most half
#     the quadrat high (LOW_HEIGHT units: the low signs of rule 1) and at
#     least half of it wide (WIDTH_LIMIT / 2 half units): it fills the
#     width of a block and leaves half of its height free. Two of them fill
#     a block at full size (level 0). Blanks and lost signs are not
#     hieroglyphs and never count.
# A8. After the table (A4), the half-block signs of a stretch that no entry
#     took and that stand in a row form runs. A run right after a sign that
#     is lower than the quadrat (cell under HEIGHT_LIMIT units), not
#     half-block and not taken, stays as it is: that sign may stand above
#     the first of the run (as p above n). Any other run is cut two by
#     two from its start into blocks, the first sign above the second; a
#     sign left over at its end stays alone. So three in a row are a block
#     of two and a lone sign, four are two blocks; a sign doubled is a
#     block like any other pair, a sign tripled a block and a lone sign.
# A9. Rule A5 holds for these blocks too: a sign right after a control
#     starts no block (the next one may), and a block that reaches the sign
#     right before a control is not formed. A block of two half-block signs
#     is at most 12 units high and 28 half units wide, so it is always
#     stacked at level 0 (rule A6), and its geometry is that of any group
#     (rules 3 to 8): each sign takes half of the block.
#
# Why these choices (measured on dictionary words typed plainly, a check
# that is not part of the font): pairs of two signs that are both low and
# at least half the quadrat wide are written one above the other about
# three times in four; narrower low signs (the bread, the stroke) only
# about half the time, and a width limit of 16 to 26 half units, or a
# height limit of 5 units, gives no better precision and fewer stacks.
# Leaving a run after a lower sign apart takes away most of the wrong
# stacks across two blocks (a small sign over the first sign of the run)
# for a sixth of the stacks. Three in a row are a pair and a lone sign
# about twice as often as a stack of three; a stack of three of the same
# sign is rare and would cost a rule per sign.
#
# The font does the same in GSUB (features.py) under feature "calt", which a
# text engine or a page can switch off ("font-feature-settings: 'calt' 0");
# layout(..., table=None) is the font with the feature off.

AUTOMATIC_TABLE = Path(__file__).with_name("automatic.txt")
START, END = "start", "end"  # the marks of an entry that holds at a word start or end
NOTATION = {":": VERTICAL_JOINER, "*": HORIZONTAL_JOINER,
            "^ts": TOP_START, "^bs": BOTTOM_START, "^te": TOP_END, "^be": BOTTOM_END}
CODE = re.compile(r"([A-Z][a-z]?)(\d+)([a-z]*)")


def code_point(code):
    """The sign of a Gardiner code, as Unicode names it: D21 is U+1308B
    EGYPTIAN HIEROGLYPH D021, Aa1 is AA001, N35a is N035A."""
    letters, number, suffix = CODE.fullmatch(code).groups()
    return ord(unicodedata.lookup(f"EGYPTIAN HIEROGLYPH {letters.upper()}{int(number):03d}{suffix.upper()}"))


def code_of(codepoint):
    """The Gardiner code of a sign: the inverse of code_point()."""
    name = unicodedata.name(chr(codepoint)).rsplit(" ", 1)[-1]
    letters, number, suffix = re.fullmatch(r"([A-Z]+?)(\d+)([A-Z]*)", name).groups()
    return f"{letters[0]}{letters[1:].lower()}{int(number)}{suffix.lower()}"


def parse_entry(text):
    """'<G14^teX1-B1>' -> (key, arrangement): the key the sign sequence with
    START and END, the arrangement a tuple of blocks of code points."""
    start, end = text.startswith("<"), text.endswith(">")
    blocks = []
    for block in text.strip("<>").split("-"):
        tokens = re.findall(r"\^(?:ts|bs|te|be)|[:*]|[A-Z][a-z]?\d+[a-z]*", block)
        if "".join(tokens) != block:
            raise ValueError(f"not an entry: {text}")
        blocks.append(tuple(NOTATION[t] if t in NOTATION else code_point(t) for t in tokens))
    signs = tuple(c for block in blocks for c in block if is_sign(c))
    return (START,) * start + signs + (END,) * end, tuple(blocks)


def write_entry(key, arrangement):
    """The inverse of parse_entry()."""
    names = {control: text for text, control in NOTATION.items()}
    text = "-".join("".join(names.get(c) or code_of(c) for c in block) for block in arrangement)
    return "<" * (key[0] == START) + text + ">" * (key[-1] == END)


def automatic_table(path=AUTOMATIC_TABLE):
    """{key: arrangement} of the table file (rule A3)."""
    table = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            key, arrangement = parse_entry(line)
            if key in table:
                raise ValueError(f"entry twice: {line}")
            table[key] = arrangement
    return table


def check_table(table, signs):
    """Rule A6 and the form of the entries: [problems]."""
    problems = []
    for key, arrangement in table.items():
        text = write_entry(key, arrangement)
        plain = [c for c in key if c not in (START, END)]
        if len(plain) < 2 or any(c not in signs for c in plain):
            problems.append(f"{text}: fewer than two signs, or a sign the font lacks")
        for block in arrangement:
            if len(block) == 1:
                continue
            if is_insertion(list(block)):
                continue  # rules I1 to I6 always draw a block
            group = parse(list(block))
            if group is None or fit_level(*measure(group, signs)[:2]) is None:
                problems.append(f"{text}: block {write_entry((), (block,))} would not be stacked")
    return problems


HALF_HEIGHT = LOW_HEIGHT  # units: a half-block sign is at most this high (rule A7)
HALF_WIDTH = WIDTH_LIMIT // 2  # half units: and at least this wide
SOURCE = Path(__file__).resolve().parents[2] / "sources" / "Thoth-Regular.ufo"
_signs = []


def default_signs():
    """The sign table of the source font, read once."""
    if not _signs:
        import ufoLib2
        _signs.append(sign_table(ufoLib2.Font.open(SOURCE)))
    return _signs[0]


def half_block(codepoint, signs):
    """Rule A7: a sign at most half the quadrat high and at least half of it wide."""
    sign = signs.get(codepoint)
    return (sign is not None and codepoint in HIEROGLYPHS
            and sign.cell[1] <= HALF_HEIGHT and sign.cell[0] >= HALF_WIDTH)


def shape_blocks(codepoints, start, end, free, signs, bound_start=False):
    """Rules A8 and A9 on the signs codepoints[start:end] of one stretch,
    `free` the indices no entry took: [(index, arrangement)]."""
    half = [at in free and half_block(codepoints[at], signs) for at in range(start, end)]
    found, at = [], start
    while at < end:
        if not half[at - start]:
            at += 1
            continue
        run_end = at
        while run_end < end and half[run_end - start]:
            run_end += 1
        before = codepoints[at - 1] if at > start else None
        if before is not None and at - 1 in free and signs[before].cell[1] < HEIGHT_LIMIT:
            at = run_end  # a lower sign may stand above the first: the run stays as it is
            continue
        if bound_start and at == start:
            at += 1  # rule A9: a sign right after a control starts no block
        while run_end - at >= 2:  # two by two, the first above the second
            found.append((at, ((codepoints[at], VERTICAL_JOINER, codepoints[at + 1]),)))
            at += 2
        at = run_end
    return found


def automatic(codepoints, table, signs=None):
    """Rules A1 to A9: (text, origin), the text with the implied controls,
    and for each of its characters the index in codepoints it comes from
    (an implied control: the sign before it). signs: the sign table, by
    default that of the source font."""
    signs = signs if signs is not None else default_signs()
    joins = {}  # index of a sign: the controls implied after it
    longest = max(map(len, table), default=0)
    index, count = 0, len(codepoints)
    while index < count:
        if not is_sign(codepoints[index]):
            index += 1
            continue
        end = index
        while end < count and is_sign(codepoints[end]):
            end += 1
        bound_start = index > 0 and codepoints[index - 1] in CONTROLS
        bound_end = end < count and codepoints[end] in CONTROLS
        stretch = (*((START,) * (not bound_start)), *codepoints[index:end], *((END,) * (not bound_end)))
        first = index - (not bound_start)  # the index of stretch[0] in codepoints
        position, taken = 0, []
        while position < len(stretch):
            if stretch[position] == END or (bound_start and position == 0):
                position += 1
                continue
            for length in range(min(longest, len(stretch) - position), 1, -1):
                arrangement = table.get(stretch[position:position + length])
                if arrangement is not None:
                    offset = position + (stretch[position] == START)
                    taken.append((first + offset, arrangement))
                    position += length
                    break
            else:
                position += 1
        free = set(range(index, end))  # rule A8: the signs no entry took
        for at, arrangement in taken:
            free -= set(range(at, at + sum(is_sign(c) for block in arrangement for c in block)))
        taken += shape_blocks(codepoints, index, end, free, signs, bound_start)
        for at, arrangement in taken:
            for block in arrangement:
                size = sum(map(is_sign, block))
                if not (bound_end and at + size == end):  # rule A5
                    sign = at
                    for c in block[1:]:
                        if is_sign(c):
                            sign += 1
                        else:
                            joins.setdefault(sign, []).append(c)
                at += size
        index = end
    text, origin = [], []
    for i, codepoint in enumerate(codepoints):
        text.append(codepoint)
        origin.append(i)
        for control in joins.get(i, ()):
            text.append(control)
            origin.append(i)
    return text, origin


# --- 8. Enclosures ----------------------------------------------------------
#
# The controls U+1343C..1343F draw a cartouche, a ḥwt or a walled
# enclosure around a stretch of groups: "the combination creates a
# full-form enclosing cartouche with horizontal lines above and below"
# (Unicode core specification, chapter 11, "Egyptian Hieroglyph Format
# Controls", figure 11-4). The syntax is that of L2/21-248, table 3 and
# section 3:
#
#     enclosure       ::= [ opening ] inner_enclosure [ closing ]
#     inner_enclosure ::= BEGIN group* END | BEGIN_WALLED group* END_WALLED
#
# with "the tokenizer ... required to analyze an opening delimiter
# immediately preceding [BEGIN] to open an enclosure, and a closing
# delimiter immediately following [END] to close it"; either delimiter may
# be missing (damaged text), and the begin and end controls "must be used
# in pairs". The delimiters are the signs of L2/21-248 table 13: cartouche
# V11A, V11D / V11B, V11C; ḥwt O6A-O6C / O6D-O6F; walls O36A, O36C / O36B,
# O36D (the serekh end O33A is left out: it has no band to join). The
# proposal does not expect nested enclosures to be implemented (section 3,
# "middle insertion versus pairs of delimiters"), and neither are they
# here; nor is an enclosure a member of a joiner group.
#
# The rules, each stated once:
#
# E1. An enclosure is BEGIN, one or more characters that are signs, other
#     controls (any group, well formed or not), damage modifiers that are
#     no part of a literal (rule M3) or nonspacing marks of other scripts,
#     and the END of the same pair; with the opening delimiter
#     right before BEGIN and the closing delimiter right after END, if
#     they are there. Nothing else forms one: an empty pair, a space, a
#     default ignorable (ZWJ, ZWNJ, also a variation selector, which is a
#     nonspacing mark: the font cannot tell them apart), another enclosure
#     control or a delimiter inside, a pair of the other kind (rule E5 adds
#     one more).
# E2. Every enclosure control, and a delimiter right before a begin
#     control or right after an end control, separates the text on its two
#     sides as a space does, whether or not an enclosure forms: no group
#     (rule 9) and no word (rules A1, A2) reaches across it.
# E3. A control that is no part of an enclosure is its fallback box, a
#     delimiter that is no part of one a lone sign (rules 1 and 9).
# E4. Inside, the text between the controls is laid out by rules 1 to 11
#     as a text of its own, and then: a lone sign is drawn as a group of
#     one sign at level 0 (rules 6 to 8), so it stands in the quadrat
#     instead of where the source puts it; an insertion block (rule I1) is
#     moved up or down as a whole, so that its base stands where that sign
#     stands as a group of one; groups and boxes stay as they are. All ink
#     is then between the baseline and ENCLOSED_TOP, at full size.
# E5. An enclosure that holds an insertion block taller than that, with
#     any sign in any corner of its base (ENCLOSABLE), is not formed (E3).
# E6. The ring keeps GAP from the quadrat: the inner edges of its bands
#     are at INNER. Each delimiter is drawn scaled by its own factor and
#     moved so that the inner edges of its bands land there; its advance
#     is scaled with it. Under every cluster inside, the bands of the
#     profile piece of the kind (PROFILE) run from its start to its
#     advance W: two pieces of SEGMENTS long M, the largest that is at
#     most W, one from the start and one to the end (they overlap where M
#     is more than half of W). A walled enclosure also has W // period
#     merlons on each band, centred on the cluster. A cluster with no
#     advance draws no lines.
# E7. Clusters: the opening delimiter and BEGIN are one cluster, END and
#     the closing delimiter another; a control without its delimiter is a
#     cluster with no advance; the groups inside keep their clusters.
#
# Why these choices.
# - Content at full size (factor 1, owner rule O3): only the ring is fitted.
#   Noto's cartouche pieces are 1,227 high, their inside 1,087, against
#   1,080 + 34 for a quadrat and its gap: a ring 2.5 % larger than the lone
#   cartouche holds every group with GAP to spare. Shrinking the content
#   instead would need levels the font does not have (one consistent
#   factor on top of seven levels) or a second copy of every glyph.
# - Lone signs as groups of one: the source draws them from 326 below the
#   baseline to 1,324 above it; inside a ring they must stand in the
#   quadrat like the members of a group, and that layout already exists.
# - Lines per cluster: the font cannot stretch a glyph, but every cluster
#   knows its advance, so two overlapping pieces of six lengths cover
#   any width without a glyph per length.

BEGIN_ENCLOSURE, END_ENCLOSURE, BEGIN_WALLED, END_WALLED = 0x1343C, 0x1343D, 0x1343E, 0x1343F
ENCLOSURE = {  # control: (kind, begins)
    BEGIN_ENCLOSURE: ("plain", True), END_ENCLOSURE: ("plain", False),
    BEGIN_WALLED: ("walled", True), END_WALLED: ("walled", False),
}
OPENINGS = (0x13258, 0x13259, 0x1325A, 0x13286, 0x13288, 0x13379, 0x1342F)  # O6A-C, O36A, O36C, V11A, V11D
CLOSINGS = (0x1325B, 0x1325C, 0x1325D, 0x13287, 0x13289, 0x1337A, 0x1337B)  # O6D-F, O36B, O36D, V11B, V11C
PROFILE = {"plain": 0x13379, "walled": 0x13288}  # the piece whose bands the lines continue
ENCLOSED_TOP = HEIGHT_LIMIT * UNIT - GAP  # 1046: content ink is between 0 and this
INNER = (-GAP, ENCLOSED_TOP + GAP)  # the inner edges of the bands: -34 and 1080
SEGMENTS = (64, 128, 256, 512, 1024, 2048)  # line lengths; any advance up to 4096 is two of one
MERLON = (85, 34, 51)  # width, gap, height of a merlon on the top of O36C, as the source draws it
OPEN_END = 25  # how far in from the open end of a delimiter its bands are measured

# A drawn part of an enclosure, x and y from the start of its cluster:
# ("piece", code point) a delimiter joined to the lines (its outline moved
# and scaled, as Ring says), ("line", kind, length, "start" or "end") a
# piece of the lines (from x on, or up to x), ("merlons", kind, count)
# centred on x.
Frame = namedtuple("Frame", "part x y")
# scale, dy: the delimiter's outline is scaled by scale about (0, 0) and
# moved up by dy; advance: its advance then; bands: the eight edges of its
# two bands at the open end, bottom to top, as the source draws them;
# opening: whether it opens.
Ring = namedtuple("Ring", "scale dy advance bands opening")


class _Crossings(BasePen):
    """Where an outline crosses the vertical line x = at."""

    def __init__(self, at):
        super().__init__(None)
        self.at, self.found, self.point, self.start = at, [], None, None

    def _moveTo(self, point):
        self.point = self.start = point

    def _lineTo(self, point):
        (x0, y0), (x1, y1) = self.point, point
        if (x0 <= self.at < x1) or (x1 <= self.at < x0):
            self.found.append(y0 + (y1 - y0) * (self.at - x0) / (x1 - x0))
        self.point = point

    def _curveToOne(self, a, b, c):
        p = self.point
        for i in range(1, 33):
            t, u = i / 32, 1 - i / 32
            self._lineTo(tuple(u ** 3 * p[n] + 3 * u * u * t * a[n] + 3 * u * t * t * b[n] + t ** 3 * c[n]
                               for n in (0, 1)))

    def _qCurveToOne(self, a, b):
        p = self.point
        for i in range(1, 17):
            t, u = i / 16, 1 - i / 16
            self._lineTo(tuple(u * u * p[n] + 2 * u * t * a[n] + t * t * b[n] for n in (0, 1)))

    def _closePath(self):
        if self.point != self.start:
            self._lineTo(self.start)


def ring_table(font, signs):
    """{delimiter: Ring} (rule E6), measured on the source outlines: the
    eight crossings of a vertical line OPEN_END in from the open end."""
    table = {}
    for codepoint in (*OPENINGS, *CLOSINGS):
        sign, opening = signs[codepoint], codepoint in OPENINGS
        pen = _Crossings(sign.box[2] - OPEN_END if opening else sign.box[0] + OPEN_END)
        font[sign.name].draw(pen)
        bands = tuple(round(y) for y in sorted(pen.found))
        if len(bands) != 8:
            raise ValueError(f"{sign.name}: {len(bands)} band edges at the open end, expected 8")
        scale = (INNER[1] - INNER[0]) / (bands[4] - bands[3])
        table[codepoint] = Ring(scale, INNER[0] - scale * bands[3], _round(sign.advance * scale), bands, opening)
    return table


_rings = []


def default_rings():
    """The ring table of the source font, read once."""
    if not _rings:
        import ufoLib2
        _rings.append(ring_table(ufoLib2.Font.open(SOURCE), default_signs()))
    return _rings[0]


def band_edges(kind, rings=None):
    """The eight edges of the bands of the lines of a kind, in font units."""
    ring = (rings or default_rings())[PROFILE[kind]]
    return tuple(_round(ring.scale * y + ring.dy) for y in ring.bands)


def merlon_size(rings=None):
    """(width, gap, height) of the merlons of a walled line: the source's,
    scaled as the walled profile piece is."""
    scale = (rings or default_rings())[PROFILE["walled"]].scale
    return tuple(_round(size * scale) for size in MERLON)


def segment(width):
    """Rule E6: the length of the two line pieces under a cluster, or None."""
    fitting = [length for length in SEGMENTS if length <= width]
    return fitting[-1] if fitting else None


def merlon_count(width, rings=None):
    merlon, gap, _ = merlon_size(rings)
    return width // (merlon + gap)


def lift_in_enclosure(sign):
    """Rule E4: how far a lone sign's ink moves to stand as a group of one."""
    return span(1, sign.cell[1], UNIT)[1] - (sign.box[1] + sign.lift)


_enclosable = {}


def enclosable(signs):
    """Rule E5: {(base, level): True if every insertion block on that base
    drawn at that level fits under ENCLOSED_TOP once moved (rule E4)}."""
    key = id(signs)
    if key not in _enclosable:
        found = {}
        for base in sorted(signs):
            for control in CORNERS:
                for inserted in signs:
                    if not insertable(signs[inserted]):
                        continue
                    placed = insertion(base, control, inserted, signs)
                    if placed is None:
                        continue
                    cluster = _inserted(0, 3, [base, control, inserted], signs)
                    top = max(ink_box(glyph, signs)[3] for glyph in cluster.glyphs)
                    fits = top + lift_in_enclosure(signs[base]) <= ENCLOSED_TOP
                    found[(base, placed[0])] = found.get((base, placed[0]), True) and fits
        _enclosable[key] = (signs, found)
    return _enclosable[key][1]


def delimiters(codepoints):
    """Rule E2: the indices of the delimiters next to an enclosure control."""
    found = set()
    for index, codepoint in enumerate(codepoints):
        if codepoint not in ENCLOSURE:
            continue
        if ENCLOSURE[codepoint][1] and index and codepoints[index - 1] in OPENINGS:
            found.add(index - 1)
        if not ENCLOSURE[codepoint][1] and index + 1 < len(codepoints) and codepoints[index + 1] in CLOSINGS:
            found.add(index + 1)
    return found


def _content(codepoint):
    """Rule E1: a character that may stand between the two controls. The
    text has no modifiers here: section 9 has taken out those of literals
    and left STRAY for the others."""
    from glyphs import IGNORABLE  # glyphs.py imports this file: imported when needed
    return (is_sign(codepoint) or (codepoint in CONTROLS and codepoint not in ENCLOSURE) or codepoint == STRAY
            or (not 0x13000 <= codepoint <= 0x1345F and codepoint not in IGNORABLE
                and unicodedata.category(chr(codepoint))[0] == "M"))


def enclosures(codepoints):
    """Rule E1: [(begin, end, kind)] of the pairs that enclose something;
    rule E5 is checked later, on the layout of what they enclose."""
    found = []
    for begin, codepoint in enumerate(codepoints):
        if codepoint not in ENCLOSURE or not ENCLOSURE[codepoint][1]:
            continue
        end = begin + 1
        while end < len(codepoints) and _content(codepoints[end]):
            end += 1
        kind = ENCLOSURE[codepoint][0]
        if end > begin + 1 and end < len(codepoints) and ENCLOSURE.get(codepoints[end]) == (kind, False):
            found.append((begin, end, kind))
    return found


def _cuts(codepoints):
    """Rule E2: the indices of the enclosure controls and their delimiters."""
    return sorted({i for i, c in enumerate(codepoints) if c in ENCLOSURE} | delimiters(codepoints))


def automatic_parts(codepoints, table, signs=None):
    """automatic() (section 7) as rule E2 has it: of each part of the text
    between the cuts on its own, as the layout of the parts and of what an
    enclosure holds reads it; the same (text, origin)."""
    text, origin, start = [], [], 0
    cuts = _cuts(codepoints)
    for cut in [*cuts, len(codepoints)]:
        implied, inner = automatic(codepoints[start:cut], table, signs)
        text += implied
        origin += [start + i for i in inner]
        if cut < len(codepoints):
            text.append(codepoints[cut])
            origin.append(cut)
        start = cut + 1
    return text, origin


def _with_enclosures(codepoints, signs, table):
    """Rules E1 to E7: lay out text that has enclosure controls (and no
    modifiers of literals: section 9 has taken them out, so a mirror
    control left in the text is a control)."""
    cuts = _cuts(codepoints)
    clusters, start = [], 0
    for cut in [*cuts, len(codepoints)]:  # rule E2: each part on its own
        clusters += [c._replace(start=c.start + start, end=c.end + start)
                     for c in layout(codepoints[start:cut], signs, table, modifiers=False)]
        if cut < len(codepoints):
            clusters.append(_unstacked(cut, codepoints[cut], signs))  # rule E3, unless formed
        start = cut + 1
    for begin, end, kind in enclosures(codepoints):
        inside = _enclosed(codepoints[begin + 1:end], begin + 1, kind, signs, table)
        if inside is None:  # rule E5
            continue
        opening = begin - 1 if begin and codepoints[begin - 1] in OPENINGS else None
        closing = end + 1 if end + 1 < len(codepoints) and codepoints[end + 1] in CLOSINGS else None
        first = begin if opening is None else opening
        last = end if closing is None else closing
        ends = [_piece(opening, begin, codepoints), _piece(closing, end, codepoints)]
        clusters = ([c for c in clusters if c.end <= first] + [ends[0], *inside, ends[1]]
                    + [c for c in clusters if c.start > last])
    return clusters


def _piece(delimiter, control, codepoints):
    """Rule E7: the cluster of a control and its delimiter, if any."""
    if delimiter is None:
        return Cluster(control, control + 1, 0, (), False)
    ring = default_rings()[codepoints[delimiter]]
    first, last = sorted((delimiter, control))
    return Cluster(first, last + 1, ring.advance, (), False, (Frame(("piece", codepoints[delimiter]), 0, 0),))


def _enclosed(content, offset, kind, signs, table):
    """Rule E4 to E6: the clusters of what an enclosure holds, or None."""
    text, origin = automatic(content, table, signs) if table is not None else (content, range(len(content)))
    found = []
    strays = [Cluster(i, i + 1, CONTROL_ADVANCE, (Glyph(STRAY, 0, 0, 0, 1.0),), False)  # rule M3: a box
              for i, c in enumerate(text) if c == STRAY]
    for cluster in sorted(layout(text, signs, modifiers=False) + strays, key=lambda c: c.start):
        run = text[cluster.start:cluster.end]
        start, end = origin[cluster.start] + offset, origin[cluster.end - 1] + 1 + offset
        if not cluster.stacked and cluster.glyphs[0].codepoint in signs:  # a lone sign
            cluster = _stacked(start, end, ((cluster.glyphs[0].codepoint,),), 0, signs)
        elif cluster.stacked and is_insertion(run) and insertion(*run, signs) is not None:
            base = cluster.glyphs[0]
            if not enclosable(signs)[(base.codepoint, base.level)]:
                return None
            move = lift_in_enclosure(signs[base.codepoint])
            cluster = cluster._replace(start=start, end=end,
                                       glyphs=tuple(g._replace(y=g.y + move) for g in cluster.glyphs))
        else:
            cluster = cluster._replace(start=start, end=end)
        found.append(cluster._replace(frame=lines(kind, cluster.advance)))
    return found


def lines(kind, width):
    """Rule E6: the frame parts under a cluster `width` wide."""
    length = segment(width)
    if length is None:
        return ()
    parts = [Frame(("line", kind, length, "start"), 0, 0), Frame(("line", kind, length, "end"), width, 0)]
    count = merlon_count(width) if kind == "walled" else 0
    if count:
        parts.append(Frame(("merlons", kind, count), width // 2, 0))
    return tuple(parts)


# --- 9. Sign modifiers: mirroring and damage ---------------------------------
#
# Unicode 15 added a control that mirrors the sign before it (U+13440) and
# fifteen modifiers that mark the sign before it as damaged (U+13447 to
# U+13455). The Unicode core specification (chapter 11, "Egyptian
# Hieroglyphs": "Mirroring", "Damage Modifiers") says what they mean; the
# proposal L2/21-248, table 3, gives their place:
#
#     literal ::= sign [ VS1 | VS2 | VS3 ] [ mirror ] [ damaged ]
#
# Damage divides "the surface" of a sign into four quarters; the modifier,
# less U+13446, is four bits, one for each damaged quarter: 1 top start,
# 2 bottom start, 4 top end, 8 bottom end. Start is where the line starts
# (the left in left-to-right text, where the signs of the code charts
# face), as for the corner insertions of section 6.
#
# The rules, each stated once:
#
# M1. A literal is a hieroglyph (blanks and lost signs are not: they take
#     no modifier), then the mirror control or not, then one damage
#     modifier or not, in this order. Between them may stand any default
#     ignorable but ZWJ and ZWNJ: Unicode allows VS1 to VS3 (rotation)
#     there; Thoth has no rotated forms and draws no selector, and cannot
#     tell the other invisible ignorables from them.
# M2. The modifiers of a literal belong to its sign. They are taken out of
#     the text before sections 4 to 8 lay it out, so a modified sign is
#     grouped, inserted, stacked automatically and enclosed exactly as the
#     sign is; in particular a modifier never starts or ends a word (rule
#     A2), and never makes, breaks or moves an enclosure (a delimiter and
#     its modifiers stand right before the begin control): Unicode gives it
#     no such meaning. The literal is one cluster with its
#     sign, or with the sign's group.
# M3. A modifier that is not part of a literal (no sign before it, a second
#     one, the mirror after a damage modifier, after a blank, after ZWJ) is
#     drawn as today: the mirror control is a control, so its run is drawn
#     unstacked with the control as its box (rule 9); a damage modifier is
#     drawn as the same box, with the advance of a control, and like any
#     other character it ends a run (rule 9) and a stretch (rule A1).
# M4. Mirror: the sign is drawn mirrored about the vertical line through
#     the middle of its ink, so that its ink box, cell, level, advance and
#     place stay as they are (a Glyph with a negative scale: x is scaled by
#     scale, y by -scale). A sign that is horizontally symmetric (every
#     on-curve point of its flipped outline within SYMMETRY units of one of
#     the outline, and back) is drawn as it is and the control draws
#     nothing: Unicode says such signs "do not require mirroring" and lets
#     a font show the control; Thoth does not.
# M5. A corner control after a mirrored (not symmetric) bird (MIRRORED_BASES)
#     is read as its mirror image (start and end swapped): the zones of a
#     mirrored base are those of the sign with start and end swapped,
#     mirrored about the middle of its ink, so the line's start and end
#     stay where they are while the bird turns. The inserted sign stands
#     mirrored with its zone. After any other mirrored sign a corner control
#     is not supported: it is read as an unsupported control, so its run is
#     drawn unstacked with the control as its box (rule 9).
# M6. Damage shades the quarters the modifier names of the sign's cell at
#     the level it is drawn at, split by the cell's middle lines. The cell
#     of a sign in a group, and of an inserted sign, is the one it stands in
#     (its ink on the bottom of the cell, centred across: the origin of its
#     variant); the cell of a lone sign, and of the base of an insertion,
#     is placed around its ink, the bottom of the cell on the bottom of the
#     ink and centred on it, at the level it is drawn at (a shrunk bird's).
#     The middle point is the middle of the cell, rounded down.
# M7. Shading is diagonal lines rising towards the end at 45 degrees,
#     HATCH_PERIOD apart across and HATCH_STROKE wide across, one line
#     through the middle point, so the quarters join. Each damaged quarter
#     is one piece: a rectangle from the middle point outwards,
#     HATCH_TILE times v across and HATCH_TILE times w up, v and w the
#     quarter's size in tiles rounded to the nearest and at least one,
#     reaching HATCH_OVERLAP over the middle lines so that pieces join
#     without a seam. The lines keep their size and spacing at every level,
#     a texture on the surface; the pieces follow the sign in its cluster,
#     its quarters in the order of their bits.
# M8. A sign in a group or inserted is mirrored only at MIRROR_LEVELS, the
#     levels of about 95 % of the signs in the groups of the owner's
#     dictionary. At a smaller level it is drawn as it is, and the mirror
#     control is drawn small over the middle of its cell (MIRROR_BOX of the
#     fallback box), as Unicode lets a font show the control. Lone signs and
#     shrunk birds are always mirrored.
# M9. Inside an enclosure (section 8) these rules apply to what rule E4
#     draws: a lone sign is mirrored and shaded as the sign of its group of
#     one, the base of an insertion on the cell around its ink, moved up or
#     down with it. The modifiers of a delimiter that joins an enclosure
#     draw nothing: it is drawn as a part of the ring (rule E6), whose ends
#     have one form each; a delimiter that joins none is a sign as any other.
#
# Why these values.
# - A symmetry tolerance of 3 units is below a pixel at every size the
#   signs are read at: a sign within it looks the same mirrored.
# - Tiles of 45 units, the half unit: a quarter of a cell is a whole number
#   of half units high and up to a quarter unit off across, so the shading
#   ends within a third of a gap of the quarter's edge.
# - Lines 120 apart and 22 wide across (16 thick): at 26 pixels to the em
#   about 3 pixels apart and under half a pixel thick, so the sign under
#   them still reads; at 40 pixels about 5 apart. Lines 90 apart and 26
#   wide made a grey block at 26 pixels in the first proof.
# - Mirrored zones for birds only: the owner's corner insertions are a
#   bird's (rule O5); those of all 683 bases that are not symmetric would
#   cost 34 KB, the birds' cost 5 KB.
# - Four levels of mirrored variants: each further level costs about 50 KB
#   (818 glyphs and their anchors); levels 4 to 6 hold about 5 % of the
#   signs in groups.

MIRROR = 0x13440
DAMAGE = range(0x13447, 0x13456)
MODIFIERS = (MIRROR, *DAMAGE)
JOINERS_ZW = (0x200C, 0x200D)  # the ignorables that break a literal (rule M1)
QUADRANTS = (1, 2, 4, 8)  # top start, bottom start, top end, bottom end
SYMMETRY = 3
HATCH_TILE, HATCH_PERIOD, HATCH_STROKE, HATCH_OVERLAP = 45, 120, 22, 4
MIRROR_LEVELS = range(4)
MIRROR_BOX = 0.25  # the scale of the fallback box drawn over a sign it cannot mirror
HATCH = 0x110000  # pieces of shading are drawn glyphs with code points beyond Unicode
STRAY = 0xFFFC  # what a stray damage modifier is while sections 4 to 8 read the text
MIRRORED_BASES = BIRDS  # rule M5
SWAPPED = {TOP_START: TOP_END, TOP_END: TOP_START, BOTTOM_START: BOTTOM_END, BOTTOM_END: BOTTOM_START}


def passed_over(codepoint):
    """Rule M1: an ignorable that may stand inside a literal."""
    from glyphs import IGNORABLE  # glyphs.py imports this file: imported when needed
    return codepoint in IGNORABLE and codepoint not in JOINERS_ZW


def quadrants(codepoint):
    """The quarters a damage modifier names: a sum of QUADRANTS."""
    return codepoint - 0x13446


def literals(codepoints):
    """Rule M1: {index of a sign: (index of its mirror control or None,
    index of its damage modifier or None)} for every sign with a modifier."""
    found, count = {}, len(codepoints)

    def after(index):
        index += 1
        while index < count and passed_over(codepoints[index]):
            index += 1
        return index

    for index, codepoint in enumerate(codepoints):
        if codepoint not in HIEROGLYPHS:
            continue
        at, mirror, damage = after(index), None, None
        if at < count and codepoints[at] == MIRROR:
            mirror, at = at, after(at)
        if at < count and codepoints[at] in DAMAGE:
            damage = at
        if mirror is not None or damage is not None:
            found[index] = (mirror, damage)
    return found


_symmetric = {}


def symmetric(codepoint, font=None):
    """Rule M4: whether a sign looks the same mirrored. font: the source
    (a ufoLib2 Font), by default sources/Thoth-Regular.ufo."""
    if codepoint not in _symmetric:
        from fontTools.pens.recordingPen import DecomposingRecordingPen
        if font is None:
            import ufoLib2
            font = _symmetric.setdefault("font", ufoLib2.Font.open(SOURCE))
        glyph = next(g for g in font if codepoint in g.unicodes)
        pen = DecomposingRecordingPen(font)
        glyph.draw(pen)
        points = [args[-1] for _, args in pen.value if args]
        bounds = BoundsPen(font)
        glyph.draw(bounds)
        middle2 = bounds.bounds[0] + bounds.bounds[2] if bounds.bounds else 0
        flipped = [(middle2 - x, y) for x, y in points]

        def near(one, other):
            return all(min(abs(a - c) + abs(b - d) for c, d in other) <= SYMMETRY for a, b in one)
        _symmetric[codepoint] = near(flipped, points) and near(points, flipped)
    return _symmetric[codepoint]


def mirror_box(x, y):
    """Rule M8: the small box of the mirror control, centred on (x, y)."""
    return Glyph(MIRROR, x - _round(MIRROR_BOX * (CONTROL_BOX[0] + CONTROL_BOX[2]) / 2),
                 y - _round(MIRROR_BOX * (CONTROL_BOX[1] + CONTROL_BOX[3]) / 2), 0, MIRROR_BOX)


def mirrored_glyph(glyph, signs):
    """Rule M4: a drawn sign mirrored about the middle of its ink."""
    box = signs[glyph.codepoint].box
    return glyph._replace(x=glyph.x + _round(abs(glyph.scale) * (box[0] + box[2])), scale=-glyph.scale)


def strip_modifiers(codepoints, signs):
    """Rules M1 to M3 and M5: (text, origin, mods). text: codepoints with
    the modifiers of literals left out, a stray damage modifier replaced by
    STRAY and a corner control after a mirrored literal swapped; origin: for
    each character of text its index in codepoints; mods: {index in text of
    a modified sign: (mirrored, quarters, end)}, end one past its last
    modifier in codepoints. Mirrored is False for a symmetric sign."""
    found = literals(codepoints)
    taken = {i for pair in found.values() for i in pair if i is not None}
    text, origin, mods, turned = [], [], {}, None
    for index, codepoint in enumerate(codepoints):
        if index in taken:
            continue
        if turned is not None and codepoint in SWAPPED:  # rule M5
            codepoint = SWAPPED[codepoint] if turned in MIRRORED_BASES else MIRROR
        if not passed_over(codepoint):
            turned = None
        if index in found:
            mirror, damage = found[index]
            mirrored = mirror is not None and not symmetric(codepoint)
            mods[len(text)] = (mirrored, quadrants(codepoints[damage]) if damage is not None else 0,
                               max(i for i in found[index] if i is not None) + 1)
            turned = codepoint if mirrored else None
        text.append(STRAY if codepoint in DAMAGE else codepoint)
        origin.append(index)
    return text, origin, mods


def hatch_code(quadrant, across, up):
    """The code point of a piece of shading (rule M7)."""
    return HATCH + (quadrant << 12) + (across << 6) + up


def is_hatch(codepoint):
    return codepoint >= HATCH


def hatch_piece(code):
    """(quadrant, across, up) of a piece: the inverse of hatch_code()."""
    code -= HATCH
    return code >> 12, (code >> 6) & 63, code & 63


def hatch_rect(code):
    """Rule M7: the rectangle a piece shades, from the middle point."""
    quadrant, across, up = hatch_piece(code)
    top, end = quadrant in (1, 4), quadrant in (4, 8)
    x = (-HATCH_OVERLAP, across * HATCH_TILE) if end else (-across * HATCH_TILE, HATCH_OVERLAP)
    y = (-HATCH_OVERLAP, up * HATCH_TILE) if top else (-up * HATCH_TILE, HATCH_OVERLAP)
    return x[0], y[0], x[1], y[1]


def tiles(size):
    """Rule M7: half of a cell's side, in tiles."""
    return max(1, _round(size / 2 / HATCH_TILE))


def damage_size(sign, level):
    """Rule M6: (across, up) of a sign's quarters at a level, in tiles, and
    the height of its middle point over the bottom of its cell."""
    width, height = sign.cell[0] * half_unit(level), sign.cell[1] * unit(level)
    return tiles(width), tiles(height), height // 2


def damage_pieces(quarters, sign, level, x, y):
    """Rules M6 and M7: the pieces of shading of a cell whose bottom
    middle is at (x, y)."""
    across, up, middle = damage_size(sign, level)
    return [Glyph(hatch_code(q, across, up), x, y + middle, 0, 1.0) for q in QUADRANTS if quarters & q]


def lone_middle(sign):
    """Rule M6: the bottom middle of the cell around a lone sign's ink, as
    the source draws it lifted (also shrunk, which keeps both)."""
    return (sign.box[0] + sign.box[2]) // 2, sign.box[1] + sign.lift


def modified_layout(codepoints, signs, table=None):
    """Rules M1 to M8: layout() of text with modifiers."""
    text, origin, mods = strip_modifiers(codepoints, signs)
    implied = automatic_parts(text, table, signs) if table is not None else (text, range(len(text)))
    clusters = []
    for c in layout(text, signs, table, modifiers=False):
        run = [t for t, o in zip(*implied) if c.start <= o < c.end]
        inserted = c.stacked and is_insertion(run) and insertion(*run, signs) is not None
        members = [i for i in range(c.start, c.end) if is_sign(text[i])]
        glyphs = list(c.glyphs)
        if inserted and mods.get(members[0], (False,))[0]:  # rule M5: the inserted sign turns with its base
            base, sign = glyphs
            box, dx = signs[base.codepoint].box, sign_offset(signs[sign.codepoint], sign.level)[0]
            glyphs[1] = sign._replace(x=box[0] + box[2] - sign.x + 2 * dx)
        drawn = []
        for index, glyph in enumerate(glyphs):
            at = members[index] if c.stacked or is_sign(text[c.start]) else None
            mirrored, quarters, _ = mods.get(at, (False, 0, 0))
            sign = signs.get(glyph.codepoint)
            if glyph.codepoint == STRAY:  # rule M3, inside an enclosure (section 8)
                glyph = glyph._replace(codepoint=codepoints[origin[c.start]])
            if not (mirrored or quarters):
                drawn.append(glyph)
                continue
            variant = c.stacked and not (inserted and index == 0)
            if variant:  # its origin
                dx, dy = sign_offset(sign, glyph.level)
                x, y = glyph.x - dx, glyph.y - dy
            else:  # lone, or the base of an insertion
                x, y = lone_middle(sign)
                y += glyph.y - sign.lift - (shrink(sign.box, glyph.level)[2] if glyph.level else 0)  # rule M9
            pieces = damage_pieces(quarters, sign, glyph.level, x, y) if quarters else []
            if mirrored and variant and glyph.level not in MIRROR_LEVELS:  # rule M8
                drawn += [glyph, mirror_box(x, y + damage_size(sign, glyph.level)[2])] + pieces
            else:
                drawn += [mirrored_glyph(glyph, signs) if mirrored else glyph] + pieces
        end = mods[c.end - 1][2] if c.end - 1 in mods else origin[c.end - 1] + 1
        clusters.append(c._replace(start=origin[c.start], end=end, glyphs=tuple(drawn)))
    covered = {c.start for c in clusters}
    for index, codepoint in enumerate(text):  # rule M3: a stray damage modifier
        if codepoint == STRAY and origin[index] not in covered:
            original = codepoints[origin[index]]
            clusters.append(Cluster(origin[index], origin[index] + 1, CONTROL_ADVANCE,
                                    (Glyph(original, 0, 0, 0, 1.0),), False))
    return sorted(clusters, key=lambda c: c.start)


def implied_text(codepoints, table=None):
    """The text the stacking rules read, with the controls the automatic
    layer implies, and for each character its index in codepoints: what
    the font has in place of the text once its modifiers are folded."""
    signs = default_signs()
    text, origin, _ = strip_modifiers(codepoints, signs) if any(c in MODIFIERS for c in codepoints) \
        else (list(codepoints), list(range(len(codepoints))), {})
    implied, inner = automatic_parts(text, table, signs) if table is not None else (text, range(len(text)))
    return implied, [origin[i] for i in inner]
