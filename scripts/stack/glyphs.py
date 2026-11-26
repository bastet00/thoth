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

    @property
    def modifiers(self):
        """The glyphs and data of the sign modifiers (Modifiers)."""
        if not hasattr(self, "_modifiers"):
            self._modifiers = Modifiers(self)
        return self._modifiers

    @property
    def nesting(self):
        """The glyphs of segments and overlay (Nesting)."""
        if not hasattr(self, "_nesting"):
            self._nesting = Nesting(self.signs)
        return self._nesting

    @property
    def sides(self):
        """The glyphs of insertion at middle, top and bottom (SideInserts)."""
        if not hasattr(self, "_sides"):
            self._sides = SideInserts(self.signs)
        return self._sides

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


# --- Segments and overlay (layout section 8) ---------------------------------

SEG_TYPES = ("V", "H", "B", "E", "O", "Bf", "Hf", "Ef", "Bg", "Vg", "Eg")
TYPE_CONTROL = {"V": 0x13430, "H": 0x13431, "B": 0x13437, "E": 0x13438, "O": 0x13436,
                "Bf": 0x13437, "Hf": 0x13431, "Ef": 0x13438, "Bg": 0x13437, "Vg": 0x13430, "Eg": 0x13438}
DEAD = "dead"


def nest_step(state, token):
    """The automaton that checks the syntax of layout.parse_nested() on the
    tokens of a run, left to right: the state after `token` ("S" a sign, a
    type of SEG_TYPES, or "X" any other control), or DEAD.

    A state is (frames, position): one frame per open segment, (seen a
    vertical joiner at its level, opened as the first member of its row);
    position: m0 a member is expected at the start of a row, m1 after a
    horizontal joiner; aS after a sign, aB after a box, aN after a segment
    that was the first member of its row (a horizontal joiner must follow);
    f1/f2/fh/fe in the left operand of an overlay (after "(", after a sign,
    after a sign and "*", after "*", after ")"); o after the overlay
    control; gs/g1/g2 in the right operand."""
    if state == DEAD:
        return DEAD
    frames, pos = state
    depth = len(frames)
    if token == "S":
        found = {"m0": "aS", "m1": "aS", "f1": "f2", "fh": "f3", "o": "aB", "gs": "g1", "gv": "g2"}.get(pos)
        return (frames, found) if found else DEAD
    if token == "V" and pos in ("aS", "aB"):
        if frames:
            frames = frames[:-1] + ((True, frames[-1][1]),)
        return (frames, "m0")
    if token == "H" and pos in ("aS", "aB", "aN"):
        return (frames, "m1")
    if token == "B" and pos in ("m0", "m1") and depth + 1 <= L.MAX_DEPTH:
        return (frames + ((False, pos == "m0"),), "m0")
    if token == "E" and pos in ("aS", "aB") and frames and frames[-1][0]:
        return (frames[:-1], "aN" if frames[-1][1] else "aB")
    if token == "O" and pos in ("aS", "fe") and depth + 1 <= L.MAX_DEPTH:
        return (frames, "o")
    if token == "Bf" and pos in ("m0", "m1") and depth + 1 <= L.MAX_DEPTH:
        return (frames, "f1")
    if token == "Hf" and pos in ("f2", "f3"):
        return (frames, "fh")
    if token == "Ef" and pos == "f3":
        return (frames, "fe")
    if token == "Bg" and pos == "o":
        return (frames, "gs")
    if token == "Vg" and pos in ("g1", "g2"):
        return (frames, "gv")
    if token == "Eg" and pos == "g2":
        return (frames, "aB")
    return DEAD


NEST_START = ((), "m0")


def nest_accepts(state):
    return state != DEAD and not state[0] and state[1] in ("aS", "aB")


def nest_role(token, state):
    """The structural token a checked control is, from its type and the
    state after it: (type, depth). Segment brackets: the depth of the
    segment; joiners: the depth of their row; overlay controls: the depth
    of the overlay's box."""
    frames = len(state[0])
    if token == "B":
        return ("B", frames)
    if token == "E":
        return ("E", frames + 1)
    if token in ("V", "H"):
        return (token, frames)
    return (token, frames + 1)


class Nesting:
    """Glyphs of segments and overlay and what the features need to know.

    All are empty marks, but the run start (a base, so that a run's marks
    end at the next run). The text is checked by an automaton (nest_step):
    a control of a run with a segment or overlay control becomes pending,
    then the pending control of its type and of the automaton's state after
    it; a run the automaton refuses becomes its controls and lone signs
    again. A checked run's controls become structural tokens, by role and
    depth (they stay in the run, empty, to the end). Each box is then
    computed from the inside out (stage 2, stage 1) with placeholders and
    markers like those of a flat group, and becomes one cell of the row it
    stands in; stage 0 measures the rows of the group itself. The group
    then goes through the flat stages like any group (features.py)."""

    def __init__(self, signs, max_depth=L.MAX_DEPTH):
        self.signs = signs
        self.depths = range(1, max_depth + 1)
        self.max_cell = (28, 12)  # layout.BOX_LIMIT
        # the automaton: every state reachable from the start
        states, todo = {NEST_START}, [NEST_START]
        while todo:
            state = todo.pop()
            for token in ("S", *SEG_TYPES):
                found = nest_step(state, token)
                if found != DEAD and found not in states:
                    states.add(found)
                    todo.append(found)
        self.states = sorted(states, key=repr)
        self.index = {state: i for i, state in enumerate(self.states)}
        # the checked controls: (type, state) reachable after that type
        self.checked = sorted({(t, self.index[nest_step(s, t)]) for s in self.states for t in SEG_TYPES
                               if nest_step(s, t) != DEAD}, key=lambda x: (SEG_TYPES.index(x[0]), x[1]))

    # -- the check --
    @staticmethod
    def pending(codepoint):
        return f"_np.{codepoint:X}"

    @staticmethod
    def flat(token):  # a pending control in an overlay's operand
        return f"_np.{token}"

    @staticmethod
    def tagged(token, state):
        return f"_nd.{token}.{state}"

    @staticmethod
    def dead(codepoint):
        return f"_nx.{codepoint:X}"

    run_start, bad_start, poisoned = "_nrs", "_nrsx", "_npz"

    # -- structural tokens --
    @staticmethod
    def token(kind, depth):
        return f"_nt.{kind}{depth}"

    def tokens(self, depth=None):
        found = []
        for d in range(0, max(self.depths) + 1):
            if depth is not None and d != depth:
                continue
            found += [self.token(k, d) for k in ("V", "H")]
            if d:
                found += [self.token(k, d) for k in ("B", "E", *SEG_TYPES[4:])]
        return found

    # -- markers of a stage --
    @staticmethod
    def cell_width(a):
        return f"_nw.{a:02}"

    @staticmethod
    def cell_height(b):
        return f"_nh.{b:02}"

    @staticmethod
    def width_sum(a, s):
        return f"_nws.{s:02}.{a:02}" if s != OVER else f"_nws.x.{a:02}"

    @staticmethod
    def height_max(m):
        return f"_nhm.{m:02}"

    row_height0, row_width0, row_widtho, row_carrier0 = "_nrh0", "_nrw0", "_nro0", "_nrc0"
    box_width0, box_height0, box_end0 = "_nbw0", "_nbh0", "_nbe0"
    layer_seg0, layer_one0, layer_two0 = "_nls0", "_nlo0", "_nlq0"

    @staticmethod
    def row_m(m):
        return f"_nrm.{m:02}"

    @staticmethod
    def row_sum(m, t):
        return f"_nrs.{t:02}.{m:02}" if t != OVER else f"_nrs.x.{m:02}"

    @staticmethod
    def row_width(s):
        return f"_nrw.{s:02}" if s != OVER else "_nrw.x"

    @staticmethod
    def row_pair(s):
        return f"_nrp.{s:02}"

    @staticmethod
    def carrier(g):
        return f"_nrc.{g:02}" if g != OVER else "_nrc.x"

    @staticmethod
    def justify(d):
        return f"_nj.{d:02}"

    @staticmethod
    def box_width(w):
        return f"_nbw.{w:02}" if w != OVER else "_nbw.x"

    @staticmethod
    def box_height(h):
        return f"_nbh.{h:02}" if h != OVER else "_nbh.x"

    @staticmethod
    def layer_seg(h, c):  # a segment's layer while its height is known
        return f"_nls.{h:02}.{c}" if h != OVER else "_nls.x.0"

    @staticmethod
    def layer_one(h):
        return f"_nlo.{h:02}" if h != OVER else "_nlo.x"

    @staticmethod
    def layer_two(h):
        return f"_nlq.{h:02}" if h != OVER else "_nlq.x"

    # -- what stays, by depth --
    @staticmethod
    def seg_layer(d, h, c):  # waiting for the slot (the height of its row)
        return f"_nls{d}.{h:02}.{c}"

    # A layer, once its size and slot (or box) are known, is two placeholders
    # waiting for the level: where its first row hangs (top) and where its
    # last row stands (bottom), each keyed by what its height depends on.
    @staticmethod
    def seg_top(d, h, c, r):  # a segment of c rows, h units high, in a slot r high
        return f"_nlt{d}.{r:02}.{h:02}.{c}"

    @staticmethod
    def seg_bottom(d, c, spare):  # spare: the slot's free units
        return f"_nlb{d}.{c}.{spare:02}"

    @staticmethod
    def ovl_top(d, layer, h, spare):  # an operand h units high, the box's free units
        return f"_nlu{d}.{layer}.{h:02}.{spare:02}"

    @staticmethod
    def ovl_bottom(d, layer, spare):
        return f"_nlw{d}.{layer}.{spare:02}"

    @staticmethod
    def xv(d, w, level=None):  # the cell of a box in its row
        return f"_nX{d}.{w:02}" + ("" if level is None else f".{level}")

    @staticmethod
    def box_end(d):
        return f"_nE{d}"

    @staticmethod
    def cluster_start(d):
        return f"_ncs{d}"

    @staticmethod
    def cluster_end(d):
        return f"_nce{d}"

    @staticmethod
    def row(d, m, level=None):
        return f"_nR{d}.{m:02}" + ("" if level is None else f".{level}")

    @staticmethod
    def last_row(d):
        return f"_nL{d}"

    @staticmethod
    def top(d, layer, y):  # layer 1: a segment or an overlay's first operand
        return f"_nVt{d}.{layer}.{y:04}"

    @staticmethod
    def bottom(d, layer, y):
        return f"_nVb{d}.{layer}.{y:04}"

    # -- families --
    def widths(self):
        return range(1, self.max_cell[0] + 1)

    def cell_widths(self):
        """The widths a cell of a box can have: those of the signs, and at
        depth 2 those of a box inside a box."""
        if max(self.depths) > 1:
            return list(self.widths())
        return sorted({sign.cell[0] for sign in self.signs.values()})

    def pair_widths(self):  # a row of two cells is at least two half units wide
        return range(2, self.max_cell[0] + 1)

    def row_heights(self):  # a row above another in a box leaves it at least a unit
        return range(1, self.max_cell[1])

    def heights(self):
        return range(1, self.max_cell[1] + 1)

    def slots(self):
        """(depth, height, rows, slot) of every segment layer that can stand
        in a row: two rows or more (rows 2 or 3 for three and more)."""
        return [(d, h, c, r) for d in self.depths for h in range(2, self.max_cell[1] + 1)
                for c in (2, 3) if c <= h for r in range(h, self.max_cell[1] + 1)]

    def overlays(self):
        """(depth, layer, height, box height) of every operand of an overlay."""
        return [(d, layer, h, b) for d in self.depths for layer in (1, 2)
                for h in self.heights() for b in range(h, self.max_cell[1] + 1)]

    def verticals(self):
        """{(placeholder of a layer's top or bottom, level): final glyph}."""
        found = {}
        for d, h, c, r in self.slots():
            for k in LEVELS:
                top, bottom = L.segment_span(c, h, r, L.unit(k))
                found[(self.seg_top(d, h, c, r), k)] = self.top(d, 1, top)
                found[(self.seg_bottom(d, c, r - h), k)] = self.bottom(d, 1, bottom)
        for d, layer, h, b in self.overlays():
            for k in LEVELS:
                top, bottom = L.overlay_span(h, b, L.unit(k))
                found[(self.ovl_top(d, layer, h, b - h), k)] = self.top(d, layer, top)
                found[(self.ovl_bottom(d, layer, b - h), k)] = self.bottom(d, layer, bottom)
        return found

    def leveled(self):
        """{level-0 placeholder: [its glyph at each level]}, the glyphs that
        take the level of their group after the flat stages (and the layers,
        verticals())."""
        found = {}
        for d in self.depths:
            for w in self.widths():
                found[self.xv(d, w)] = [self.xv(d, w, k) for k in LEVELS]
            for m in self.heights():
                if m in self.row_heights():
                    found[self.row(d, m)] = [self.row(d, m, k) for k in LEVELS]
        return found

    def markers(self):
        """Every empty mark of this section (the run start is a base)."""
        found = [self.pending(c) for c in CONTROLS] + [self.flat(t) for t in SEG_TYPES[5:]]
        found += [self.tagged(t, s) for t, s in self.checked] + [self.dead(c) for c in CONTROLS]
        found += [self.poisoned] + self.tokens()
        widths, heights = [*self.widths(), OVER], [*self.heights(), OVER]
        found += [self.cell_width(a) for a in self.cell_widths()] + [self.cell_height(b) for b in self.heights()]
        found += [self.width_sum(a, s) for a in self.cell_widths() for s in [*range(a, self.max_cell[0] + 1), OVER]]
        found += [self.height_max(m) for m in self.heights()]
        found += [self.row_height0, self.row_width0, self.row_widtho, self.row_carrier0,
                  self.box_width0, self.box_height0, self.box_end0,
                  self.layer_seg0, self.layer_one0, self.layer_two0]
        found += [self.row_m(m) for m in self.heights()]
        found += [self.row_sum(m, t) for m in self.heights() for t in [*range(m, self.max_cell[1] + 1), OVER]]
        found += [self.row_width(s) for s in widths] + [self.row_pair(s) for s in self.pair_widths()]
        found += [self.carrier(g) for g in widths] + [self.justify(d) for d in range(1, L.MAX_JUSTIFY + 1)]
        found += [self.box_width(w) for w in widths] + [self.box_height(h) for h in heights]
        found += [self.layer_seg(h, c) for h in range(2, self.max_cell[1] + 1) for c in (2, 3) if c <= h]
        found += [self.layer_seg(OVER, 0)]
        found += [self.layer_one(h) for h in heights] + [self.layer_two(h) for h in heights]
        found += [self.seg_layer(d, h, c) for d in self.depths for h in range(2, self.max_cell[1] + 1)
                  for c in (2, 3) if c <= h]
        found += sorted({name for name, _ in self.verticals()})
        for d in self.depths:
            found += [self.box_end(d), self.cluster_start(d), self.cluster_end(d), self.last_row(d)]
        for name, names in self.leveled().items():
            found += [name, *names]
        found += sorted(set(self.verticals().values()))
        return list(dict.fromkeys(found))


def add_nesting(font, nesting):
    """Add the glyphs of segments and overlay. Returns the run start, the
    only base, for the glyph order."""
    font.addGlyph(Glyph(nesting.run_start, width=0))
    font.addGlyph(Glyph(nesting.bad_start, width=0))
    for name in nesting.markers():
        font.addGlyph(Glyph(name, width=0))
    return [nesting.run_start, nesting.bad_start]


# --- Insertion at middle, top and bottom (layout section 9) ------------------

SIDE_TAGS = {L.MIDDLE_INSERT: "m", L.TOP_INSERT: "t", L.BOTTOM_INSERT: "b"}


class SideInserts:
    """Glyphs of side insertion, as Inserts has them for the corners (no
    bird shrinks here): a candidate per control and shape, the zone of the
    base as two markers, the mark of the control, shape and seat (rule S4)
    that hangs from the base, and the end of the block."""

    zone_done, cluster_end = "_szx", "_sye"

    def __init__(self, signs):
        self.signs = signs
        self.insertable = sorted(signs)
        self.shape = {c: L.shape_of(signs[c]) for c in self.insertable}
        self.size = {(c, k): L.side_size(signs[c], k) for c in self.insertable for k in L.SIDE_LEVELS}
        self.zones, self.anchors = {}, defaultdict(set)  # (base, control, shape): Zone / {seat}
        fits = {}  # (zone width, height, shape): {sign: level}
        for base in sorted(signs):
            for control in L.SIDES:
                for shape, zone in signs[base].corners[control][0].items():
                    if not zone.width:
                        continue
                    key = (zone.width, zone.height, shape, control == L.MIDDLE_INSERT)
                    if key not in fits:
                        fits[key] = {}
                        for c in self.insertable:
                            if self.shape[c] != shape or not L.side_insertable(control, signs[c]):
                                continue
                            for k in L.side_levels(control):
                                w, h = self.size[(c, k)]
                                if w <= zone.width and h <= zone.height:
                                    fits[key][c] = k
                                    break
                    if fits[key]:
                        self.zones[(base, control, shape)] = zone
                        self.anchors[(base, control, shape)] = {
                            L.side_seat(control, signs[c], k) for c, k in fits[key].items()}
        self.widths = sorted({zone.width for zone in self.zones.values()})
        self.heights = sorted({zone.height for zone in self.zones.values()})
        self.shapes = sorted(L.SHAPES)
        self.mark_sizes = sorted({(control, shape, x) for (_, control, shape), xs in self.anchors.items() for x in xs})

    @staticmethod
    def candidate(control):
        return f"{control_name(control)}.ins"

    @staticmethod
    def shaped(control, shape):
        return f"{control_name(control)}.ins.{shape}"

    @staticmethod
    def zone_width(width):
        return f"_szw.{width}"

    @staticmethod
    def zone_height(height):
        return f"_szh.{height}"

    @staticmethod
    def mark(control, shape, seat):
        return f"_sn.{SIDE_TAGS[control]}.{shape}.{seat}"

    def candidates(self):
        return ([self.candidate(c) for c in L.SIDES]
                + [self.shaped(c, s) for c in L.SIDES for s in self.shapes])

    def marks(self):
        return [self.mark(c, s, x) for c, s, x in self.mark_sizes]

    def markers(self):
        return ([self.zone_width(w) for w in self.widths] + [self.zone_height(h) for h in self.heights]
                + [self.zone_done, self.cluster_end] + self.marks())


def add_side_insertion(font, sides):
    """Add the glyphs of side insertion. Returns the candidates (they have
    the advance of the box), for the glyph order."""
    for name in sides.candidates():
        glyph = Glyph(name, width=L.CONTROL_ADVANCE)
        glyph.components.append(Component(FALLBACK))
        font.addGlyph(glyph)
    for name in sides.markers():
        font.addGlyph(Glyph(name, width=0))
    return sides.candidates()


# --- Enclosures (layout section 10) -------------------------------------------

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
        self.side_enclosable = L.side_enclosable(signs)  # layout section 9
        # {base glyph of an insertion that rule E4 moves inside an enclosure:
        # (how far, code point, level)}
        self.moved = {}
        fitting = {key for key, fits in self.enclosable.items() if fits}
        fitting |= {(base, 0) for (base, _), fits in self.side_enclosable.items() if fits}
        for base, level in sorted(fitting):
            move = L.lift_in_enclosure(signs[base])
            if move:
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


# --- Sign modifiers (layout section 11) ---------------------------------------

class Modifiers:
    """Glyphs of mirroring and damage and what the features need to know.

    A sign followed by its modifiers gets a marker after it (_mk), which
    takes the modifiers into one glyph by ligature, so that they are one
    cluster with the sign: _mir (mirrored), _dm.q (damaged, q the quarters)
    or _md.q (both, later _mir and _dm.q). These and the size markers below
    are of the ligature class, which every other lookup ignores, so the
    stacking rules see the sign alone. A damaged sign gets two size markers,
    its cell's width (_dw.a) and height (_dh.b), from its lone glyph; once
    its level is known they become its quarters in tiles (_hn.v, _hm.w,
    then one glyph _hs.v.w), and each damaged quarter adds a piece of
    shading (_ht.q.v.w), a mark hung from the middle of the cell. Mirrored
    signs: the lone glyph, the variant at each of MIRROR_LEVELS and the
    shrunk bird, each one component of the sign flipped across. A damage
    modifier that is not part of a literal shows the fallback box.
    """

    marker, mirror, mirror_box = "_mk", "_mir", "_mir.box"

    def __init__(self, names):
        signs = names.signs
        self.names, self.signs = names, signs
        self.hieroglyphs = [c for c in sorted(signs) if c in L.HIEROGLYPHS]
        self.mirrored = [c for c in self.hieroglyphs if not L.symmetric(c)]
        self.symmetric = [c for c in self.hieroglyphs if L.symmetric(c)]
        self.levels = list(L.MIRROR_LEVELS)
        mirrored = set(self.mirrored)
        self.shrunk = [(c, k) for c, k in names.inserts.shrunk_glyphs if c in mirrored]
        self.quarters = [L.quadrants(c) for c in L.DAMAGE]
        self.cell_widths = sorted({signs[c].cell[0] for c in self.hieroglyphs})
        self.cell_heights = sorted({signs[c].cell[1] for c in self.hieroglyphs})
        # (across, up) in tiles of every quarter a sign can have, at any level
        self.sizes = sorted({L.damage_size(signs[c], k)[:2] for c in self.hieroglyphs
                             for k in range(len(L.LEVEL_HEIGHTS))})
        self.across = sorted({v for v, _ in self.sizes})
        self.up = sorted({w for _, w in self.sizes})

    # -- names --
    def lone(self, codepoint):
        return f"{self.signs[codepoint].name}.m"

    def variant(self, codepoint, level):  # sorts after the variants of its level, as a block
        return f"_{level}m.{self.signs[codepoint].name}"

    def shrunk_glyph(self, codepoint, level):
        return f"{self.names.inserts.shrunk(codepoint, level)}.m"

    @staticmethod
    def both(q):
        return f"_md.{q}"

    @staticmethod
    def damaged(q):
        return f"_dm.{q}"

    @staticmethod
    def width(a):  # the cell's width in half units, then in tiles
        return f"_dw.{a}" if a else "_dw.0"

    @staticmethod
    def height(b):
        return f"_dh.{b}" if b else "_dh.0"

    @staticmethod
    def across_tiles(v):
        return f"_hn.{v}"

    @staticmethod
    def up_tiles(w):
        return f"_hm.{w}"

    @staticmethod
    def size(v, w):
        return f"_hs.{v}.{w}"

    @staticmethod
    def piece(q, v, w):
        return f"_ht.{q}.{v}.{w}"

    @staticmethod
    def stray(codepoint):  # a damage modifier as typed: the box
        return control_name(codepoint)

    # -- families --
    def mirrored_variants(self, codepoint, level):
        """The mirrored variant of a sign at a level, as a list (empty if none)."""
        return [self.variant(codepoint, level)] if level in self.levels and codepoint in self._mirrored else []

    @property
    def _mirrored(self):
        if not hasattr(self, "_mirrored_set"):
            self._mirrored_set = set(self.mirrored)
        return self._mirrored_set

    def pieces(self):
        return [self.piece(q, v, w) for q in L.QUADRANTS for v, w in self.sizes]

    def markers(self):
        """Empty glyphs of the ligature class."""
        return ([self.marker, self.mirror] + [self.both(q) for q in self.quarters]
                + [self.damaged(q) for q in self.quarters]
                + [self.width(a) for a in [0, *self.cell_widths]] + [self.height(b) for b in [0, *self.cell_heights]]
                + [self.across_tiles(v) for v in self.across] + [self.up_tiles(w) for w in self.up]
                + [self.size(v, w) for v, w in self.sizes])

    def bases(self):
        """Glyphs with an advance: mirrored lone signs and birds, and the boxes."""
        return ([self.lone(c) for c in self.mirrored] + [self.shrunk_glyph(c, k) for c, k in self.shrunk]
                + [self.stray(c) for c in L.DAMAGE])

    def marks(self):
        """Mirrored variants and the pieces of shading."""
        return [self.variant(c, k) for k in self.levels for c in self.mirrored] + self.pieces() + [self.mirror_box]


def _hatch(pen, rect):
    """Rule M7 of layout.py: the lines of shading inside rect, in the
    coordinates of the middle point; each line, cut to rect, one contour."""
    x0, y0, x1, y1 = rect
    half = L.HATCH_STROKE // 2
    first = (x0 - y1 - half) // L.HATCH_PERIOD - 1
    last = (x1 - y0 + half) // L.HATCH_PERIOD + 1
    for k in range(first, last + 1):
        low, high = k * L.HATCH_PERIOD - half, k * L.HATCH_PERIOD + half  # low <= x - y <= high
        polygon = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # counter-clockwise
        for inside, cross in ((lambda x, y: x - y >= low, low), (lambda x, y: x - y <= high, high)):
            clipped = []
            for i, (p, q) in enumerate(zip(polygon, polygon[1:] + polygon[:1])):
                if inside(*p):
                    clipped.append(p)
                if inside(*p) != inside(*q):  # the edge crosses x - y = cross
                    if p[0] == q[0]:
                        clipped.append((p[0], p[0] - cross))
                    else:
                        clipped.append((p[1] + cross, p[1]))
            polygon = [p for i, p in enumerate(clipped) if p != clipped[i - 1]] if clipped else []
        if len(polygon) >= 3:
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
            if area > 0:
                pen.moveTo(polygon[0])
                for point in polygon[1:]:
                    pen.lineTo(point)
                pen.closePath()


def add_modifiers(font, names):
    """Add the glyphs of the sign modifiers. Returns those with an advance,
    for the glyph order; the rest come last, sorted by name."""
    m = names.modifiers
    for codepoint in m.mirrored:
        sign = names.signs[codepoint]
        glyph = Glyph(m.lone(codepoint), width=sign.advance)
        glyph.components.append(Component(sign.name, (-1, 0, 0, 1, sign.box[0] + sign.box[2], 0)))
        font.addGlyph(glyph)
    for codepoint, level in m.shrunk:
        sign = names.signs[codepoint]
        scale, x, y = L.shrink(sign.box, level)
        offset = (x + L._round(scale * (sign.box[0] + sign.box[2])), L._round(y + sign.lift - scale * sign.lift))
        glyph = Glyph(m.shrunk_glyph(codepoint, level), width=sign.advance)
        glyph.components.append(Component(sign.name, (-scale, 0, 0, scale, *offset)))
        font.addGlyph(glyph)
    for codepoint in L.DAMAGE:
        glyph = Glyph(m.stray(codepoint), width=L.CONTROL_ADVANCE, unicodes=[codepoint])
        glyph.components.append(Component(FALLBACK))
        font.addGlyph(glyph)
    for level in m.levels:  # as add_stacking() places the variant, flipped across
        for codepoint in m.mirrored:
            sign = names.signs[codepoint]
            scale = sign.scales[level]
            dx, dy = L.sign_offset(sign, level)
            offset = (dx + L._round(scale * (sign.box[0] + sign.box[2])), L._round(dy - scale * sign.lift))
            glyph = Glyph(m.variant(codepoint, level), width=0)
            glyph.components.append(Component(sign.name, (-scale, 0, 0, scale, *offset)))
            font.addGlyph(glyph)
    turned = {8: 1, 2: 4}  # a bottom piece is the top piece across from it, turned half round
    for q in L.QUADRANTS:
        for v, w in m.sizes:
            glyph = Glyph(m.piece(q, v, w), width=0)
            if q in turned:
                glyph.components.append(Component(m.piece(turned[q], v, w), (-1, 0, 0, -1, 0, 0)))
            else:
                _hatch(glyph.getPen(), L.hatch_rect(L.hatch_code(q, v, w)))
            font.addGlyph(glyph)
    glyph = Glyph(m.mirror_box, width=0)  # rule M8
    box = L.mirror_box(0, 0)
    glyph.components.append(Component(FALLBACK, (box.scale, 0, 0, box.scale, box.x, box.y)))
    font.addGlyph(glyph)
    for name in m.markers():
        font.addGlyph(Glyph(name, width=0))
    return m.bases()
