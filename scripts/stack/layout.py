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
 2. A sign's cell is its ink plus GAP, rounded up to whole units. A sign
    larger than the quadrat is first reduced, on its own, to fit it.
 3. A row (signs joined horizontally) is as wide as its cells together and
    as high as its highest cell. A group (rows joined vertically) is as
    wide as its widest row and as high as its rows together.
 4. The whole group is drawn at one level: the largest of eight at which it
    is at most WIDTH_LIMIT by HEIGHT_LIMIT units of full size. Most groups
    fit at level 0, so their signs are as large as the lone signs next to
    them.
 5. At every level the ink of a sign leaves GAP in its cell, so neighbours
    never come closer than GAP. Where the scale of the level alone would
    leave less, the sign is reduced a little more, on its own, by a quarter
    at most (Sign.scales).
 6. Across: the cells of a row touch, each sign is centred in the width of
    its cell, and a row narrower than its group is centred in it. But a row
    of exactly two signs whose cells leave at most MAX_JUSTIFY units of the
    group's width free is justified: the first cell flush with the left
    edge of the group, the second with its right edge.
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
    group is wider than MAX_WIDTH or higher than MAX_HEIGHT units, is drawn
    unstacked: every sign as a lone sign, every control as its fallback box.

Rounding. The font can only add whole numbers that its glyphs carry, so
every position here is such a sum, rounded as the font rounds it: a unit is
a whole number of font units at each level (unit()); each glyph's share of
a position is rounded on its own, from what that one glyph knows: a cell's
width (whole units), half of its row and half of the group (rounded down),
the margins of rule 7 (rounded down, from the group's height and level),
a sign's offset in its cell (to the nearest, baked into its variant); then
the shares are added. The font and this file therefore agree exactly. Only the outline of a scaled component may differ
from ink_box(), by its own rounding: at most 2.
"""

import math
from collections import namedtuple

from fontTools.pens.boundsPen import BoundsPen

# --- 1. Constants -----------------------------------------------------------
# Lengths are in font units (1000 to the em) unless they are called units.

UNIT = 90  # the grid: cells are whole units wide and high
GAP = 34  # least distance between the ink of two neighbours, at every level
HEIGHT_LIMIT = 12  # units the quadrat is high
WIDTH_LIMIT = 14  # units the quadrat is wide
LEVEL_HEIGHTS = (12, 14, 16, 18, 20, 24, 36, 48)  # one scale level for each:
# the height in units that the level brings down to HEIGHT_LIMIT
MAX_WIDTH, MAX_HEIGHT = 32, 40  # units: a larger group is not stacked
MAX_JUSTIFY = 6  # units: the most a justified row of two may leave free
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
# - Fourteen units of width, against twelve of height, let the two commonest
#   wide signs (mouth 1079, water 1099) keep their size in a group. In a
#   square quadrat they would be smaller than the lone signs next to them.
# - A gap of 34 is about one pixel at the smallest size the signs are read
#   at (26 pixels to the em); with less, neighbours run together there. It
#   is the same at every level because the pixel is. With a unit of 90 it
#   is also the largest gap that leaves the stroke (416 high) in five units.
# - Eight levels from 1.0 to 0.244: halves, thirds and quarters for two,
#   three and four full rows, and 14, 16, 18 and 20 units because that is
#   where real groups are. The price: the level of a group inside a group
#   (a later milestone) comes from a table of products rounded down to a
#   level, not from a sum.
# - The caps are the largest group of the owner's dictionary (9,330 groups
#   in 10,224 words), 29 units wide and 36 high, plus three and four units.
#   The font needs no state for sizes beyond them.
# - Six units free let the bread and the stool of "offering" reach the ends
#   of the table above them, and keep two strokes under a water sign (nine
#   units free) together.
# - Low is half the quadrat: bread, mouth, water and stool are centred when
#   alone; figures, birds, staffs and lying animals stand on the baseline.


def unit(level):
    """The unit at a level, in font units: 90, 77, 67, 60, 54, 45, 30, 22."""
    return HEIGHT_LIMIT * UNIT // LEVEL_HEIGHTS[level]


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
# (xMin, yMin, xMax, yMax); cell: (width, height) in units, the size class;
# scales: the scale of the sign in a group, one for each level; lift: how
# far the lone sign is moved up (rule 1). The font bakes scales into the
# variants of the sign and lift into its lone glyph.
Sign = namedtuple("Sign", "name advance box cell scales lift")


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
                                sign_lift(box, cell))
    return table


def _fit(box):
    """Rule 2: 1, or the scale that brings a large sign inside the quadrat."""
    sizes = (box[2] - box[0], box[3] - box[1])
    limits = (WIDTH_LIMIT, HEIGHT_LIMIT)
    return min(1, *((limit * UNIT - GAP) / size for size, limit in zip(sizes, limits)))


def sign_cell(box):
    """Rule 2: the cell of a sign, (width, height) in units."""
    fit = _fit(box)
    return tuple(math.ceil(round(size * fit + GAP, 6) / UNIT)
                 for size in (box[2] - box[0], box[3] - box[1]))


def sign_scale(box, cell, level):
    """Rules 2 and 5: the scale of a sign in a group at a level."""
    sizes = (box[2] - box[0], box[3] - box[1])
    scale = _fit(box) * unit(level) / UNIT
    clear = min((cells * unit(level) - GAP) / size for size, cells in zip(sizes, cell))
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
Cluster = namedtuple("Cluster", "start end advance glyphs stacked")


def measure(group, signs):
    """Rule 3: (width, height) of a group in units, and of each row."""
    rows = []
    for row in group:
        cells = [signs[member].cell for member in row]
        rows.append((sum(cell[0] for cell in cells), max(cell[1] for cell in cells)))
    return max(row[0] for row in rows), sum(row[1] for row in rows), rows


def fit_level(width, height):
    """Rules 4 and 9: the level of a group of this size in units, or None."""
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        return None
    return next(
        level for level in range(len(LEVEL_HEIGHTS))
        if width * unit(level) <= WIDTH_LIMIT * UNIT
        and height * unit(level) <= HEIGHT_LIMIT * UNIT
    )


def layout(codepoints, signs):
    """Lay out text: [Cluster] for its signs and controls, in text order.

    Characters that are neither (letters, spaces) get no cluster: the font
    shapes them as usual.
    """
    clusters = []
    for start, end in runs(codepoints):
        run = codepoints[start:end]
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


def _stacked(start, end, group, level, signs):
    """Rules 6 to 8: place the signs of a group that fits at this level.

    The cells of the group start half a gap left of its ink and on the
    baseline; the quadrat is HEIGHT_LIMIT units of full size above it.
    """
    width, height, rows = measure(group, signs)
    step = unit(level)
    edge = SIDE_BEARING - GAP // 2
    glyphs = []
    for row, (row_width, _), line in zip(group, rows, _lines(rows, height, step)):
        cells = [signs[member].cell[0] for member in row]
        if len(row) == 2 and 0 < width - row_width <= MAX_JUSTIFY:
            lefts = [0, width * step - cells[1] * step]
        else:
            lefts = [width * step // 2 - row_width * step // 2 + sum(cells[:i]) * step
                     for i in range(len(row))]
        for member, left, cell in zip(row, lefts, cells):
            sign = signs[member]
            scale = sign.scales[level]
            x_min, y_min, x_max, _ = sign.box
            glyphs.append(Glyph(
                member,
                edge + left + cell * step // 2 - _round(scale * (x_min + x_max) / 2),
                line - _round(scale * y_min),
                level,
                scale,
            ))
    advance = width * step - GAP + 2 * SIDE_BEARING
    return Cluster(start, end, advance, tuple(glyphs), True)


def _lines(rows, height, step):
    """Rule 7: the line each row stands on, from the baseline."""
    top = HEIGHT_LIMIT * UNIT
    spare = top - height * step
    if len(rows) == 1:
        return [spare // 2 if rows[0][1] <= LOW_HEIGHT else 0]
    if len(rows) == 2:
        margin = min((spare + GAP) // 4, spare // 2)
        return [top - margin - rows[0][1] * step, margin]
    lines, line = [], top - spare // 2
    for _, row_height in rows:
        line -= row_height * step
        lines.append(line)
    return lines


def _round(value):
    return math.floor(value + 0.5)


def ink_box(glyph, signs):
    """The ink box of a drawn glyph, relative to the start of its cluster."""
    box = signs[glyph.codepoint].box if glyph.codepoint in signs else CONTROL_BOX
    return (
        glyph.x + glyph.scale * box[0], glyph.y + glyph.scale * box[1],
        glyph.x + glyph.scale * box[2], glyph.y + glyph.scale * box[3],
    )
