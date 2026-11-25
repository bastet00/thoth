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

from collections import defaultdict

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

    @property
    def inserts(self):
        """The glyphs and data of corner insertion (Inserts)."""
        if not hasattr(self, "_inserts"):
            self._inserts = Inserts(self.signs)
        return self._inserts

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


# --- Corner insertion (layout section 6) -------------------------------------

CORNER_TAGS = {L.TOP_START: "ts", L.BOTTOM_START: "bs", L.TOP_END: "te", L.BOTTOM_END: "be"}


class Inserts:
    """Glyphs of corner insertion and what the features need to know.

    The rules of layout.py are tabulated here once, from layout.insertion():
    which birds shrink before which signs, the zone class (width, height) of
    every base for each corner and shape, the size class of every
    insertable sign at each level, and the anchors.

    Glyphs: a corner control between two signs becomes a candidate (a box,
    in case no rule takes it), then the candidate of its corner and the
    shape of the inserted sign; a shrunk bird is the bird's outline scaled
    as layout.shrink() says, with the bird's advance; the zone of the base
    is two markers after the candidate, its width and its height, which
    become one marker once the level is known; the candidate then becomes
    the mark of its corner, of the shape and of the width of the inserted
    sign, which hangs from the base where a sign of that width stands; a
    marker after the inserted sign makes the block one cluster.
    """

    zone_done, cluster_end = "_izx", "_iye"

    def __init__(self, signs):
        self.signs = signs
        self.insertable = sorted(c for c in signs if L.insertable(signs[c]))
        self.shape = {c: L.shape_of(signs[c]) for c in self.insertable}
        self.size = {(c, k): L.insert_size(signs[c], k) for c in self.insertable for k in L.INSERT_LEVELS}
        levels = (0, *L.SHRINK_LEVELS)
        # what layout.insertion() decides, for every base, corner and sign
        self.shrinks = defaultdict(set)  # (bird, control, base level): {inserted sign}
        self.zones = {}  # (base, base level, control, shape): Zone, where some sign is placed
        self.anchors = defaultdict(set)  # the same key: {width of the inserted sign, in units}
        for base in sorted(signs):
            for control in L.CORNERS:
                for c in self.insertable:
                    found = L.insertion(base, control, c, signs)
                    if found is None:
                        continue
                    level, inner = found
                    if level:
                        self.shrinks[(base, control, level)].add(c)
                    key = (base, level, control, self.shape[c])
                    self.zones[key] = signs[base].corners[control][levels.index(level)][self.shape[c]]
                    self.anchors[key].add(L.seat_width(self.size[(c, inner)]))
        self.shrunk_glyphs = sorted({(base, level) for base, level, _, _ in self.zones if level})
        self.widths = sorted({zone.width for zone in self.zones.values()})
        self.heights = sorted({zone.height for zone in self.zones.values()})
        self.shapes = sorted(L.SHAPES)
        # the widths of inserted signs: a mark for each, in every corner
        self.mark_sizes = sorted({(shape, w) for (_, _, _, shape), ws in self.anchors.items() for w in ws})

    # -- names --
    @staticmethod
    def candidate(control):
        return f"{control_name(control)}.ins"

    @staticmethod
    def shaped(control, shape):  # the candidate, before a sign of this shape
        return f"{control_name(control)}.ins.{shape}"

    @staticmethod
    def zone_width(width):  # the width of the zone, in STEPs
        return f"_izw.{width}"

    @staticmethod
    def zone_height(height):
        return f"_izh.{height}"

    @staticmethod
    def mark(control, shape, width):  # an inserted sign `width` units wide
        return f"_in.{CORNER_TAGS[control]}.{shape}.{width}"

    def shrunk(self, codepoint, level):
        return f"{self.signs[codepoint].name}.shrink{level}"

    def base(self, codepoint, level):
        """The glyph of a base drawn at a level: lone, or shrunk."""
        return self.shrunk(codepoint, level) if level else self.signs[codepoint].name

    # -- families --
    def bases(self):
        """Glyphs with an advance: the candidates and the shrunk birds."""
        return self.candidates() + [self.shrunk(c, k) for c, k in self.shrunk_glyphs]

    def candidates(self):
        return ([self.candidate(c) for c in L.CORNERS]
                + [self.shaped(c, s) for c in L.CORNERS for s in self.shapes])

    def corner_marks(self):
        return [self.mark(c, s, x) for c in L.CORNERS for s, x in self.mark_sizes]

    def markers(self):
        """Empty marks: the zone, the end of the block and the corner marks."""
        return ([self.zone_width(w) for w in self.widths] + [self.zone_height(h) for h in self.heights]
                + [self.zone_done, self.cluster_end] + self.corner_marks())


def add_insertion(font, names):
    """Add the glyphs of corner insertion. Returns those with an advance,
    for the glyph order."""
    inserts = names.inserts
    for name in inserts.candidates():
        glyph = Glyph(name, width=L.CONTROL_ADVANCE)
        glyph.components.append(Component(FALLBACK))
        font.addGlyph(glyph)
    for codepoint, level in inserts.shrunk_glyphs:
        sign = names.signs[codepoint]
        scale, x, y = L.shrink(sign.box, level)
        # the lone glyph was lifted: its outline is scaled with its lift
        offset = (x, L._round(y + sign.lift - scale * sign.lift))
        glyph = Glyph(inserts.shrunk(codepoint, level), width=sign.advance)
        glyph.components.append(Component(sign.name, (scale, 0, 0, scale, *offset)))
        font.addGlyph(glyph)
    for name in inserts.markers():
        font.addGlyph(Glyph(name, width=0))
    return inserts.bases()


# --- Automatic stacking (layout section 7) ------------------------------------

class Automatic:
    """Glyphs of the automatic layer and the table it compiles.

    All are empty marks: a word start and a word end (rule A2) put before
    and after the signs of a stretch where it begins or ends a word; a slot
    between every two signs of a stretch; an implied control, one per
    control the table and the shape rule (A8, the vertical joiner) use,
    which a slot becomes and which becomes the control itself once rule A5
    has been checked; an empty glyph that an implied control becomes where
    rule A5 keeps its block from forming; an inner slot, which a slot
    inside an entry becomes where the entry joins nothing (so the shape
    rule knows the signs are taken); and a kept slot, which a slot inside
    a run of half-block signs becomes where the run stays as it is (A8).
    """

    start, end, slot, null = "auto.start", "auto.end", "auto.slot", "auto.null"
    inner, kept = "auto.inner", "auto.kept"

    def __init__(self, table):
        self.table = table  # layout.automatic_table()
        self.controls = sorted({c for arrangement in table.values() for block in arrangement
                                for c in block if not L.is_sign(c)} | {L.VERTICAL_JOINER})

    @staticmethod
    def join(control):  # an implied control
        return f"auto.{control_name(control)}"

    def markers(self):
        return ([self.start, self.end, self.slot, self.null, self.inner, self.kept]
                + [self.join(c) for c in self.controls])


def add_automatic(font, automatic):
    for name in automatic.markers():
        font.addGlyph(Glyph(name, width=0))


# --- Enclosures (layout section 8) --------------------------------------------

class Enclosures:
    """Glyphs of enclosures and what the features need to know.

    Glyphs: a pending copy of each enclosure control (its box) and of each
    delimiter (its sign), which the features put in first so that no group
    or word reaches across them (rule E2) and put back where no enclosure
    forms (rule E3); the joined delimiters (rule E6); an empty base for a
    control without its delimiter (rule E7); the line pieces and merlon
    rows (rule E6); a spacer per cell, the base of a lone sign drawn as a
    group of one (rule E4); and the empty marks that carry the state of an
    enclosure while the features check it (features._gsub_enclosure_end).
    """

    start, end = "_enc.start", "_enc.end"  # a control without its delimiter
    inside = "_ein"  # after the base of every cluster that may be inside
    kinds = ("plain", "walled")

    def __init__(self, signs, rings):
        self.signs, self.rings = signs, rings
        self.cells = sorted({s.cell for s in signs.values()})
        self.edges = {kind: L.band_edges(kind, rings) for kind in self.kinds}
        self.merlon = L.merlon_size(rings)
        widest = L.advance(L.MAX_WIDTH, L.half_unit(0))  # the widest cluster there is
        self.counts = range(1, L.merlon_count(widest, rings) + 1)
        self.enclosable = L.enclosable(signs)
        # {base glyph of an insertion that rule E4 moves inside an enclosure:
        # (how far, code point, level)}
        self.moved = {}
        for (base, level), fits in sorted(self.enclosable.items()):
            move = L.lift_in_enclosure(signs[base])
            if fits and move:
                self.moved[signs[base].name + (f".shrink{level}" if level else "")] = (move, base, level)

    # -- names --
    @staticmethod
    def pending(codepoint):  # an enclosure control, until it is known to enclose
        return f"{control_name(codepoint)}.enc"

    def waiting(self, codepoint):  # a delimiter next to an enclosure control
        return f"{self.signs[codepoint].name}.{'open' if codepoint in L.OPENINGS else 'close'}"

    def joined(self, codepoint):
        return f"{self.signs[codepoint].name}.ring"

    @staticmethod
    def spacer(cell):
        return f"_E.{cell[0]}.{cell[1]}"

    @staticmethod
    def line(kind, length, side):  # side: "start" (x 0 to length) or "end" (x -length to 0)
        return f"_el.{kind[0]}.{length}.{side[0]}"

    @staticmethod
    def merlons(kind, count):
        return f"_em.{kind[0]}.{count}"

    @staticmethod
    def state(name, kind=None):
        """b: after a begin control; in: inside, of a kind; e: after an end
        control; ok: checked, the enclosure forms."""
        return f"_e{name}" + (f".{kind[0]}" if kind else "")

    def frame_name(self, part):
        """The glyph of a layout.Frame part."""
        if part[0] == "piece":
            return self.joined(part[1])
        if part[0] == "line":
            return self.line(*part[1:])
        return self.merlons(part[1], part[2])

    # -- families --
    def bases(self):
        """Glyphs with an advance, for the glyph order."""
        return ([self.pending(c) for c in L.ENCLOSURE] + [self.waiting(c) for c in (*L.OPENINGS, *L.CLOSINGS)]
                + [self.joined(c) for c in (*L.OPENINGS, *L.CLOSINGS)] + [self.spacer(c) for c in self.cells])

    def empty_bases(self):
        return [self.start, self.end]

    def states(self):
        return ([self.inside] + [self.state(n, k) for n in ("b", "in", "e", "eok", "ok", "bok") for k in self.kinds])

    def lines(self):
        return [self.line(k, m, s) for k in self.kinds for m in L.SEGMENTS for s in ("start", "end")]

    def merlon_rows(self):
        return [self.merlons("walled", n) for n in self.counts]

    def markers(self):
        """Empty marks."""
        return self.states()

    def marks(self):
        """Every mark: the empty ones and the drawn lines."""
        return self.states() + self.lines() + self.merlon_rows()


def _rectangle(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y0))  # counter-clockwise, as in the rest of the source
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()


def _bands(pen, edges, x0, x1):
    """The four thin lines of the two bands, from x0 to x1."""
    for low, high in zip(edges[::2], edges[1::2]):
        _rectangle(pen, x0, low, x1, high)


def _joined_outline(font, sign, ring, edges):
    """Rule E6: the delimiter scaled and moved as its Ring says, its band
    ends opened, and the bands of the lines carried on to its edge."""
    import pathops
    from fontTools.pens.transformPen import TransformPen

    source = pathops.Path()
    font[sign.name].draw(TransformPen(source.getPen(), (ring.scale, 0, 0, ring.scale, 0, ring.dy)))
    # the end of the hole of the upper band: where the ink closes it
    middle = (ring.bands[5] + ring.bands[6]) / 2
    pen = L._Crossings(middle)  # crossings of the line y = middle: the outline turned
    font[sign.name].draw(TransformPen(pen, (0, 1, 1, 0, 0, 0)))
    xs = sorted(pen.found)
    cut = (xs[-2] if ring.opening else xs[1]) * ring.scale
    far = ring.advance + 100
    cap = pathops.Path()
    low, high = ring.bands[0] * ring.scale + ring.dy, ring.bands[7] * ring.scale + ring.dy
    for a, b in ((low - 1, ring.bands[3] * ring.scale + ring.dy + 1),
                 (ring.bands[4] * ring.scale + ring.dy - 1, high + 1)):
        _rectangle(cap.getPen(), cut if ring.opening else -100, a, far if ring.opening else cut, b)
    opened = pathops.op(source, cap, pathops.PathOp.DIFFERENCE, fix_winding=True)
    carried = pathops.Path()
    _bands(carried.getPen(), edges, cut - 1 if ring.opening else 0, ring.advance if ring.opening else cut + 1)
    return pathops.op(opened, carried, pathops.PathOp.UNION, fix_winding=True)


def add_enclosures(font, enclosures):
    """Add the glyphs of enclosures (font: the source, signs not yet
    lifted). Returns those with an advance, for the glyph order."""
    from fontTools.pens.roundingPen import RoundingPen

    e, signs = enclosures, enclosures.signs
    for codepoint in L.ENCLOSURE:
        glyph = Glyph(e.pending(codepoint), width=L.CONTROL_ADVANCE)
        glyph.components.append(Component(FALLBACK))
        font.addGlyph(glyph)
    for codepoint in (*L.OPENINGS, *L.CLOSINGS):
        sign, ring = signs[codepoint], e.rings[codepoint]
        glyph = Glyph(e.waiting(codepoint), width=sign.advance)
        glyph.components.append(Component(sign.name))
        font.addGlyph(glyph)
        kind = "walled" if codepoint in (0x13286, 0x13287, 0x13288, 0x13289) else "plain"
        outline = _joined_outline(font, sign, ring, e.edges[kind])
        glyph = Glyph(e.joined(codepoint), width=ring.advance)
        outline.draw(RoundingPen(glyph.getPen()))
        font.addGlyph(glyph)
    for cell in e.cells:
        font.addGlyph(Glyph(e.spacer(cell), width=L.advance(cell[0], L.half_unit(0))))
    for name in e.empty_bases() + e.markers():
        font.addGlyph(Glyph(name, width=0))
    for kind in e.kinds:
        for length in L.SEGMENTS:
            for side in ("start", "end"):
                glyph = Glyph(e.line(kind, length, side), width=0)
                _bands(glyph.getPen(), e.edges[kind], 0 if side == "start" else -length,
                       length if side == "start" else 0)
                font.addGlyph(glyph)
    merlon, gap, height = e.merlon
    edges = e.edges["walled"]
    stroke = edges[7] - edges[6]
    for count in e.counts:
        glyph = Glyph(e.merlons("walled", count), width=0)
        pen = glyph.getPen()
        left = -(count * (merlon + gap) - gap) // 2
        for i in range(count):
            x0 = left + i * (merlon + gap)
            x1 = x0 + merlon
            for base, up in ((edges[7], 1), (edges[0], -1)):  # on the top band, under the bottom one
                tip = base + up * height
                outer = [(x0, base), (x1, base), (x1, tip), (x0, tip)]
                inner = [(x0 + stroke, base), (x1 - stroke, base), (x1 - stroke, tip - up * stroke),
                         (x0 + stroke, tip - up * stroke)]
                # a U standing on the band: the outer box less the inner one
                points = [outer[0], inner[0], inner[3], inner[2], inner[1], outer[1], outer[2], outer[3]]
                if up < 0:
                    points.reverse()
                pen.moveTo(points[0])
                for point in points[1:]:
                    pen.lineTo(point)
                pen.closePath()
        font.addGlyph(glyph)
    return e.bases()
