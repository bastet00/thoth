"""Glyphs the generator adds to the source font, and their names.

Three kinds:
- lone signs: the source glyphs, low ones moved up (layout rule 1);
- sign variants: one per sign and level, the source outline as a single
  scaled component placed in its cell (layout rules 2, 5 and 6), drawn at
  the centre of the bottom of the cell, advance 0;
- markers: empty glyphs that carry the state of a group while the
  features (features.py) compute it. Only a group head has an advance.

Names says which glyphs exist; features.py uses the same names.
"""

from ufoLib2.objects import Component, Glyph

import layout as L

# Egyptian hieroglyph format controls (U+13430-U+13440). The source has no
# glyphs for them. Each gets its own glyph, so that features can tell them
# apart, and all of them show one shared outline when no rule replaces them.
CONTROLS = range(0x13430, 0x13441)
FALLBACK = "control.fallback"

SIDE_BEARING = 49  # the side bearing of the signs
BOX, BOTTOM, STROKE = 600, 200, 50  # a square centred on the quadrat (y = 500)
CORNER, DASH, GAP = 100, 125, 50  # one side: corner, gap, dash, gap, dash, gap, corner

# Unicode's Default_Ignorable_Code_Point (DerivedCoreProperties.txt, 16.0)
IGNORABLE = {0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5, *range(0x180B, 0x1810),
             *range(0x200B, 0x2010), *range(0x202A, 0x202F), *range(0x2060, 0x2070), 0x3164,
             *range(0xFE00, 0xFE10), 0xFEFF, 0xFFA0, *range(0xFFF0, 0xFFF9),
             *range(0x1BCA0, 0x1BCA4), *range(0x1D173, 0x1D17B), *range(0xE0000, 0xE1000)}

LEVELS = range(len(L.LEVEL_HEIGHTS))
OVER = "x"  # a sum beyond the caps (layout rule 9)


def control_name(codepoint):
    return f"u{codepoint:05X}"


class Names:
    """Every glyph the stacking features use, by role.

    The states of a sum or maximum run from 1 to its cap, and OVER beyond
    it. Glyphs that depend on the level come once per level (leveled()).
    """

    def __init__(self, signs, font):
        self.signs = signs  # {code point: layout.Sign}
        # default ignorables as HarfBuzz has them while it shapes: their glyph,
        # or .notdef where the font has none
        self.ignorables = [".notdef"] + sorted(
            glyph.name for glyph in font if any(u in IGNORABLE for u in glyph.unicodes))
        cmap = {u: glyph.name for glyph in font for u in glyph.unicodes}
        self.dotted_circle, self.zwnj = cmap[0x25CC], cmap[0x200C]
        self.max_cell = (max(s.cell[0] for s in signs.values()),
                         max(s.cell[1] for s in signs.values()))
        self.widths = range(1, L.MAX_WIDTH + 1)  # widths of rows and groups
        self.heights = range(1, L.MAX_HEIGHT + 1)  # heights of groups
        self.cell_widths = range(1, self.max_cell[0] + 1)
        self.cell_heights = range(1, self.max_cell[1] + 1)
        self.slacks = range(1, L.MAX_JUSTIFY + 1)
        # (width, height, level) of every size a group can have, at its level
        self.sizes = [(w, h, L.fit_level(w, h)) for w in self.widths for h in self.heights]
        # the group head is two glyphs: Q carries the width and the level
        # (advance, axis), V where the rows hang (top and bottom, rule 7)
        self.head_sizes = sorted({(w, k) for w, h, k in self.sizes})
        self.vertical = sorted({L.span(n, h, L.unit(k)) for h, n in self.vertical_sizes()
                                for k in self.levels(h)})

    # -- inputs --
    def lone(self, codepoint):
        return self.signs[codepoint].name

    joined = {0x13430: "u13430.join", 0x13431: "u13431.join"}  # a joiner inside a group, while checked

    # -- sign variants --
    def variant(self, codepoint, level):
        return f"_{level}.{self.signs[codepoint].name}"

    # -- markers while a group is computed --
    head0, vertical0, row0, width0, carrier0 = "Q0", "_V0", "_Rh0", "_Rw0", "_wc0"
    vj, hj = "_vj", "_hj"  # joiners inside a group
    fallback_head, fallback = "Qx", "_x"  # a group over the caps
    cell_end, cell_start = "_ce", "_cs"  # the ends of a cell, to make a group one cluster
    hidden = "nothing"  # an empty base

    @staticmethod
    def cell_width(a):
        return f"_cw.{a}"

    @staticmethod
    def cell_height(b):
        return f"_ch.{b}"

    @staticmethod
    def width_sum(a, s):  # a cell a half units wide, s the width from it to the end of its row
        return f"_cf.{a}.{s}"

    @staticmethod
    def height_max(m):  # the highest cell from this one to the end of its row
        return f"_chf.{m}"

    @staticmethod
    def row_height(m):
        return f"_rhm.{m}"

    @staticmethod
    def height_sum(m, t):  # a row m units high, t the height from it to the end of the group
        return f"_rhf.{m}.{t}"

    @staticmethod
    def row_width(s):
        return f"_rws.{s}"

    @staticmethod
    def pair_width(s):  # a row of exactly two members
        return f"_rw2.{s}"

    @staticmethod
    def carrier(g):  # the widest row from this one to the end, then the group's width
        return f"_wc.{g}"

    @staticmethod
    def justify(d):
        return f"_j.{d}"

    @staticmethod
    def head_width(w):
        return f"QW.{w}"

    @staticmethod
    def vertical_size(h, n):  # n: 1, 2, or 3 for three rows or more
        return f"_VH.{h}.{n}"

    vertical_over = "_VX"

    # -- what the group is drawn with --
    @staticmethod
    def head(width, level):  # width in half units
        return f"Q.{width}.{level}"

    @staticmethod
    def vertical_final(top, bottom):
        return f"_V.{top}.{bottom}"

    # Leveled glyphs are named "_<level>.<role>", so that sorted by name
    # (the build appends unlisted glyphs that way) each level is one block
    # in the same order: then a change of level is one delta in GSUB.
    @staticmethod
    def row(m, level):
        return f"_{level}.Rh.{m}"

    @staticmethod
    def last_row(level):
        return f"_{level}.RhL"

    @staticmethod
    def row_left(s, level):
        return f"_{level}.Rw.{s}"

    @staticmethod
    def spacer(d, level):
        return f"_{level}.sp.{d}"

    # -- the vertical state of a group --
    @staticmethod
    def row_counts(height):
        return [n for n in (1, 2, 3) if n <= height and (n > 1 or height <= L.HEIGHT_LIMIT)]

    def levels(self, height):
        """The levels a group of this height can have."""
        return sorted({L.fit_level(w, height) for w in self.widths})

    # -- families, in glyph order --
    def width_sums(self):
        return [(a, s) for a in self.cell_widths for s in [*range(a, L.MAX_WIDTH + 1), OVER]]

    def height_sums(self):
        return [(m, t) for m in self.cell_heights for t in [*range(m, L.MAX_HEIGHT + 1), OVER]]

    def vertical_sizes(self):
        return [(h, n) for h in self.heights for n in self.row_counts(h)]

    def leveled(self, level):
        """Glyphs that come once per level, in the same order at each level."""
        return sorted([self.variant(c, level) for c in self.signs]
                      + [self.row(m, level) for m in self.cell_heights] + [self.last_row(level)]
                      + [self.row_left(s, level) for s in self.widths]
                      + [self.spacer(d, level) for d in self.slacks])

    def heads(self):
        """Bases: they stop a group and the first carries its advance."""
        return ([self.head0, self.fallback_head, self.hidden] + [self.head_width(w) for w in self.widths]
                + [self.head(w, k) for w, k in self.head_sizes])

    def markers(self):
        """Empty marks: the state of a group while it is computed, and V."""
        return ([self.vertical0, self.row0, self.width0, self.carrier0, self.vj, self.hj,
                 self.fallback, self.vertical_over, self.cell_end, self.cell_start]
                + [self.cell_width(a) for a in self.cell_widths]
                + [self.cell_height(b) for b in self.cell_heights]
                + [self.width_sum(a, s) for a, s in self.width_sums()]
                + [self.height_max(m) for m in self.cell_heights]
                + [self.row_height(m) for m in self.cell_heights]
                + [self.height_sum(m, t) for m, t in self.height_sums()]
                + [self.row_width(s) for s in [*self.widths, OVER]]
                + [self.pair_width(s) for s in self.widths[1:]]
                + [self.carrier(g) for g in [*self.widths, OVER]]
                + [self.justify(d) for d in self.slacks]
                + [self.vertical_size(h, n) for h, n in self.vertical_sizes()]
                + [self.vertical_final(*key) for key in self.vertical])


def _dashed_box(pen):
    def polygon(points):  # counter-clockwise, as in the rest of the source
        pen.moveTo(points[0])
        for point in points[1:]:
            pen.lineTo(point)
        pen.closePath()

    s, t, c = BOX, STROKE, CORNER
    shapes = [  # the four corners, each an L
        [(0, 0), (c, 0), (c, t), (t, t), (t, c), (0, c)],
        [(s, 0), (s, c), (s - t, c), (s - t, t), (s - c, t), (s - c, 0)],
        [(s, s), (s - c, s), (s - c, s - t), (s - t, s - t), (s - t, s - c), (s, s - c)],
        [(0, s), (0, s - c), (t, s - c), (t, s - t), (c, s - t), (c, s)],
    ]
    for start in range(CORNER + GAP, BOX - CORNER, DASH + GAP):
        end = start + DASH
        for low in (0, s - t):  # bottom and top sides, then left and right
            shapes.append([(start, low), (end, low), (end, low + t), (start, low + t)])
            shapes.append([(low, start), (low + t, start), (low + t, end), (low, end)])
    for shape in shapes:
        polygon([(x + SIDE_BEARING, y + BOTTOM) for x, y in shape])


def add_controls(font):
    """Add the fallback outline, one glyph per control, and the two joiners
    as they are while a group is checked (the same box)."""
    advance = BOX + 2 * SIDE_BEARING
    fallback = Glyph(FALLBACK, width=advance)
    _dashed_box(fallback.getPen())
    font.addGlyph(fallback)
    names = [control_name(codepoint) for codepoint in CONTROLS]
    for name, codepoint in zip(names, CONTROLS):
        glyph = Glyph(name, width=advance, unicodes=[codepoint])
        glyph.components.append(Component(FALLBACK))
        font.addGlyph(glyph)
    for name in Names.joined.values():
        glyph = Glyph(name, width=advance)
        glyph.components.append(Component(FALLBACK))
        font.addGlyph(glyph)
    return [FALLBACK, *names, *Names.joined.values()]


def lift_signs(font, signs):
    """Rule 1: move each low lone sign up by its lift. Returns their names."""
    moved = []
    for codepoint in sorted(signs):
        sign = signs[codepoint]
        if sign.lift:
            font[sign.name].move((0, sign.lift))
            moved.append(sign.name)
    return moved


def add_stacking(font, names):
    """Add the sign variants and the markers. Returns the heads, the only
    ones with an advance, for the glyph order. The rest are left out of it,
    so that they come last, sorted by name, and hmtx stores no advance for
    them."""
    for name in names.heads():
        font.addGlyph(Glyph(name, width=0))
    for width, level in names.head_sizes:
        font[names.head(width, level)].width = L.advance(width, L.half_unit(level))
    for name in names.markers():
        font.addGlyph(Glyph(name, width=0))
    for level in LEVELS:
        for name in names.leveled(level):
            font.addGlyph(Glyph(name, width=0))
        for codepoint in sorted(names.signs):
            sign = names.signs[codepoint]
            if not len(font[sign.name]):  # a blank: nothing to draw
                continue
            scale = sign.scales[level]
            dx, dy = L.sign_offset(sign, level)
            # the lone glyph was lifted; the variant takes that back
            offset = (dx, L._round(dy - scale * sign.lift))
            font[names.variant(codepoint, level)].components.append(
                Component(sign.name, (scale, 0, 0, scale, *offset)))
    return names.heads()
