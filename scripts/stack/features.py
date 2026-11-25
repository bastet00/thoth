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

Before all of these, under feature calt, the automatic layer (layout
section 7) adds the controls that the table and the shape rule imply in plain text; see
_gsub_auto(). HarfBuzz applies calt and rlig in the same stage, lookup by
lookup in the order of the lookup list, so the automatic lookups, which
come first in it, run before the stacking lookups; a text engine can turn
calt off and leave rlig on.

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
RULES = 1500  # automatic layer: about this many rules to a subtable


def cls(names):
    return "[" + " ".join(names) + "]"


class Writer:
    def __init__(self):
        self.text, self.gsub, self.gpos = [], [], []

    def define(self, name, glyphs):
        self.text.append(f"@{name} = {cls(glyphs)};")
        return f"@{name}"

    def lookup(self, name, rules, marks=None, table=None, extension=False, flags="IgnoreLigatures"):
        """A lookup; marks: its mark filtering set; table: "gsub" or "gpos"
        if a feature applies it (else it is only called by other lookups);
        extension: stored as an extension lookup, at the end of its table;
        flags: by default the lookup ignores the ligature class, which only
        the markers of the sign modifiers have (_gsub_modifiers())."""
        flag = " ".join(f for f in (flags, f"UseMarkFilteringSet {marks}" if marks else "") if f)
        flag = [f"    lookupflag {flag};"] if flag else []
        ext = " useExtension" if extension else ""
        self.text += [f"lookup {name}{ext} {{", *flag, *(f"    {r};" for r in rules), f"}} {name};"]
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
    _gsub_insert(n, w, lone, ign)  # corner insertion comes first: its fallback is a flat group
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


def _gsub_auto(n, w, auto):
    """The automatic layer (layout rules A1 to A9), feature calt. S is a
    lone sign, C a control as typed, I a default ignorable. Returns the
    lookups, in order.

     1. words    a word start goes before S if neither S nor C is before
                 it, a word end after S if neither S nor C follows it; the
                 rules name I where it is next to S, as HarfBuzz would skip
                 it in context (rule A2). Every stretch then has a word
                 start, or C right before it, and a word end, or C right
                 after it; signs of different stretches never touch.
     2. slots    an empty slot goes between every two signs of a stretch.
     3. stack    one rule per table entry, longest first, the entries that
                 hold at a word start before the others, matched over the
                 signs (the slots are skipped); an entry marked START has
                 the word start as its backtrack, one marked END the word
                 end as its lookahead. At each sign that the arrangement
                 joins to the next, the slot after it becomes that implied
                 control, and every other slot of the entry an inner slot:
                 a substitution of one glyph by one, so that the rule's
                 positions do not move. A rule consumes its signs, so the
                 next rule is tried after them (rule A4). S right after C
                 starts nothing (rule A5).
     3b. shape   the signs that no entry took (no inner slot or implied
                 control next to them) and that are half-block (rule A7):
                 a run of them right after a free lower sign has its slots
                 kept; otherwise they become blocks two by two, the slot
                 between the two a vertical joiner (rule A8); a block does
                 not start right after C (rule A9).
     4. release  right to left, an implied control before the S that is
                 right before C, and every implied control of the same
                 block before it, becomes an empty glyph (rule A5).
     5. controls the implied controls become the controls, for the
                 stacking lookups. The slots that are left stay, empty, between
                 signs that were apart anyway.
    """
    signs = sorted(n.signs)
    sign = w.define("A_SIGN", [n.lone(c) for c in signs])
    ctrl = w.define("A_CTRL", [control_name(c) for c in CONTROLS])
    ign = w.define("A_IGNORABLE", n.ignorables)
    lookups = []

    # 1. words, 2. slots
    for name, output in (("auto_start_mark", "{a} {s}"), ("auto_end_mark", "{s} {b}"),
                         ("auto_slot_mark", "{s} {c}")):
        w.lookup(name, [f"sub {n.lone(c)} by " + output.format(a=auto.start, b=auto.end, c=auto.slot,
                                                                s=n.lone(c)) for c in signs])
    w.lookup("auto_starts", [f"sub {ign} {sign}' lookup auto_start_mark", f"ignore sub [{sign} {ctrl}] {sign}'",
                             f"sub {sign}' lookup auto_start_mark"])
    w.lookup("auto_ends", [f"sub {sign}' lookup auto_end_mark {ign}", f"ignore sub {sign}' [{sign} {ctrl}]",
                           f"sub {sign}' lookup auto_end_mark"])
    w.lookup("auto_slots", [f"sub {sign}' lookup auto_slot_mark {sign}"])
    lookups += ["auto_starts", "auto_ends", "auto_slots"]

    # 3. stack: at a sign, the slot after it becomes an implied control,
    # or an inner slot where the entry joins nothing
    for control in auto.controls:
        w.lookup(f"auto_to_{control_name(control)}", [f"sub {auto.slot} by {auto.join(control)}"])
        w.lookup(f"auto_{control_name(control)}",
                 [f"sub {sign}' {auto.slot}' lookup auto_to_{control_name(control)}"])
    w.lookup("auto_to_inner", [f"sub {auto.slot} by {auto.inner}"])
    w.lookup("auto_inner", [f"sub {sign}' {auto.slot}' lookup auto_to_inner"])

    def order(item):  # by the first sign; the rules of one sign as rule A4 tries them
        key, _ = item
        first = key[1] if key[0] == L.START else key[0]
        return (first, key[0] != L.START, -len(key), L.write_entry(*item))

    # a subtable takes the rules of whole first signs, about RULES of them,
    # so that it stays in the 16-bit offsets of format 1 (rules by glyph)
    rules, count, previous = [f"ignore sub {ctrl} {sign}'"], 0, None
    for key, arrangement in sorted(auto.table.items(), key=order):
        first = order((key, arrangement))[0]
        if first != previous and (previous is None or count >= RULES):
            rules.append("subtable")
            count = 0
        previous, count = first, count + 1
        follows = []  # the control after each sign of the entry, or None
        for block in arrangement:
            for a, b in zip(block, (*block[1:], None)):
                if L.is_sign(a):
                    follows.append(None if b is None or L.is_sign(b) else b)
        signs_of = [c for c in key if c not in (L.START, L.END)]
        body = " ".join(f"{n.lone(c)}'" + (f" lookup auto_{control_name(f) if f else 'inner'}"
                                           if i < len(signs_of) - 1 else "")
                        for i, (c, f) in enumerate(zip(signs_of, follows)))
        back = f"{auto.start} " if key[0] == L.START else ""
        ahead = f" {auto.end}" if key[-1] == L.END else ""
        rules.append(f"sub {back}{body}{ahead}")
    w.lookup("auto_stack", rules, w.define("A_WORD", [auto.start, auto.end]), extension=True)
    lookups.append("auto_stack")

    # 3b. shape (rules A7 to A9), over the signs no entry took: theirs are
    # the signs with no inner slot or implied control on either side. A
    # sign is free on its left after a slot, a word start or a control.
    signs_table = n.signs
    half = [c for c in signs if L.half_block(c, signs_table)]
    lower = [c for c in signs if not L.half_block(c, signs_table) and signs_table[c].cell[1] < L.HEIGHT_LIMIT]
    half_cls = w.define("A_HALF", [n.lone(c) for c in half])
    lower_cls = w.define("A_LOWER", [n.lone(c) for c in lower])
    vj = f"auto_to_{control_name(L.VERTICAL_JOINER)}"
    w.lookup("auto_to_kept", [f"sub {auto.slot} by {auto.kept}"])
    free_left = f"[{auto.slot} {auto.start} {ctrl}]"
    free_right = f"[{auto.slot} {auto.end} {ctrl}]"
    start_left = f"[{auto.slot} {auto.start}]"  # rule A9: not after a control
    rules = [  # a run right after a free lower sign stays as it is: its slots are kept
        f"sub {free_left} {lower_cls} {auto.slot} {half_cls}' {auto.slot}' lookup auto_to_kept {half_cls}",
        f"sub {auto.kept} {half_cls}' {auto.slot}' lookup auto_to_kept {half_cls}",
        "subtable",  # else two, the first above the second
        f"sub {start_left} {half_cls}' {auto.slot}' lookup {vj} {half_cls}' {free_right}",
    ]
    w.lookup("auto_shape", rules)
    lookups.append("auto_shape")

    # 4. release, 5. controls
    rules = []
    for name in [auto.join(c) for c in auto.controls]:
        rules += [f"rsub {name}' {sign} {ctrl} by {auto.null}", f"rsub {name}' {sign} {auto.null} by {auto.null}"]
    w.lookup("auto_release", rules)
    w.lookup("auto_controls", [f"sub {auto.join(c)} by {control_name(c)}" for c in auto.controls])
    return lookups + ["auto_release", "auto_controls"]


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
            for name in [n.variant(c, k)] + n.modifiers.mirrored_variants(c, k):  # mirrored: the same cell
                enter[-L.half(a, step)].append(name)
                leave[a * step - L.half(a, step)].append(name)
        for d in n.slacks:
            enter[0].append(n.spacer(d, k))
            leave[d * step].append(n.spacer(d, k))
    for x, names in sorted(enter.items()):
        w.text.append(f"markClass {cls(names)} <anchor {x} 0> @mCELL;")
    rules = [f"pos mark {cls(name for name, _ in lefts)} <anchor 0 0> mark @mCELL"]
    rules += [f"pos mark {cls(names)} <anchor {x} 0> mark @mCELL" for x, names in sorted(leave.items())]
    members = [name for name, _ in lefts] + [x for names in enter.values() for x in names]
    w.lookup("place_cells", rules, w.define("F_CELLS", members), "gpos")


def _gsub_insert(n, w, lone, ign):
    """Corner insertion (layout section 6), before the flat stages, whose
    horizontal joiner is its fallback. B is the base, C the corner control,
    S the inserted sign.

     1. check    C between two lone signs becomes a candidate, unless an
                 ignorable touches it; a candidate whose base follows, or
                 whose S is followed by, another control goes back to its
                 box (rule I1). Before an insertable S, the candidate takes
                 the shape of S.
     2. shrink   a bird before a candidate and a sign that it can only take
                 smaller (rule I4) becomes its shrunk glyph.
     3. zone     the candidate gets the zone of B for its corner and shape:
                 a height and a width marker after it, from one class
                 definition of bases per corner and shape (rule I2).
     4. level    S becomes its variant at the first of INSERT_LEVELS and
                 goes one level down while it is wider or higher than the
                 zone; past the last level it is lone again (rule I3). A
                 marker after it ends the block.
     5. mark     the zone markers become one; before a variant, the
                 candidate becomes the mark of its corner, shape and the
                 variant's width in units, which hangs from B (rule I5); any other
                 candidate becomes a horizontal joiner (rule I6).
     6. cluster  B and the marker after S make a ligature (B again), so B,
                 C and S are one cluster.
    """
    i = n.inserts
    corners, shapes = list(L.CORNERS), i.shapes
    cands = [i.candidate(c) for c in corners]
    controls = cls(control_name(c) for c in corners)
    cand = w.define("I_CAND", cands)
    shaped = w.define("I_SHAPED", [i.shaped(c, s) for c in corners for s in shapes])
    others = w.define("I_CONTROLS", [control_name(c) for c in CONTROLS] + i.candidates())
    insertable = w.define("I_INS", [n.lone(c) for c in i.insertable])
    zw = w.define("I_ZW", [i.zone_width(x) for x in i.widths])
    zh = w.define("I_ZH", [i.zone_height(x) for x in i.heights])

    # 1. check
    w.lookup("ins_to_cand", [f"sub {control_name(c)} by {i.candidate(c)}" for c in corners])
    w.lookup("ins_undo", [f"sub {i.candidate(c)} by {control_name(c)}" for c in corners])
    w.lookup("ins_check", [f"ignore sub {ign} {controls}'", f"ignore sub {controls}' {ign}",
                           f"sub {lone} {controls}' lookup ins_to_cand {lone}"], table="gsub")
    w.lookup("ins_alone_before", [f"ignore sub {others} {ign} {lone} {cand}'",
                                  f"sub {others} {lone} {cand}' lookup ins_undo"], table="gsub")
    w.lookup("ins_alone_after", [f"ignore sub {cand}' {lone} {ign} {others}",
                                 f"sub {cand}' lookup ins_undo {lone} {others}"], table="gsub")
    rules = []
    for s in shapes:
        w.lookup(f"ins_to_{s}", [f"sub {i.candidate(c)} by {i.shaped(c, s)}" for c in corners])
        rules.append(f"sub {cand}' lookup ins_to_{s} {cls(n.lone(c) for c in i.insertable if i.shape[c] == s)}")
    w.lookup("ins_shape", rules, table="gsub")

    # 2. shrink: the birds and signs for which layout.insertion() says so
    if i.shrinks:
        for level in L.SHRINK_LEVELS:
            w.lookup(f"ins_shrink_{level}", [f"sub {n.lone(c)} by {i.shrunk(c, k)}"
                                              for c, k in i.shrunk_glyphs if k == level])
        rules = [f"sub {n.lone(b)}' lookup ins_shrink_{level} {cls(i.shaped(control, s) for s in shapes)} "
                 f"{cls(n.lone(c) for c in sorted(found))}"
                 for (b, control, level), found in sorted(i.shrinks.items())]
        w.lookup("ins_shrink", rules, table="gsub")

    # 3. zone: the width, then the height, each a rule per corner, shape
    # and size; the height marker ends up first
    for part, sizes, marker in ((0, i.widths, i.zone_width), (1, i.heights, i.zone_height)):
        name = ("ins_zone_width", "ins_zone_height")[part]
        for x in sizes:
            w.lookup(f"{name}_{x}", [f"sub {c} by {c} {marker(x)}" for c in i.candidates()[len(cands):]])
        found = defaultdict(list)
        for (base, level, control, shape), zone in sorted(i.zones.items()):
            found[(control, shape, zone[part])].append(i.base(base, level))
        w.lookup(name, [f"sub {cls(bases)} {i.shaped(control, shape)}' lookup {name}_{x}"
                        for (control, shape, x), bases in sorted(found.items())], table="gsub", extension=True)

    # 4. level: from the first insert level down, one lookup per level
    first, last = L.INSERT_LEVELS[0], L.INSERT_LEVELS[-1]
    w.lookup("ins_first", [f"sub {n.lone(c)} by {n.variant(c, first)} {i.cluster_end}" for c in i.insertable])
    w.lookup("ins_start", [f"sub {shaped} {zh} {zw} {insertable}' lookup ins_first"], table="gsub")
    for k in L.INSERT_LEVELS:
        after = [n.variant(c, k + 1) if k < last else n.lone(c) for c in i.insertable]
        w.lookup(f"ins_next_{k}", [f"sub {n.variant(c, k)} by {a}" for c, a in zip(i.insertable, after)])
        # wider than the zone: the width marker before the variant
        found = defaultdict(list)
        for c in i.insertable:
            found[i.size[(c, k)][0]].append(n.variant(c, k))
        rules = [f"sub {cls(i.zone_width(x) for x in i.widths if x < a)} {cls(found[a])}' lookup ins_next_{k}"
                 for a in sorted(found) if a > i.widths[0]]
        # higher than the zone: the height marker, then the width marker
        found = defaultdict(list)
        for c in i.insertable:
            found[i.size[(c, k)][1]].append(n.variant(c, k))
        rules += [f"sub {cls(i.zone_height(y) for y in i.heights if y < b)} {zw} {cls(found[b])}' "
                  f"lookup ins_next_{k}" for b in sorted(found) if b > i.heights[0]]
        w.lookup(f"ins_level_{k}", rules, table="gsub")

    # 5. mark
    w.lookup("ins_zone_done", [f"sub {i.zone_height(y)} {i.zone_width(x)} by {i.zone_done}"
                               for y in i.heights for x in i.widths], table="gsub")
    rules = []
    for shape, size in i.mark_sizes:
        variants = [n.variant(c, k) for c in i.insertable for k in L.INSERT_LEVELS
                    if i.shape[c] == shape and L.seat_width(i.size[(c, k)]) == size]
        rules.append(f"rsub {cls(i.shaped(c, shape) for c in corners)}' {i.zone_done} {cls(variants)} "
                     f"by {cls(i.mark(c, shape, size) for c in corners)}")
    w.lookup("ins_mark", rules, table="gsub")
    hj = control_name(L.HORIZONTAL_JOINER)
    w.lookup("ins_joiner_zone", [f"sub {c} {i.zone_done} by {hj}" for c in i.candidates()[len(cands):]],
             table="gsub")
    w.lookup("ins_joiner", [f"sub {cls(i.candidates())} by {hj}"], table="gsub")

    # 6. cluster: every base that takes a sign somewhere
    bases = sorted({i.base(base, level) for base, level, _, _ in i.zones})
    w.lookup("ins_cluster", [f"sub {b} {i.cluster_end} by {b}" for b in bases],
             w.define("I_END", [i.cluster_end]), "gsub", extension=True)


def _gpos_insert(n, w):
    """Corner insertion: the corner mark hangs from the base at the anchor
    of its width (rule I5), in subtables by corner, shape and the narrowest
    and widest sign a base takes, so that a base has few empty anchors; the inserted sign hangs from the corner mark by the centre of the
    bottom of its ink, which is its variant's origin. Returns the lookups,
    mark to base first."""
    i = n.inserts
    for control in L.CORNERS:
        for shape, size in i.mark_sizes:
            w.text.append(f"markClass {i.mark(control, shape, size)} <anchor 0 0> @I_{control:X}_{shape}_{size};")
    groups = defaultdict(list)
    for key, sizes in sorted(i.anchors.items()):
        groups[(key[2], key[3], min(sizes), max(sizes))].append(key)
    rules = []
    for (control, shape, *_), keys in sorted(groups.items()):
        if rules:
            rules.append("subtable")
        for key in keys:
            base, level = key[:2]
            zone, lift = i.zones[key], n.signs[base].lift
            anchors = " ".join(f"<anchor {zone.x} {zone.seats[size - 1] + lift}> mark @I_{control:X}_{shape}_{size}"
                               for size in sorted(i.anchors[key]))
            rules.append(f"pos base {i.base(base, level)} {anchors}")
    w.lookup("ins_place", rules)
    variants = [n.variant(c, k) for c in i.insertable for k in L.INSERT_LEVELS]
    w.text.append(f"markClass {cls(variants)} <anchor 0 0> @I_SIGN;")
    marks = i.corner_marks()
    w.lookup("ins_sign_place", [f"pos mark {cls(marks)} <anchor 0 0> mark @I_SIGN"],
             w.define("I_PLACE", marks + variants))
    return ["ins_place", "ins_sign_place"]


def categories(font, names, automatic):
    """GDEF glyph classes, in the form of public.openTypeCategories.

    The Latin letters and marks arrive with their own classes. Every sign
    and control is a base, also U+13440, which Unicode calls a mark: HarfBuzz
    removes the advance of a mark, and the fallback would cover the next sign.
    The group heads are bases, the rest of what the generator adds is marks.
    """
    bases = {glyph.name for glyph in font
             if any(u in SIGNS or u == DOTTED_CIRCLE for u in glyph.unicodes)}
    bases |= {*names.joined.values(), *names.heads(), *names.inserts.bases()}
    marks = set(names.markers()) | set(names.inserts.markers()) | set(automatic.markers())
    for level in LEVELS:
        marks |= set(names.leveled(level))
    found = {name: "base" for name in bases}
    found.update({name: "mark" for name in marks})
    return dict(sorted(found.items()))


def add_features(font, names, automatic):
    w = Writer()
    w.text += [f"languagesystem {script} {language};" for script, language in SYSTEMS]
    modifiers = _gsub_modifiers(names, w)  # first in the lookup list: folds the modifiers
    auto = _gsub_auto(names, w, automatic)
    _gsub(names, w)
    modifiers_late = _gsub_modifiers_late(names, w)  # after the stacking lookups
    _gpos(names, w)

    def feature(tag, lookups, automatic=False):
        # ufo2ft puts the Latin mark rules at "# Automatic Code", for every
        # script; the stacking lookups are registered for SYSTEMS only
        body = ["    # Automatic Code"] if automatic else []
        for script, language in SYSTEMS:
            body += [f"    script {script};", f"    language {language};"]
            body += [f"    lookup {name};" for name in lookups]
        return [f"feature {tag} {{", *body, f"}} {tag};"]

    inserts = _gpos_insert(names, w)
    mirrored_bases = _gpos_mirrored_bases(names, w)  # moved before the inserted signs hang from them
    hatch = _gpos_modifiers(names, w)  # last: the shading hangs from the placed signs
    w.text += feature("calt", modifiers + auto)
    w.text += feature("rlig", modifiers + w.gsub + modifiers_late)
    w.text += feature("mark", w.gpos[:1] + mirrored_bases + inserts[:1] + hatch[:1], automatic=True)
    w.text += feature("mkmk", w.gpos[1:] + inserts[1:] + hatch[1:], automatic=True)
    font.lib["public.openTypeCategories"] = categories(font, names, automatic)
    font.lib["public.openTypeCategories"].update(modifier_categories(names))
    font.features.text = "\n".join(w.text) + "\n"


# --- Sign modifiers (layout section 8) ----------------------------------------

def _gsub_modifiers(n, w):
    """Mirroring and damage, first part: before the automatic layer and the
    stacking lookups, in calt and rlig. S is a hieroglyph's lone glyph, M
    the mirror control, D a damage modifier, as typed.

     1. find     S followed by M or D (any ignorable but ZWJ and ZWNJ
                 between: HarfBuzz skips those the rules do not name) gets
                 the marker _mk after it (rule M1).
     2. fold     _mk and the modifiers after it become one glyph by
                 ligature (_mir, _dm.q or _md.q), so that they are one
                 cluster with S; an M or D that no ligature takes keeps its
                 box (rule M3). From here on these glyphs are of the
                 ligature class, which every lookup of the stacking ignores.
     3. symmetric  after a symmetric sign, the mirror is dropped (rule M4).
     4. swap     a corner control after a mirrored sign is swapped, start
                 for end (rule M5).
     5. size     _md.q becomes _mir _dm.q; _dm.q gets the cell width and
                 height of S as two markers (rule M6).
    """
    m = n.modifiers
    mirror = control_name(L.MIRROR)
    sign = w.define("M_SIGN", [n.lone(c) for c in m.hieroglyphs])
    damage = w.define("M_DAMAGE", [m.stray(c) for c in L.DAMAGE])
    breaks = w.define("M_BREAK", [g for g in n.ignorables if g != ".notdef"])  # ZWJ, ZWNJ
    damaged = w.define("M_DM", [m.damaged(q) for q in m.quarters])
    both = w.define("M_MD", [m.both(q) for q in m.quarters])
    lookups = []

    def lookup(name, rules, **kwargs):
        w.lookup(name, rules, flags="", **kwargs)
        lookups.append(name)

    # 1. find
    w.lookup("mod_mark", [f"sub {n.lone(c)} by {n.lone(c)} {m.marker}" for c in m.hieroglyphs], flags="")
    lookup("mod_find", [f"ignore sub {sign}' {breaks}", f"sub {sign}' lookup mod_mark [{mirror} {damage}]"])
    # 2. fold
    w.lookup("mod_fold_mirror", [f"sub {m.marker} {mirror} by {m.mirror}"], flags="")
    w.lookup("mod_fold_all", [f"sub {m.marker} {mirror} {m.stray(c)} by {m.both(L.quadrants(c))}" for c in L.DAMAGE]
             + [f"sub {m.marker} {mirror} by {m.mirror}"]
             + [f"sub {m.marker} {m.stray(c)} by {m.damaged(L.quadrants(c))}" for c in L.DAMAGE], flags="")
    lookup("mod_fold", [f"sub {m.marker}' lookup mod_fold_mirror {mirror}' {breaks}",
                        f"sub {m.marker}' lookup mod_fold_all {mirror}' {damage}'",
                        f"sub {m.marker}' lookup mod_fold_mirror {mirror}'",
                        f"sub {m.marker}' lookup mod_fold_all {damage}'"])
    # 3. symmetric
    symmetric = w.define("M_SYM", [n.lone(c) for c in m.symmetric])
    w.lookup("mod_drop_mirror", [f"sub {m.mirror} by NULL"], flags="")
    w.lookup("mod_unmirror", [f"sub {m.both(q)} by {m.damaged(q)}" for q in m.quarters], flags="")
    lookup("mod_symmetric", [f"sub {symmetric} {m.mirror}' lookup mod_drop_mirror",
                             f"sub {symmetric} {both}' lookup mod_unmirror"])
    # 4. swap, after a bird; after another sign the corner control becomes
    # an unsupported control (the mirror control's glyph)
    pairs = [(c, L.SWAPPED[c]) for c in sorted(L.SWAPPED)]
    corners = cls(control_name(a) for a, _ in pairs)
    birds = cls(n.lone(c) for c in m.mirrored if c in L.MIRRORED_BASES)
    others = cls(n.lone(c) for c in m.mirrored if c not in L.MIRRORED_BASES)
    w.lookup("mod_swap_corner", [f"sub {control_name(a)} by {control_name(b)}" for a, b in pairs], flags="")
    w.lookup("mod_no_corner", [f"sub {corners} by {mirror}"], flags="")
    lookup("mod_swap", [f"sub {birds} [{m.mirror} {both}] {corners}' lookup mod_swap_corner",
                        f"sub {others} [{m.mirror} {both}] {corners}' lookup mod_no_corner"])
    # 5. size
    lookup("mod_split", [f"sub {m.both(q)} by {m.mirror} {m.damaged(q)}" for q in m.quarters])
    lookup("mod_size", [f"sub {m.damaged(q)} by {m.damaged(q)} {m.width(0)} {m.height(0)}" for q in m.quarters])
    rules = []
    for a in m.cell_widths:
        w.lookup(f"mod_width_{a}", [f"sub {m.width(0)} by {m.width(a)}"], flags="")
        signs = cls(n.lone(c) for c in m.hieroglyphs if n.signs[c].cell[0] == a)
        rules += [f"sub {signs} {damaged} {m.width(0)}' lookup mod_width_{a}",
                  f"sub {signs} {m.mirror} {damaged} {m.width(0)}' lookup mod_width_{a}"]
    lookup("mod_widths", rules)
    widths = cls(m.width(a) for a in m.cell_widths)
    rules = []
    for b in m.cell_heights:
        w.lookup(f"mod_height_{b}", [f"sub {m.height(0)} by {m.height(b)}"], flags="")
        signs = cls(n.lone(c) for c in m.hieroglyphs if n.signs[c].cell[1] == b)
        rules += [f"sub {signs} {damaged} {widths} {m.height(0)}' lookup mod_height_{b}",
                  f"sub {signs} {m.mirror} {damaged} {widths} {m.height(0)}' lookup mod_height_{b}"]
    lookup("mod_heights", rules)
    return lookups


def _gsub_modifiers_late(n, w):
    """Mirroring and damage, second part: after the stacking lookups, when
    each sign is its lone glyph, its variant at its level or a shrunk bird.

     1. mirror   the glyph before _mir (other marks between are skipped)
                 becomes its mirrored glyph; _mir goes (rule M4).
     2. tiles    from the level of that glyph, the cell's width and height
                 become the quarter's size in tiles, then one glyph (M7).
     3. pieces   for each quarter of _dm.q, a piece of shading after the
                 size, in the order of the bits (rule M7).
     4. clean    the markers go; deleted glyphs leave their cluster to the
                 glyph before them, which is the sign's.
    """
    m, i = n.modifiers, n.inserts
    hiero = set(m.hieroglyphs)
    variants = {k: [n.variant(c, k) for c in m.hieroglyphs] + [m.variant(c, k) for c in m.mirrored if k in m.levels]
                for k in LEVELS}
    every = w.define("M_VARIANTS", [g for k in LEVELS for g in variants[k]])
    lone = [n.lone(c) for c in m.hieroglyphs] + [m.lone(c) for c in m.mirrored]
    shrunk = {k: [i.shrunk(c, kk) for c, kk in i.shrunk_glyphs if kk == k and c in hiero]
              + [m.shrunk_glyph(c, kk) for c, kk in m.shrunk if kk == k] for k in L.SHRINK_LEVELS}
    damaged = w.define("M_DM2", [m.damaged(q) for q in m.quarters])
    lookups = []

    def lookup(name, rules, **kwargs):
        w.lookup(name, rules, flags="", **kwargs)
        lookups.append(name)

    # 1. mirror
    w.lookup("mod_mirror_variant", [f"sub {n.variant(c, k)} by {m.variant(c, k)}"
                                    for k in m.levels for c in m.mirrored], flags="")
    w.lookup("mod_mirror_lone", [f"sub {n.lone(c)} by {m.lone(c)}" for c in m.mirrored]
             + [f"sub {i.shrunk(c, k)} by {m.shrunk_glyph(c, k)}" for c, k in m.shrunk], flags="")
    mirrorable = cls(n.variant(c, k) for k in m.levels for c in m.mirrored)
    lone_mirrorable = cls([n.lone(c) for c in m.mirrored] + [i.shrunk(c, k) for c, k in m.shrunk])
    lookup("mod_mirror", [f"sub {mirrorable}' lookup mod_mirror_variant {m.mirror}' lookup mod_drop_mirror",
                          f"sub {lone_mirrorable}' lookup mod_mirror_lone {m.mirror}' lookup mod_drop_mirror"],
           marks=every)
    lookup("mod_mirror_box", [f"sub {m.mirror} by {m.mirror_box}"])  # rule M8: a level without mirrored glyphs
    # 2. tiles: the glyph before gives the level
    contexts = [(cls(variants[k]), k) for k in LEVELS] + [(cls(lone), 0)]
    contexts += [(cls(shrunk[k]), k) for k in L.SHRINK_LEVELS if shrunk[k]]
    for name, sizes, marker, step, tiles_name, before in (
            ("across", m.cell_widths, m.width, L.half_unit, m.across_tiles, ""),
            ("up", m.cell_heights, m.height, L.unit, m.up_tiles, cls(m.across_tiles(v) for v in m.across) + " ")):
        values = m.across if name == "across" else m.up
        for v in values:
            w.lookup(f"mod_{name}_{v}", [f"sub {cls(marker(a) for a in sizes)} by {tiles_name(v)}"], flags="")
        rules = []
        for context, k in contexts:
            found = defaultdict(list)
            for a in sizes:
                found[L.tiles(a * step(k))].append(marker(a))
            rules += [f"sub {context} {damaged} {before}{cls(found[v])}' lookup mod_{name}_{v}" for v in sorted(found)]
        lookup(f"mod_{name}", rules, marks=every)
    lookup("mod_tiles", [f"sub {m.across_tiles(v)} {m.up_tiles(u)} by {m.size(v, u)}" for v, u in m.sizes])
    # 3. pieces, the last quarter first: each goes right after the size
    sizes = cls(m.size(v, u) for v, u in m.sizes)
    for q in reversed(L.QUADRANTS):
        w.lookup(f"mod_add_{q}", [f"sub {m.size(v, u)} by {m.size(v, u)} {m.piece(q, v, u)}" for v, u in m.sizes],
                 flags="")
        lookup(f"mod_pieces_{q}", [f"sub {cls(m.damaged(x) for x in m.quarters if x & q)} {sizes}' lookup mod_add_{q}"])
    # 4. clean
    lookup("mod_clean", [f"sub {g} by NULL" for g in m.markers()])
    return lookups


def _gpos_mirrored_bases(n, w):
    """A mirrored base of a corner insertion: the corner mark hangs from it
    where it hangs from the sign, mirrored across the middle of the ink
    (rule M5: the control was swapped). As in _gpos_insert(), in subtables
    by corner, shape and the narrowest and widest sign."""
    m, i = n.modifiers, n.inserts
    mirrored = set(m.mirrored) & set(L.MIRRORED_BASES)
    groups = defaultdict(list)
    for key, sizes in sorted(i.anchors.items()):
        if key[0] in mirrored:
            groups[(key[2], key[3], min(sizes), max(sizes))].append(key)
    rules = []
    for _, keys in sorted(groups.items()):
        if rules:
            rules.append("subtable")
        for base, level, control, shape in keys:
            sign, zone = n.signs[base], i.zones[(base, level, control, shape)]
            x = sign.box[0] + sign.box[2] - zone.x
            glyph = m.lone(base) if not level else m.shrunk_glyph(base, level)
            anchors = " ".join(f"<anchor {x} {zone.seats[size - 1] + sign.lift}> mark @I_{control:X}_{shape}_{size}"
                               for size in sorted(i.anchors[(base, level, control, shape)]))
            rules.append(f"pos base {glyph} {anchors}")
    start = len(w.text)
    w.lookup("mod_insert_place", rules)
    # its place in the lookup list: right before ins_place, after the mark
    # classes it uses, so that CoreText (which applies attachments in lookup
    # order) places the corner mark before the inserted sign hangs from it
    block = w.text[start:]
    del w.text[start:]
    at = w.text.index("lookup ins_place {")
    w.text[at:at] = block
    return ["mod_insert_place"]


def _gpos_modifiers(n, w):
    """A mirrored inserted sign hangs from its corner mark as the sign does;
    the pieces of shading hang from the middle of their cell (rule M6): from
    a lone sign or a shrunk bird (mark to base, at the middle of the cell
    around its ink), from a variant (mark to mark, at the middle of the cell
    above its origin), or from the piece before them. Returns the lookups,
    mark to base first."""
    m, i = n.modifiers, n.inserts
    inserted = [m.variant(c, k) for c in i.insertable for k in L.INSERT_LEVELS
                if k in m.levels and c in set(m.mirrored)]
    w.text.append(f"markClass {cls(inserted)} <anchor 0 0> @M_I_SIGN;")
    marks = i.corner_marks()
    w.lookup("mod_insert_sign_place", [f"pos mark {cls(marks)} <anchor 0 0> mark @M_I_SIGN"],
             w.define("M_I_PLACE", marks + inserted))
    pieces = m.pieces() + [m.mirror_box]  # the box of rule M8 hangs where the pieces do
    w.text.append(f"markClass {cls(pieces)} <anchor 0 0> @M_HATCH;")
    bases = defaultdict(list)
    for c in m.hieroglyphs:
        sign = n.signs[c]
        x, y = L.lone_middle(sign)
        bases[(x, y + L.damage_size(sign, 0)[2])] += [n.lone(c)] + ([m.lone(c)] if c in set(m.mirrored) else [])
    for c, k in i.shrunk_glyphs:
        if c in set(m.hieroglyphs):
            sign = n.signs[c]
            x, y = L.lone_middle(sign)
            bases[(x, y + L.damage_size(sign, k)[2])] += [i.shrunk(c, k)] + (
                [m.shrunk_glyph(c, k)] if (c, k) in set(m.shrunk) else [])
    w.lookup("mod_hatch_base", [f"pos base {cls(names)} <anchor {x} {y}> mark @M_HATCH"
                                for (x, y), names in sorted(bases.items())])
    middles = defaultdict(list)
    for k in LEVELS:
        for c in m.hieroglyphs:
            middles[L.damage_size(n.signs[c], k)[2]] += [n.variant(c, k)] + m.mirrored_variants(c, k)
    rules = [f"pos mark {cls(names)} <anchor 0 {y}> mark @M_HATCH" for y, names in sorted(middles.items())]
    rules.append(f"pos mark {cls(pieces)} <anchor 0 0> mark @M_HATCH")
    w.lookup("mod_hatch_mark", rules, w.define("M_HATCH_ON", [g for names in middles.values() for g in names] + pieces))
    return ["mod_hatch_base", "mod_insert_sign_place", "mod_hatch_mark"]


def modifier_categories(names):
    """GDEF classes of the glyphs of the sign modifiers."""
    m = names.modifiers
    found = {name: "base" for name in m.bases()}
    found.update({name: "mark" for name in m.marks()})
    found.update({name: "ligature" for name in m.markers()})
    return found
