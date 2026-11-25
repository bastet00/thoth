"""OpenType layout: GDEF classes and the feature file.

The features compute what layout.py computes, with glyphs as the only
memory (their names are in glyphs.Names). GSUB, feature rlig:

 1. check    a joiner joins if it stands between two signs; then every
             control of a run that has any other control (a joiner at its
             end, next to another control, an unsupported control) stays a
             box, so the run is drawn unstacked (rule 9).
 2. expand   each sign of a group becomes its cell width, its cell height
             and its level-0 variant; the group gets a head and each row a
             row head, a row-width marker and a carrier.
 3. fold     right to left (reverse chaining substitution): the width and
             height of each row, the widest row, the height of the group
             and its number of rows. Sums beyond the caps become OVER.
 4. head     the head becomes Q, the group's width and level (its advance
             and axis), and V, where its rows hang (top and bottom). A
             group over the caps falls back: lone signs and boxes (rule 9).
 5. justify  the group's width goes to every row; a row of two with slack
             takes the group's width, and a spacer goes between its cells.
 6. level    the level goes from Q to every marker and sign after it.
 7. cluster  the group becomes one cluster: a ligature joins the end of
             each cell to the start of the next, and HarfBuzz gives a
             ligature and everything between its parts one cluster value,
             so no text engine puts letter spacing or a line break inside
             a group.

GPOS, features mark and mkmk: every glyph of a group hangs from one before
it: V from Q (on the axis), each row from V or the row above, the last row
from V's bottom, the row-width marker from its row, each sign from the
row's left edge or the sign (or spacer) before it. The lookups come parent
first, because CoreText applies attachments in lookup order.

The numbers all come from layout.py (span, centre, half, advance, slack,
fit_level, unit, the sign table); nothing here decides geometry.
"""

from collections import defaultdict

import layout as L
from glyphs import CONTROLS, LEVELS, OVER, control_name

SIGNS = range(0x13000, 0x13460)  # Egyptian Hieroglyphs and their format controls
DOTTED_CIRCLE = 0x25CC
SYSTEMS = (("DFLT", "dflt"), ("egyp", "dflt"))  # where the stacking lookups apply


def cls(names):
    return "[" + " ".join(names) + "]"


class Writer:
    def __init__(self):
        self.text, self.gsub, self.gpos = [], [], []

    def define(self, name, glyphs):
        self.text.append(f"@{name} = {cls(glyphs)};")
        return f"@{name}"

    def lookup(self, name, rules, marks=None, table=None):
        """A lookup; marks: its mark filtering set; table: "gsub" or "gpos"
        if a feature applies it (else it is only called by other lookups)."""
        flag = [f"    lookupflag UseMarkFilteringSet {marks};"] if marks else []
        self.text += [f"lookup {name} {{", *flag, *(f"    {r};" for r in rules), f"}} {name};"]
        if table:
            getattr(self, table).append(name)


def _gsub(n, w):
    signs = sorted(n.signs)
    vj, hj = control_name(L.VERTICAL_JOINER), control_name(L.HORIZONTAL_JOINER)
    vjo, hjo = n.joined[L.VERTICAL_JOINER], n.joined[L.HORIZONTAL_JOINER]
    widths, cells, heights = [*n.widths, OVER], n.cell_widths, [*n.heights, OVER]
    lone = w.define("SIGN", [n.lone(c) for c in signs])
    var0 = w.define("S0", [n.variant(c, 0) for c in signs])
    okj = w.define("OKJ", [vjo, hjo])
    bad = w.define("BAD", [control_name(c) for c in CONTROLS])
    cw = w.define("CW", [n.cell_width(a) for a in cells])
    ch = w.define("CH", [n.cell_height(b) for b in n.cell_heights])
    cf = w.define("CF", [n.width_sum(a, s) for a, s in n.width_sums()])
    chf = w.define("CHF", [n.height_max(m) for m in n.cell_heights])
    rhm = w.define("RHM", [n.row_height(m) for m in n.cell_heights])
    rhf = w.define("RHF", [n.height_sum(m, t) for m, t in n.height_sums()])
    rws = w.define("RWS", [n.row_width(s) for s in widths])
    rw2 = w.define("RW2", [n.pair_width(s) for s in n.widths[1:]])
    wc = w.define("WC", [n.carrier(g) for g in widths])
    jst = w.define("J", [n.justify(d) for d in n.slacks])
    vh = w.define("VH", [n.vertical_size(h, c) for h, c in n.vertical_sizes()])
    mk = w.define("MK", [m for m in n.markers() if m not in (n.vj, n.hj, n.fallback)])

    def width_sums(total):  # cells whose row is `total` wide from them on
        return cls(n.width_sum(a, total) for a in cells if total == OVER or a <= total)

    def height_sums(total):
        return cls(n.height_sum(m, total) for m in n.cell_heights if total == OVER or m <= total)

    def plus(a, s, cap):
        return OVER if s == OVER or a + s > cap else a + s

    def rows_of(*totals):  # row-width markers of rows this wide
        return cls(x for s in totals for x in [n.row_width(s)] + [n.pair_width(s)] * (s not in (1, OVER)))

    # 0. HarfBuzz's USE shaper puts a dotted circle before a ZWNJ that starts
    # a cluster; the text has nothing there to show
    w.lookup("hide", [f"sub {n.dotted_circle} by {n.hidden}"])
    w.lookup("no_dotted_circle", [f"sub {n.dotted_circle}' lookup hide {n.zwnj}"], table="gsub")

    # 1. check
    w.lookup("okj", [f"sub {vj} by {vjo}", f"sub {hj} by {hjo}"])
    w.lookup("unok", [f"sub {vjo} by {vj}", f"sub {hjo} by {hj}"])
    # HarfBuzz skips a default ignorable when it matches context, unless
    # the rule names it, so the rules name them where they end a run
    ign = w.define("IGNORABLE", n.ignorables)
    w.lookup("check", [f"ignore sub {ign} [{vj} {hj}]'", f"ignore sub [{vj} {hj}]' {ign}",
                       f"sub {lone} [{vj} {hj}]' lookup okj {lone}"], table="gsub")
    w.lookup("bad_after", [f"ignore sub {bad} {ign} {lone} {okj}'",
                           f"sub {bad} {lone} {okj}' lookup unok"], table="gsub")
    w.lookup("bad_before", [f"rsub {okj}' {lone} {ign} by {okj}",  # as is
                            f"rsub {okj}' {lone} {bad} by [{vj} {hj}]"], table="gsub")

    # 2. expand
    w.lookup("cell", [f"sub {n.lone(c)} by {n.cell_width(n.signs[c].cell[0])} "
                      f"{n.cell_height(n.signs[c].cell[1])} {n.variant(c, 0)}" for c in signs])
    head = f"{n.head0} {n.vertical0} {n.row0} {n.width0} {n.carrier0}"
    w.lookup("prefix", [f"sub {n.cell_width(a)} by {head} {n.cell_width(a)}" for a in cells])
    w.lookup("expand", [f"sub {okj} {lone}' lookup cell", f"sub {lone}' lookup cell {okj}"],
             table="gsub")
    w.lookup("start", [f"ignore sub {okj} {cw}'", f"sub {cw}' lookup prefix"], table="gsub")
    w.lookup("join_rows", [f"sub {vjo} by {n.vj} {n.row0} {n.width0} {n.carrier0}"], table="gsub")
    w.lookup("join_cells", [f"sub {hjo} by {n.hj}"], table="gsub")

    # 3. fold, right to left. A row ends where the next row's marker starts.
    rules = [f"rsub {cw}' {width_sums(s)} by {cls(n.width_sum(a, plus(a, s, L.MAX_WIDTH)) for a in cells)}"
             for s in widths]
    rules.append(f"rsub {cw}' by {cls(n.width_sum(a, a) for a in cells)}")
    w.lookup("row_widths", rules, w.define("F_ROW_WIDTHS", [cw, cf, n.width0]), "gsub")
    rules = [f"rsub {ch}' {n.height_max(m)} by {cls(n.height_max(max(b, m)) for b in n.cell_heights)}"
             for m in n.cell_heights]
    rules.append(f"rsub {ch}' by {cls(n.height_max(b) for b in n.cell_heights)}")
    w.lookup("row_heights", rules, w.define("F_ROW_HEIGHTS", [ch, chf, n.width0]), "gsub")
    last = cls(n.width_sum(b, b) for b in cells)  # the last cell of its row
    rules = [f"rsub {n.width0}' {cls(n.width_sum(a, s) for a in cells if a < s)} {last} by {n.pair_width(s)}"
             for s in n.widths if s > 1]
    rules += [f"rsub {n.width0}' {width_sums(s)} by {n.row_width(s)}" for s in widths]
    w.lookup("row_width", rules, w.define("F_ROW_WIDTH", [n.width0, cf]), "gsub")
    rules = [f"rsub {n.row0}' {n.height_max(m)} by {n.row_height(m)}" for m in n.cell_heights]
    w.lookup("row_height", rules, w.define("F_ROW_HEIGHT", [n.row0, chf]), "gsub")
    # the widest row, on the carrier after each row-width marker
    rules = [f"rsub {rows_of(OVER)} {n.carrier0}' by {n.carrier(OVER)}",
             f"rsub {n.carrier0}' @RWANY {n.carrier(OVER)} by {n.carrier(OVER)}"]
    w.define("RWANY", [rws, rw2])
    for r in n.widths:
        rules.append(f"rsub {rows_of(r)} {n.carrier0}' @RWANY "
                     f"{cls(n.carrier(g) for g in range(1, r + 1))} by {n.carrier(r)}")
        if r > 1:
            rules.append(f"rsub {rows_of(*range(1, r))} "
                         f"{n.carrier0}' @RWANY {n.carrier(r)} by {n.carrier(r)}")
    rules += [f"rsub {rows_of(r)} {n.carrier0}' by {n.carrier(r)}" for r in n.widths]
    w.lookup("group_width", rules, w.define("F_GROUP_WIDTH", ["@RWANY", n.carrier0, wc]), "gsub")
    rules = [f"rsub {rhm}' {height_sums(t)} by "
             f"{cls(n.height_sum(m, plus(m, t, L.MAX_HEIGHT)) for m in n.cell_heights)}" for t in heights]
    rules.append(f"rsub {rhm}' by {cls(n.height_sum(m, m) for m in n.cell_heights)}")
    w.lookup("group_height", rules, w.define("F_GROUP_HEIGHT", [rhm, rhf]), "gsub")

    # 4. head
    rules = [f"rsub {n.head0}' {n.carrier(g)} by {n.head_width(g)}" for g in n.widths]
    rules.append(f"rsub {n.head0}' {n.carrier(OVER)} by {n.fallback_head}")
    w.lookup("head_width", rules, wc, "gsub")
    lasts = cls(n.height_sum(m, m) for m in n.cell_heights)  # the last row of its group
    rules = []
    for h, count in n.vertical_sizes():
        if count == 1:
            context = n.height_sum(h, h)
        elif count == 2:
            context = f"{cls(n.height_sum(m, h) for m in n.cell_heights if m < h)} {lasts}"
        else:
            context = height_sums(h)
        rules.append(f"rsub {n.vertical0}' {context} by {n.vertical_size(h, count)}")
    rules.append(f"rsub {n.vertical0}' {height_sums(OVER)} by {n.vertical_over}")
    w.lookup("group_height_head", rules, w.define("F_V", [n.vertical0, rhf]), "gsub")
    # the level: the head's from its width and V's height, then V's top and
    # bottom from its height, row count and the head's level
    rules = []
    for j in LEVELS:
        sizes = [n.vertical_size(h, c) for h, c in n.vertical_sizes() if L.fit_level(1, h) == j]
        rules.append(f"rsub {cls(n.head_width(g) for g in n.widths)}' {cls(sizes)} by "
                     f"{cls(n.head(g, max(j, L.fit_level(g, 1))) for g in n.widths)}")
    rules.append(f"rsub {cls(n.head_width(g) for g in n.widths)}' {n.vertical_over} by {n.fallback_head}")
    w.lookup("head_level", rules, w.define("F_HEAD", [vh, n.vertical_over]), "gsub")
    rules = []
    for k in LEVELS:
        heads = [n.head(g, j) for g, j in n.head_sizes if j == k]
        sizes = [(h, c) for h, c in n.vertical_sizes() if L.fit_level(1, h) <= k]
        rules.append(f"rsub {cls(heads)} {cls(n.vertical_size(h, c) for h, c in sizes)}' by "
                     f"{cls(n.vertical_final(*L.span(c, h, L.unit(k))) for h, c in sizes)}")
    w.lookup("head_rows", rules, vh, "gsub")
    # a group over the caps: every marker becomes _x, then each sign and
    # joiner after an _x goes back to its lone glyph and its box
    w.lookup("to_fallback", [f"sub {mk} by {n.fallback}"])
    w.lookup("revert", [f"sub {var0} by {lone}", f"sub {n.vj} by {vj}", f"sub {n.hj} by {hj}"])
    w.lookup("fallback", [f"sub [{n.fallback_head} {n.fallback}] {mk}' lookup to_fallback"],
             w.define("F_FALLBACK", [n.fallback, mk]), "gsub")
    # joiners first: a sign that is back is a base, and bases end a context
    w.lookup("unstack_joiners", [f"sub {n.fallback} [{n.vj} {n.hj}]' lookup revert"],
             w.define("F_UNSTACK_JOINERS", [n.fallback, n.vj, n.hj]), "gsub")
    w.lookup("unstack_signs", [f"sub {n.fallback} {var0}' lookup revert"],
             w.define("F_UNSTACK_SIGNS", [n.fallback, var0]), "gsub")

    # 5. justify: the carrier of the first row has the group's width
    rules = []
    for g in n.widths[1:]:
        narrower = [n.carrier(x) for x in range(1, g)]
        w.lookup(f"width_{g}", [f"sub {cls(narrower)} by {n.carrier(g)}"])
        rules.append(f"sub {n.carrier(g)} {cls(narrower)}' lookup width_{g}")
    w.lookup("group_width_rows", rules, wc, "gsub")
    rules = []
    for s in n.widths[1:]:
        groups = [g for g in range(s + 1, s + L.MAX_JUSTIFY + 1) if g in n.widths]
        if groups:
            rules.append(f"rsub {n.pair_width(s)} {cls(n.carrier(g) for g in groups)}' by "
                         f"{cls(n.justify(L.slack((0, 0), g, s)) for g in groups)}")
    w.lookup("justify", rules, w.define("F_JUSTIFY", [rw2, rws, wc]), "gsub")
    rules = [f"rsub {n.justify(d)} {n.hj}' by {n.spacer(d, 0)}" for d in n.slacks]
    for d in n.slacks:
        pairs = [s for s in n.widths[1:] if s + d in n.widths]
        rules.append(f"rsub {cls(n.pair_width(s) for s in pairs)}' {n.justify(d)} by "
                     f"{cls(n.row_left(s + d, 0) for s in pairs)}")
    w.lookup("justify_rows", rules, w.define("F_JUSTIFY_ROWS", [jst, wc, n.hj, rw2]), "gsub")
    rules = [f"sub {n.row_width(s)} by {n.row_left(s, 0)}" for s in n.widths]
    rules += [f"sub {n.pair_width(s)} by {n.row_left(s, 0)}" for s in n.widths[1:]]
    rules += [f"sub {n.height_sum(m, t)} by {n.last_row(0) if t == m else n.row(m, 0)}"
              for m, t in n.height_sums() if t != OVER]
    w.lookup("row_heads", rules, table="gsub")

    # 6. level, from Q to everything after it in the group
    leveled = {k: w.define(f"L{k}", n.leveled(k)) for k in LEVELS}
    rules = []
    for k in LEVELS[1:]:
        w.lookup(f"to_level_{k}", [f"sub {leveled[0]} by {leveled[k]}"])
        heads = [n.head(g, j) for g, j in n.head_sizes if j == k]
        rules.append(f"sub [{' '.join(heads)} {leveled[k]}] {leveled[0]}' lookup to_level_{k}")
    w.lookup("levels", rules, w.define("F_LEVELS", [*leveled.values()]), "gsub")

    # 7. cluster. Every cell of a group still has its width marker first and
    # its height marker before its sign; they have done their work, so they
    # become the start and the end of the cell. The ligature of a cell's end
    # and the next cell's start skips the sign and the joiner between them
    # (all marks); bases, the head of the next group or a lone sign, stop it.
    # Its parts are marks, so it is a mark ligature: HarfBuzz gives it no
    # ligature id, and the mark attachments of GPOS are unchanged.
    w.lookup("cell_ends", [f"sub {cf} by {n.cell_start}", f"sub {chf} by {n.cell_end}"], table="gsub")
    w.lookup("one_cluster", [f"sub {n.cell_end} {n.cell_start} by {n.cell_start}"],
             w.define("F_CLUSTER", [n.cell_end, n.cell_start]), "gsub")


def _gpos(n, w):
    signs = sorted(n.signs)
    vf = [(key, n.vertical_final(*key)) for key in n.vertical]
    w.text.append(f"markClass {cls(name for _, name in vf)} <anchor 0 0> @mV;")
    rules = [f"pos base {n.head(g, k)} <anchor {L.centre(g, L.half_unit(k))} 0> mark @mV"
             for g, k in n.head_sizes]
    w.lookup("place_head", rules, table="gpos")

    rows = [(n.row(m, k), m * L.unit(k)) for k in LEVELS for m in n.cell_heights]
    for name, up in rows:
        w.text.append(f"markClass {name} <anchor 0 {up}> @mROW;")
    rules = [f"pos mark {name} <anchor 0 {top}> mark @mROW" for (top, _), name in vf]
    rules.append(f"pos mark {cls(name for name, _ in rows)} <anchor 0 0> mark @mROW")
    w.lookup("place_rows", rules, w.define("F_ROWS", [name for _, name in vf] + [name for name, _ in rows]),
             "gpos")
    lasts = [n.last_row(k) for k in LEVELS]
    w.text.append(f"markClass {cls(lasts)} <anchor 0 0> @mLAST;")
    rules = [f"pos mark {name} <anchor 0 {bottom}> mark @mLAST" for (_, bottom), name in vf]
    w.lookup("place_last_row", rules, w.define("F_LAST", [name for _, name in vf] + lasts), "gpos")

    lefts = [(n.row_left(s, k), L.half(s, L.half_unit(k))) for k in LEVELS for s in n.widths]
    for name, x in lefts:
        w.text.append(f"markClass {name} <anchor {x} 0> @mLEFT;")
    heads = [name for name, _ in rows] + lasts
    w.lookup("place_row_left", [f"pos mark {cls(heads)} <anchor 0 0> mark @mLEFT"],
             w.define("F_LEFT", heads + [name for name, _ in lefts]), "gpos")

    # cells: a sign hangs by the left edge of its cell, the next one from its
    # right edge; a spacer moves the next cell by the slack
    enter, leave = defaultdict(list), defaultdict(list)
    for k in LEVELS:
        step = L.half_unit(k)  # cells and spacers go across
        for c in signs:
            a = n.signs[c].cell[0]
            enter[-L.half(a, step)].append(n.variant(c, k))
            leave[a * step - L.half(a, step)].append(n.variant(c, k))
        for d in n.slacks:
            enter[0].append(n.spacer(d, k))
            leave[d * step].append(n.spacer(d, k))
    for x, names in sorted(enter.items()):
        w.text.append(f"markClass {cls(names)} <anchor {x} 0> @mCELL;")
    rules = [f"pos mark {cls(name for name, _ in lefts)} <anchor 0 0> mark @mCELL"]
    rules += [f"pos mark {cls(names)} <anchor {x} 0> mark @mCELL" for x, names in sorted(leave.items())]
    members = [name for name, _ in lefts] + [x for names in enter.values() for x in names]
    w.lookup("place_cells", rules, w.define("F_CELLS", members), "gpos")


def categories(font, names):
    """GDEF glyph classes, in the form of public.openTypeCategories.

    The Latin letters and marks arrive with their own classes. Every sign
    and control is a base, also U+13440, which Unicode calls a mark: HarfBuzz
    removes the advance of a mark, and the fallback would cover the next sign.
    The group heads are bases, the rest of what the generator adds is marks.
    """
    bases = {glyph.name for glyph in font
             if any(u in SIGNS or u == DOTTED_CIRCLE for u in glyph.unicodes)}
    bases |= {*names.joined.values(), *names.heads()}
    marks = set(names.markers())
    for level in LEVELS:
        marks |= set(names.leveled(level))
    found = {name: "base" for name in bases}
    found.update({name: "mark" for name in marks})
    return dict(sorted(found.items()))


def add_features(font, names):
    w = Writer()
    w.text += [f"languagesystem {script} {language};" for script, language in SYSTEMS]
    _gsub(names, w)
    _gpos(names, w)

    def feature(tag, lookups, automatic=False):
        # ufo2ft puts the Latin mark rules at "# Automatic Code", for every
        # script; the stacking lookups are registered for SYSTEMS only
        body = ["    # Automatic Code"] if automatic else []
        for script, language in SYSTEMS:
            body += [f"    script {script};", f"    language {language};"]
            body += [f"    lookup {name};" for name in lookups]
        return [f"feature {tag} {{", *body, f"}} {tag};"]

    w.text += feature("rlig", w.gsub)
    w.text += feature("mark", w.gpos[:1], automatic=True)
    w.text += feature("mkmk", w.gpos[1:], automatic=True)
    font.lib["public.openTypeCategories"] = categories(font, names)
    font.features.text = "\n".join(w.text) + "\n"
