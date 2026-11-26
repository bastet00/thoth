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

    def lookup(self, name, rules, marks=None, table=None, extension=False):
        """A lookup; marks: its mark filtering set; table: "gsub" or "gpos"
        if a feature applies it (else it is only called by other lookups);
        extension: stored as an extension lookup, at the end of its table."""
        flag = [f"    lookupflag UseMarkFilteringSet {marks};"] if marks else []
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

    # 1. words, 2. slots. Inserting a glyph takes a rule per sign, so there
    # are two such lookups, a mark before the sign and one after it; a word
    # end goes in as a slot, which auto_end turns into the end before any
    # other slot is there
    for name, output in (("auto_start_mark", "{a} {s}"), ("auto_slot_mark", "{s} {c}")):
        w.lookup(name, [f"sub {n.lone(c)} by " + output.format(a=auto.start, c=auto.slot, s=n.lone(c))
                        for c in signs])
    w.lookup("auto_starts", [f"sub {ign} {sign}' lookup auto_start_mark", f"ignore sub [{sign} {ctrl}] {sign}'",
                             f"sub {sign}' lookup auto_start_mark"])
    w.lookup("auto_ends", [f"sub {sign}' lookup auto_slot_mark {ign}", f"ignore sub {sign}' [{sign} {ctrl}]",
                           f"sub {sign}' lookup auto_slot_mark"])
    w.lookup("auto_end", [f"sub {auto.slot} by {auto.end}"])
    w.lookup("auto_slots", [f"sub {sign}' lookup auto_slot_mark {sign}"])
    lookups += ["auto_starts", "auto_ends", "auto_end", "auto_slots"]

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


def _gpos(n, w, extra_cells=()):
    """extra_cells: (glyph, enter or None, leave) of other glyphs in the
    chain of cells (the boxes of segments and overlay, nest_cells())."""
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
    for name, x_in, x_out in extra_cells:
        if x_in is not None:
            enter[x_in].append(name)
        leave[x_out].append(name)
    for x, names in sorted(enter.items()):
        w.text.append(f"markClass {cls(names)} <anchor {x} 0> @mCELL;")
    rules = [f"pos mark {cls(name for name, _ in lefts)} <anchor 0 0> mark @mCELL"]
    rules += [f"pos mark {cls(names)} <anchor {x} 0> mark @mCELL" for x, names in sorted(leave.items())]
    members = [name for name, _ in lefts] + [x for names in enter.values() for x in names]
    members += [name for name, x_in, _ in extra_cells if x_in is None]
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
        # the birds that shrink to the same level before the same corner and
        # signs share a rule (a subtable each). A bird and corner shrink to
        # one level for any one sign, so no two rules match the same text
        # and their order does not matter
        birds = defaultdict(list)
        for (b, control, level), found in sorted(i.shrinks.items()):
            birds[(control, level, tuple(sorted(found)))].append(b)
        rules = [f"sub {cls(n.lone(b) for b in bs)}' lookup ins_shrink_{level} "
                 f"{cls(i.shaped(control, s) for s in shapes)} {cls(n.lone(c) for c in found)}"
                 for (control, level, found), bs in birds.items()]
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
    auto = _gsub_auto(names, w, automatic)  # first in the lookup list
    nest, sides = G.Nesting(names.signs), G.SideInserts(names.signs)
    w.gsub += _gsub_side(names, w, sides)  # before the flat stages (layout section 9)
    w.gsub += _gsub_nest(names, w, nest)  # before the flat stages (layout section 8)
    _gsub(names, w)
    _splice(w, "unstack_signs", lambda part: _gsub_nest_fallback(names, part, nest))
    w.gsub += _gsub_nest_level(names, w, nest)
    _gpos(names, w, nest_cells(nest))
    nested = []
    _splice(w, "place_cells", lambda part: nested.extend(_gpos_nest(names, part, nest)) or nested, table="gpos")

    def feature(tag, lookups, automatic=False):
        # ufo2ft puts the Latin mark rules at "# Automatic Code", for every
        # script; the stacking lookups are registered for SYSTEMS only
        body = ["    # Automatic Code"] if automatic else []
        for script, language in SYSTEMS:
            body += [f"    script {script};", f"    language {language};"]
            body += [f"    lookup {name};" for name in lookups]
        return [f"feature {tag} {{", *body, f"}} {tag};"]

    inserts = _gpos_insert(names, w)
    side = _gpos_side(names, w, sides)
    w.text += feature("calt", auto)
    w.text += feature("rlig", w.gsub)
    w.text += feature("mark", w.gpos[:1] + inserts[:1] + side[:1], automatic=True)
    w.text += feature("mkmk", w.gpos[1:] + inserts[1:] + nested + side[1:], automatic=True)
    font.lib["public.openTypeCategories"] = categories(font, names, automatic)
    font.lib["public.openTypeCategories"].update({**nest_categories(nest), **side_categories(sides)})
    font.features.text = "\n".join(w.text) + "\n"


# --- Segments and overlay (layout section 8) ---------------------------------
#
# Three parts, all in rlig:
#
#  A. before the flat stages (_gsub_nest): a run with a segment or overlay
#     control is checked and its boxes are computed from the inside out, so
#     that the flat stages see each box as one cell (_cw, _ch) of its row:
#      1. flood    the controls of such a run become pending and its signs
#                  their level-0 variants (marks), left and right from the
#                  segment and overlay controls, up to two signs in a row,
#                  an ignorable or other text (layout.runs()); an empty base,
#                  the run start, goes before each such run, so that the
#                  marks of one run never see those of another.
#      2. flat     the brackets and joiners of an overlay's operands are
#                  told apart from those of segments (by the overlay control
#                  next to them).
#      3. check    the automaton of glyphs.nest_step() runs left to right:
#                  each control becomes its type and the state after it, or
#                  dead; a control that ends its run in a state that does
#                  not accept dies. A run with a dead control is drawn as
#                  before (its run start sees the dead control: lone signs
#                  and boxes); the controls of the others become tokens by
#                  role and depth.
#      4. stages   for each depth from the deepest: each box gets a head
#                  (its width and height, where its layers hang) and each row
#                  a head (width, height, a carrier), each sign of the box
#                  its cell width and height; folds right to left as in the
#                  flat stages give rows, layers and boxes their sizes; a box
#                  over BOX_LIMIT makes its run fall back; a segment's rows
#                  of two are justified (a spacer after the joiner); then the
#                  box becomes, for its own row, a cell (width, height) and
#                  the glyph that stands in that cell (Xv), and a box end
#                  (E) after its last sign; the rows of a box tell their
#                  height to the segments in them (their slot). The box is
#                  one cluster (a ligature from its start to its end).
#      5. stage 0  the rows of the group itself tell their height to the
#                  segments in them; the group's tokens become the joiners
#                  as the flat stages know them, its signs lone signs again.
#  B. after the fallback of the flat stages: a group over the caps gives
#     its boxes back as lone signs and boxes (_gsub_nest_fallback).
#  C. after the flat stages: Xv, the rows and the layers of every box take
#     the level of their group (_gsub_nest_level).
#
# GPOS: Xv is a cell of the flat chain (place_cells); a layer's top and
# bottom hang from Xv, its rows from them, each row's left edge (the shared
# row-left glyphs) from its row, its signs from that as in a flat row; E
# hangs from the right edge of Xv, and the next cell of the outer row from
# E. Positions in an inner box are therefore found by HarfBuzz from the last
# attachment of each glyph (a later lookup overrides an earlier one).

import glyphs as G  # noqa: E402  (the automaton and the role of each control)


def _nest_classes(n, nest, w):
    signs = sorted(n.signs)
    return {
        "lone": [n.lone(c) for c in signs],
        "var": [n.variant(c, 0) for c in signs],
        "raw": [control_name(c) for c in CONTROLS],
        "pending": [nest.pending(c) for c in CONTROLS] + [nest.flat(t) for t in ("Bf", "Hf", "Ef", "Bg", "Vg", "Eg")],
        "tagged": [nest.tagged(t, s) for t, s in nest.checked],
        "dead": [nest.dead(c) for c in CONTROLS],
    }


def _nest_pending(nest, token):
    if token in ("V", "H", "B", "E", "O"):
        return nest.pending(G.TYPE_CONTROL[token])
    return nest.flat(token)


def _gsub_nest(n, w, nest):
    """Part A. Returns the lookups, in order."""
    c = _nest_classes(n, nest, w)
    lone, var, raw = (w.define(f"N_{k.upper()}", c[k]) for k in ("lone", "var", "raw"))
    pend, dead = w.define("N_PEND", c["pending"]), w.define("N_DEAD", c["dead"])
    tagged = w.define("N_TAGGED", c["tagged"])
    ign = w.define("N_IGN", n.ignorables)
    seeds = cls(control_name(x) for x in L.NESTING)
    flooded = w.define("N_FLOODED", c["pending"] + c["var"])
    lookups = []

    # 1. flood
    w.lookup("n_to_pending", [f"sub {control_name(x)} by {nest.pending(x)}" for x in CONTROLS])
    w.lookup("n_to_var", [f"sub {lone} by {var}"])
    w.lookup("n_to_lone", [f"sub {var} by {lone}"])
    w.lookup("n_flood_right", [f"ignore sub {ign} [{lone} {raw}]'", f"ignore sub {var} {lone}'",
                               f"sub {flooded} {lone}' lookup n_to_var",
                               f"sub {flooded} {raw}' lookup n_to_pending",
                               f"sub {seeds}' lookup n_to_pending"])
    pending_of = cls(nest.pending(x) for x in CONTROLS)
    w.lookup("n_flood_left", [f"rsub {lone}' {ign} by {lone}", f"rsub {raw}' {ign} by {raw}",
                              f"rsub {lone}' {var} by {lone}",
                              f"rsub {lone}' {flooded} by {var}",
                              f"rsub {raw}' {flooded} by {pending_of}"])
    w.lookup("n_rs", [f"sub {g} by {nest.run_start} {g}" for g in c["pending"] + c["var"]])
    w.lookup("n_run_start", [f"sub {ign} {flooded}' lookup n_rs", f"sub {var} {var}' lookup n_rs",
                             f"ignore sub {flooded} {flooded}'", f"sub {flooded}' lookup n_rs"])
    lookups += ["n_flood_right", "n_flood_left", "n_run_start"]

    # 2. flat: the operands of an overlay
    p = {t: _nest_pending(nest, t) for t in G.SEG_TYPES}
    w.lookup("n_flat_left", [f"rsub {p['E']}' {p['O']} by {p['Ef']}",
                             f"rsub {p['H']}' {var} [{p['Ef']} {p['Hf']}] by {p['Hf']}",
                             f"rsub {p['B']}' {var} {p['Hf']} by {p['Bf']}"])
    for t in ("Bg", "Vg", "Eg"):
        w.lookup(f"n_to_{t}", [f"sub {p[t[0]]} by {p[t]}"])
    w.lookup("n_flat_right", [f"sub {p['O']} {p['B']}' lookup n_to_Bg",
                              f"sub [{p['Bg']} {p['Vg']}] {var} {p['V']}' lookup n_to_Vg",
                              f"sub {p['Vg']} {var} {p['E']}' lookup n_to_Eg"])
    lookups += ["n_flat_left", "n_flat_right"]

    # 3. check: one lookup per state maps a pending control to its next state
    def step_rules(state):
        rules = []
        for cp in CONTROLS:
            name = nest.pending(cp)
            types = [t for t in ("V", "H", "B", "E", "O") if G.TYPE_CONTROL[t] == cp]
            found = G.nest_step(state, types[0]) if types else G.DEAD
            rules.append(f"sub {name} by " + (nest.dead(cp) if found == G.DEAD
                                              else nest.tagged(types[0], nest.index[found])))
        for t in ("Bf", "Hf", "Ef", "Bg", "Vg", "Eg"):
            found = G.nest_step(state, t)
            rules.append(f"sub {nest.flat(t)} by " + (nest.dead(G.TYPE_CONTROL[t]) if found == G.DEAD
                                                      else nest.tagged(t, nest.index[found])))
        return rules

    dead_of = {nest.pending(x): nest.dead(x) for x in CONTROLS}
    dead_of.update({nest.flat(t): nest.dead(G.TYPE_CONTROL[t]) for t in ("Bf", "Hf", "Ef", "Bg", "Vg", "Eg")})
    w.lookup("n_step_dead", [f"sub {g} by {dead_of[g]}" for g in c["pending"]])
    for state, i in nest.index.items():
        w.lookup(f"n_step_{i}", step_rules(state))
    by_state = defaultdict(list)  # state: the checked controls with that state after them
    for t, s in nest.checked:
        by_state[s].append(nest.tagged(t, s))
    after_sign = defaultdict(list)  # state after a sign: the checked controls before it
    for t, s in nest.checked:
        found = G.nest_step(nest.states[s], "S")
        after_sign["dead" if found == G.DEAD else nest.index[found]].append(nest.tagged(t, s))
    rules = []
    start = nest.index[G.NEST_START]
    first = G.nest_step(G.NEST_START, "S")
    rules.append(f"sub {nest.run_start} {pend}' lookup n_step_{start}")
    rules.append(f"sub {nest.run_start} {var} {pend}' lookup n_step_{nest.index[first]}")
    rules.append(f"sub {dead} {pend}' lookup n_step_dead")
    rules.append(f"sub {dead} {var} {pend}' lookup n_step_dead")
    for s, names in sorted(by_state.items()):
        rules.append(f"sub {cls(names)} {pend}' lookup n_step_{s}")
    for s, names in sorted(after_sign.items(), key=lambda x: str(x[0])):
        rules.append(f"sub {cls(names)} {var} {pend}' lookup n_step_{s}")
    w.lookup("n_check", rules)
    # the end of a run: a control after which the run cannot end dies
    w.lookup("n_kill", [f"sub {g} by {nest.dead(G.TYPE_CONTROL[g.split('.')[1]])}" for g in c["tagged"]])
    ends_badly = [nest.tagged(t, s) for t, s in nest.checked if not G.nest_accepts(nest.states[s])]
    sign_ends_badly = [nest.tagged(t, s) for t, s in nest.checked
                       if not G.nest_accepts(G.nest_step(nest.states[s], "S"))]
    rules = [f"ignore sub {tagged}' [{tagged} {dead}]", f"ignore sub {tagged}' {var} [{tagged} {dead}]"]
    if sign_ends_badly:
        rules.append(f"sub {cls(sign_ends_badly)}' lookup n_kill {var}")
    rules.append(f"ignore sub {tagged}' {var}")
    if ends_badly:
        rules.append(f"sub {cls(ends_badly)}' lookup n_kill")
    w.lookup("n_end", rules)
    w.lookup("n_to_bad", [f"sub {nest.run_start} by {nest.bad_start}"])
    w.lookup("n_bad", [f"sub {nest.run_start}' lookup n_to_bad {dead}"], dead)
    lookups += ["n_check", "n_end", "n_bad"]
    lookups += _nest_revert(n, w, nest, c, "n_rv1", nest.bad_start, "check")
    roles = []
    for t, s in nest.checked:
        kind, depth = G.nest_role(t, nest.states[s])
        roles.append(f"sub {nest.tagged(t, s)} by {nest.token(kind, depth)}")
    w.lookup("n_roles", roles)
    lookups.append("n_roles")

    # 4. stages, from the deepest box
    _nest_cell_lookups(n, w, nest)
    for d in reversed(nest.depths):
        lookups += _nest_stage(n, w, nest, d, c)
    over = w.define("N_OVER", [nest.box_width(G.OVER), nest.box_height(G.OVER)])
    w.lookup("n_over", [f"sub {nest.run_start}' lookup n_to_bad {over}"], over)
    lookups.append("n_over")
    lookups += _nest_revert(n, w, nest, c, "n_rv2", nest.bad_start, "stages")

    # 5. stage 0
    lookups += _nest_stage0(n, w, nest, c)
    return lookups


def _nest_poisonable(n, nest, when):
    """The glyphs of this section that a run (or group) can hold at a
    point, but the signs: what a fallback there turns into dead controls or
    an empty glyph. when: "check" (after the automaton), "stages" (after
    the boxes), "flat" (in the fallback of the flat stages)."""
    checked = {nest.pending(c) for c in CONTROLS} | {nest.flat(t) for t in G.SEG_TYPES[5:]}
    checked |= {nest.tagged(t, s) for t, s in nest.checked}
    if when == "check":
        return sorted(checked)
    leveled = nest.leveled()
    finals = {x for names in leveled.values() for x in names}
    finals |= set(nest.verticals().values())
    found = set(nest.markers()) - {nest.poisoned} - {nest.dead(c) for c in CONTROLS} - checked - finals
    found |= {n.row_left(s, 0) for s in n.widths} | {n.spacer(d, 0) for d in n.slacks}
    if when == "stages":
        return sorted(found | {n.cell_width(a) for a in n.cell_widths} | {n.cell_height(b) for b in n.cell_heights})
    stage = {nest.cell_width(a) for a in nest.cell_widths()} | {nest.cell_height(b) for b in nest.heights()}
    stage |= {x for x in found if x.split(".")[0] in ("_nws", "_nhm", "_nrm", "_nrs", "_nrw", "_nrp", "_nrc",
                                                      "_nj", "_nbw", "_nbh", "_nls", "_nlo", "_nlq")}
    stage |= {nest.row_height0, nest.row_width0, nest.row_widtho, nest.row_carrier0, nest.box_width0,
              nest.box_height0, nest.box_end0, nest.layer_seg0, nest.layer_one0, nest.layer_two0}
    return sorted(found - stage)


def _nest_revert(n, w, nest, c, name, start, when, extra=()):
    """A run (or group) whose start is `start` is drawn as if it had no
    segment or overlay control: every control of this section becomes the
    control it was (dead first), every other glyph of it goes, every sign
    next to a control is lone again. `extra`: more glyphs the chain may
    cross (the markers of a flat group in fallback)."""
    poison, kinds = [], {}
    tokens = set(nest.tokens())
    poisonable = _nest_poisonable(n, nest, when)
    for g in poisonable:
        if g in tokens:
            kind = g[4:].rstrip("0123456789")
            poison.append(f"sub {g} by {nest.dead(G.TYPE_CONTROL[kind])}")
        elif g.startswith("_nd."):
            poison.append(f"sub {g} by {nest.dead(G.TYPE_CONTROL[g.split('.')[1]])}")
        elif g.startswith("_np."):
            kind = g[4:]
            cp = G.TYPE_CONTROL[kind] if kind in G.TYPE_CONTROL else int(kind, 16)
            poison.append(f"sub {g} by {nest.dead(cp)}")
        else:
            poison.append(f"sub {g} by {nest.poisoned}")
    w.lookup(f"{name}_poison", poison)
    dead = cls(c["dead"])
    chain = w.define(f"{name.upper()}_CHAIN", [*poisonable, *c["dead"], nest.poisoned, *extra])
    w.lookup(f"{name}_sweep", [f"sub [{start} {' '.join(c['dead'])} {nest.poisoned} {' '.join(extra)}] "
                              f"{cls(poisonable)}' lookup {name}_poison"], chain)
    w.lookup(f"{name}_clear", [f"sub {nest.poisoned} by NULL"])
    w.lookup(f"{name}_signs", [f"sub {dead} {cls(c['var'])}' lookup n_to_lone",
                               f"sub {cls(c['var'])}' lookup n_to_lone {dead}"])
    w.lookup(f"{name}_raw", [f"sub {nest.dead(x)} by {control_name(x)}" for x in CONTROLS]
             + ([f"sub {start} by NULL"] if start == nest.bad_start else []))
    return [f"{name}_sweep", f"{name}_clear", f"{name}_signs", f"{name}_raw"]


def _nest_cell_lookups(n, w, nest):
    """Per sign: its cell markers before it; and the same with a box end
    after it (the last sign of an overlay)."""
    signs = sorted(n.signs)
    w.lookup("n_cell", [f"sub {n.variant(c, 0)} by {nest.cell_width(n.signs[c].cell[0])} "
                        f"{nest.cell_height(n.signs[c].cell[1])} {n.variant(c, 0)}" for c in signs])
    w.lookup("n_cell_end", [f"sub {n.variant(c, 0)} by {nest.cell_width(n.signs[c].cell[0])} "
                            f"{nest.cell_height(n.signs[c].cell[1])} {n.variant(c, 0)} {nest.box_end0}"
                            for c in signs])


def _nest_stage(n, w, nest, d, c):
    """Part A.4 for the boxes at depth d. Returns the lookups, in order."""
    var = cls(c["var"])
    t = {k: nest.token(k, d) for k in ("V", "H", "B", "E", *G.SEG_TYPES[4:])}
    t_d = cls(t.values())
    parents = [nest.run_start] + [nest.token(k, d - 1) for k in ("H", "V")] + ([nest.token("B", d - 1)] if d > 1 else [])
    box_head = f"{nest.box_width0} {nest.box_height0} {nest.cluster_start(d)}"
    row_head = f"{nest.row_height0} {nest.row_width0} {nest.row_carrier0}"
    ovl_row = f"{nest.row_height0} {nest.row_widtho} {nest.row_carrier0}"
    lookups, p = [], f"n{d}_"
    OV = G.OVER
    widths, heights = list(nest.widths()), list(nest.heights())

    # cells and heads
    w.lookup(p + "box_start", [f"sub {g} by {g} {box_head} {nest.layer_one0} {ovl_row}" for g in parents])
    w.lookup(p + "cells", [f"sub {t['O']} {var}' lookup n_cell_end",
                           f"sub {cls(parents)}' lookup {p}box_start {var} {t['O']}",
                           f"sub {var}' lookup n_cell {t_d}", f"sub {t_d} {var}' lookup n_cell"])
    w.lookup(p + "o_plain", [f"sub {t['O']} by {t['O']} {nest.layer_two0}"])
    w.lookup(p + "o_row", [f"sub {t['O']} by {t['O']} {nest.layer_two0} {ovl_row}"])
    w.lookup(p + "heads", [f"sub {t['O']}' lookup {p}o_plain {t['Bg']}", f"sub {t['O']}' lookup {p}o_row"])
    w.lookup(p + "tokens", [
        f"sub {t['B']} by {box_head} {nest.layer_seg0} {row_head} {t['B']}",
        f"sub {t['V']} by {t['V']} {row_head}",
        f"sub {t['E']} by {t['E']} {nest.box_end0}",
        f"sub {t['Bf']} by {box_head} {nest.layer_one0} {ovl_row} {t['Bf']}",
        f"sub {t['Bg']} by {t['Bg']} {ovl_row}", f"sub {t['Vg']} by {t['Vg']} {ovl_row}",
        f"sub {t['Eg']} by {t['Eg']} {nest.box_end0}"])
    w.lookup(p + "ends", [f"sub {nest.box_end0} by {nest.box_end(d)} {nest.cluster_end(d)}"])
    lookups += [p + "cells", p + "heads", p + "tokens", p + "ends"]

    # folds, right to left
    cws = nest.cell_widths()
    cw, ws = [nest.cell_width(a) for a in cws], nest.width_sum

    def plus(a, s, cap):
        return OV if s == OV or a + s > cap else a + s

    rules = [f"rsub {cls(cw)}' {cls(ws(b, s) for b in cws if b <= s)} by "
             f"{cls(ws(a, plus(a, s, nest.max_cell[0])) for a in cws)}" for s in widths]
    rules.append(f"rsub {cls(cw)}' {cls(ws(b, OV) for b in cws)} by {cls(ws(a, OV) for a in cws)}")
    rules.append(f"rsub {cls(cw)}' by {cls(ws(a, a) for a in cws)}")
    w.lookup(p + "ws", rules, w.define(p.upper() + "F_WS", [*cw, *(ws(a, s) for a in cws for s in [*range(a, 29), OV]),
                                                            nest.row_height0]))
    ch, hm = [nest.cell_height(b) for b in heights], nest.height_max
    rules = [f"rsub {cls(ch)}' {hm(m)} by {cls(hm(max(b, m)) for b in heights)}" for m in heights]
    rules.append(f"rsub {cls(ch)}' by {cls(hm(b) for b in heights)}")
    w.lookup(p + "hm", rules, w.define(p.upper() + "F_HM", [*ch, *(hm(m) for m in heights), nest.row_height0]))
    rules = [f"rsub {nest.row_width0}' {cls(ws(a, s) for a in cws if a < s)} {cls(ws(b, b) for b in cws)} "
             f"by {nest.row_pair(s)}" for s in nest.pair_widths()]
    for s in [*widths, OV]:
        rules.append(f"rsub [{nest.row_width0} {nest.row_widtho}]' {cls(ws(a, s) for a in cws if s == OV or a <= s)} "
                     f"by [{nest.row_width(s)} {nest.row_width(s)}]")
    w.lookup(p + "rw", rules, w.define(p.upper() + "F_RW", [nest.row_width0, nest.row_widtho,
                                                            *(ws(a, s) for a in cws for s in [*range(a, 29), OV])]))
    w.lookup(p + "rm", [f"rsub {nest.row_height0}' {hm(m)} by {nest.row_m(m)}" for m in heights],
             w.define(p.upper() + "F_RM", [nest.row_height0, *(hm(m) for m in heights)]))
    lookups += [p + "ws", p + "hm", p + "rw", p + "rm"]
    if d + 1 in nest.depths:  # the slots of the segments one deeper
        lookups += _nest_slots(w, nest, d + 1, p)
    rs = nest.row_sum
    rules = [f"rsub {cls(nest.row_m(m) for m in heights)}' {cls(rs(b, t2) for b in heights if b <= t2)} by "
             f"{cls(rs(m, plus(m, t2, nest.max_cell[1])) for m in heights)}" for t2 in heights]
    rules.append(f"rsub {cls(nest.row_m(m) for m in heights)}' {cls(rs(b, OV) for b in heights)} by "
                 f"{cls(rs(m, OV) for m in heights)}")
    rules.append(f"rsub {cls(nest.row_m(m) for m in heights)}' by {cls(rs(m, m) for m in heights)}")
    all_rs = [rs(m, t2) for m in heights for t2 in [*range(m, 13), OV]]
    layers0 = [nest.layer_seg0, nest.layer_one0, nest.layer_two0]
    w.lookup(p + "rs", rules, w.define(p.upper() + "F_RS", [*(nest.row_m(m) for m in heights), *all_rs, *layers0]))
    lookups.append(p + "rs")

    # the carrier: the widest row from this one to the end of the box
    def rw_list(*values):
        return [x for v in values for x in [nest.row_width(v)] + ([nest.row_pair(v)] if v in nest.pair_widths() else [])]

    def rw_of(*values):
        return cls(rw_list(*values))

    rw_any = rw_of(*widths, OV)
    rules = [f"rsub {rw_any} {nest.row_carrier0}' {rw_any} {nest.carrier(OV)} by {nest.carrier(OV)}",
             f"rsub {rw_of(OV)} {nest.row_carrier0}' by {nest.carrier(OV)}"]
    for g in widths:
        rules.append(f"rsub {rw_of(g)} {nest.row_carrier0}' {rw_any} {cls(nest.carrier(x) for x in range(1, g + 1))} "
                     f"by {nest.carrier(g)}")
        if g > 1:
            rules.append(f"rsub {rw_of(*range(1, g))} {nest.row_carrier0}' {rw_any} {nest.carrier(g)} by {nest.carrier(g)}")
    rules += [f"rsub {rw_of(g)} {nest.row_carrier0}' by {nest.carrier(g)}" for g in widths]
    carriers = [nest.carrier(g) for g in [*widths, OV]]
    w.lookup(p + "carrier", rules, w.define(p.upper() + "F_CAR", [*rw_list(*widths, OV), nest.row_carrier0, *carriers, nest.box_width0]))
    w.lookup(p + "bw", [f"rsub {nest.box_width0}' {rw_any} {nest.carrier(g)} by {nest.box_width(g)}" for g in [*widths, OV]],
             w.define(p.upper() + "F_BW", [nest.box_width0, *rw_list(*widths, OV), *carriers]))
    lookups += [p + "carrier", p + "bw"]

    # layers and box height
    rules = [f"rsub {nest.layer_seg0}' {cls(rs(m, h) for m in heights if m < h)} {cls(rs(b, b) for b in heights)} "
             f"by {nest.layer_seg(h, 2)}" for h in heights if h >= 2]
    rules += [f"rsub {nest.layer_seg0}' {cls(rs(m, h) for m in heights if m <= h)} by {nest.layer_seg(h, 3)}"
              for h in heights if h >= 3]
    rules.append(f"rsub {nest.layer_seg0}' {cls(all_rs)} by {nest.layer_seg(OV, 0)}")  # over (or one row: impossible)
    for h in [*heights, OV]:
        found = cls(rs(m, h) for m in heights if h == OV or m <= h)
        rules += [f"rsub {nest.layer_one0}' {found} by {nest.layer_one(h)}",
                  f"rsub {nest.layer_two0}' {found} by {nest.layer_two(h)}"]
    w.lookup(p + "layers", rules, w.define(p.upper() + "F_LAYERS", [*layers0, *all_rs]))
    segs = [nest.layer_seg(h, k) for h in range(2, 13) for k in (2, 3) if k <= h]
    ones, twos = ([f(h) for h in [*heights, OV]] for f in (nest.layer_one, nest.layer_two))
    rules = []
    for h in heights:
        rules.append(f"rsub {nest.box_height0}' {cls(nest.layer_seg(h, k) for k in (2, 3) if k <= h)} by {nest.box_height(h)}")
        rules.append(f"rsub {nest.box_height0}' {nest.layer_one(h)} {cls(nest.layer_two(x) for x in range(1, h + 1))} "
                     f"by {nest.box_height(h)}")
        rules.append(f"rsub {nest.box_height0}' {cls(nest.layer_one(x) for x in range(1, h))} {nest.layer_two(h)} "
                     f"by {nest.box_height(h)}")
    rules += [f"rsub {nest.box_height0}' {nest.layer_seg(OV, 0)} by {nest.box_height(OV)}",
              f"rsub {nest.box_height0}' {nest.layer_one(OV)} by {nest.box_height(OV)}",
              f"rsub {nest.box_height0}' {cls(ones)} {nest.layer_two(OV)} by {nest.box_height(OV)}"]
    w.lookup(p + "bh", rules, w.define(p.upper() + "F_BH", [nest.box_height0, *segs, nest.layer_seg(OV, 0), *ones, *twos]))
    lookups += [p + "layers", p + "bh"]
    for b in heights:  # an operand learns the height of its box
        w.lookup(f"{p}ovl_{b}", [f"sub {nest.layer_one(h)} by {nest.ovl_top(d, 1, h, b - h)} {nest.ovl_bottom(d, 1, b - h)}"
                                 for h in range(1, b + 1)]
                 + [f"sub {nest.layer_two(h)} by {nest.ovl_top(d, 2, h, b - h)} {nest.ovl_bottom(d, 2, b - h)}"
                    for h in range(1, b + 1)])
    rules = [f"sub {nest.box_height(b)} {cls(nest.layer_one(h) for h in range(1, b + 1))}' lookup {p}ovl_{b}"
             for b in heights]
    rules += [f"sub {nest.box_height(b)} {cls(nest.layer_two(h) for h in range(1, b + 1))}' lookup {p}ovl_{b}"
              for b in heights]
    w.lookup(p + "ovl", rules, w.define(p.upper() + "F_OVL", [*(nest.box_height(h) for h in heights), *ones, *twos]))
    lookups.append(p + "ovl")

    # justify the rows of two of a segment
    for g in widths[1:]:
        w.lookup(f"{p}to_w{g}", [f"sub {cls(nest.carrier(x) for x in range(1, g))} by {nest.carrier(g)}"])
    rules = [f"sub {nest.carrier(g)} {cls(nest.carrier(x) for x in range(1, g))}' lookup {p}to_w{g}" for g in widths[1:]]
    w.lookup(p + "wfill", rules, w.define(p.upper() + "F_WFILL", [*(nest.box_width(g) for g in [*widths, OV]), *carriers]))
    rules = []
    for s in widths:
        slacks = [g for g in range(s + 1, min(s + L.MAX_JUSTIFY, nest.max_cell[0]) + 1)]
        if slacks:
            w.lookup(f"{p}nj{s}", [f"sub {nest.carrier(g)} by {nest.justify(g - s)}" for g in slacks])
            if s in nest.pair_widths():
                rules.append(f"sub {nest.row_pair(s)} {cls(nest.carrier(g) for g in slacks)}' lookup {p}nj{s}")
    justs = [nest.justify(j) for j in range(1, L.MAX_JUSTIFY + 1)]
    rows_of = [nest.row_width(s) for s in [*widths, OV]] + [nest.row_pair(s) for s in nest.pair_widths()]
    w.lookup(p + "just", rules, w.define(p.upper() + "F_JUST", [*rows_of, *carriers, *justs]))
    for j in range(1, L.MAX_JUSTIFY + 1):
        w.lookup(f"{p}jrow{j}", [f"sub {nest.row_pair(s)} by {n.row_left(s + j, 0)}" for s in nest.pair_widths() if s + j <= 28])
        w.lookup(f"{p}jsp{j}", [f"sub {t['H']} by {t['H']} {n.spacer(j, 0)}"])
    w.lookup(p + "jrow", [f"sub {cls(nest.row_pair(s) for s in nest.pair_widths())}' lookup {p}jrow{j} {nest.justify(j)}"
                          for j in range(1, L.MAX_JUSTIFY + 1)],
             w.define(p.upper() + "F_JROW", [*rows_of, *carriers, *justs]))
    w.lookup(p + "jsp", [f"sub {nest.justify(j)} {t['H']}' lookup {p}jsp{j}" for j in range(1, L.MAX_JUSTIFY + 1)],
             w.define(p.upper() + "F_JSP", [*justs, *carriers, t["H"], t["V"]]))
    lookups += [p + "wfill", p + "just", p + "jrow", p + "jsp"]

    # the box is done: final rows, the cell for its row, Xv
    rules = [f"sub {nest.row_width(s)} by {n.row_left(s, 0)}" for s in widths]
    rules += [f"sub {nest.row_pair(s)} by {n.row_left(s, 0)}" for s in nest.pair_widths()]
    rules += [f"sub {rs(m, t2)} by {nest.last_row(d) if t2 == m else nest.row(d, m)}"
              for m in heights for t2 in range(m, 13)]
    rules += [f"sub {g} by NULL" for g in carriers + justs]
    rules += [f"sub {ws(a, s)} by NULL" for a in cws for s in [*range(a, 29), OV]]
    rules += [f"sub {hm(m)} by NULL" for m in heights]
    rules += [f"sub {nest.layer_seg(h, k)} by {nest.seg_layer(d, h, k)}" for h in range(2, 13) for k in (2, 3) if k <= h]
    for g in widths:
        parent = n.cell_width(g) if d == 1 else nest.cell_width(g)
        rules.append(f"sub {nest.box_width(g)} by {parent} {nest.xv(d, g)}")
    for h in heights:
        parent = f"{n.cell_height(h)} {nest.cell_height(h)}" if d == 1 else nest.cell_height(h)
        rules.append(f"sub {nest.box_height(h)} by {parent}")
    single = [r for r in rules if " by NULL" not in r and len(r.split(" by ")[1].split()) == 1]
    multi = [r for r in rules if r not in single]
    w.lookup(p + "done1", single, table=None)
    w.lookup(p + "done2", multi, table=None)
    lookups += [p + "done1", p + "done2"]
    return lookups


def _nest_slots(w, nest, child, p):
    """The rows at depth child - 1 tell the segment layers one deeper in
    them their slot (the row's height)."""
    heights = list(nest.heights())
    waiting = [nest.seg_layer(child, h, k) for h in range(2, 13) for k in (2, 3) if k <= h]
    rules = []
    for m in heights[1:]:  # a segment is at least two units high
        w.lookup(f"{p}slot{m}", [f"sub {nest.seg_layer(child, h, k)} by {nest.seg_top(child, h, k, m)} "
                                 f"{nest.seg_bottom(child, k, m - h)}"
                                 for h in range(2, m + 1) for k in (2, 3) if k <= h])
        have = [nest.seg_top(child, h, k, m) for h in range(2, m + 1) for k in (2, 3) if k <= h]
        fits = [nest.seg_layer(child, h, k) for h in range(2, m + 1) for k in (2, 3) if k <= h]
        rules.append(f"sub [{nest.row_m(m)} {' '.join(have)}] {cls(fits)}' lookup {p}slot{m}")
    slots = sorted({nest.seg_top(d, h, k, r) for d, h, k, r in nest.slots() if d == child})
    w.lookup(p + "slots", rules, w.define(p.upper() + "F_SLOTS", [*(nest.row_m(m) for m in heights), *waiting, *slots]))
    return [p + "slots"]


def _nest_stage0(n, w, nest, c):
    """Part A.5: the rows of the group itself; its tokens become joiners."""
    var = cls(c["var"])
    t0 = cls(nest.token(k, 0) for k in ("V", "H"))
    heights = list(nest.heights())
    w.lookup("n0_cells", [f"sub {var}' lookup n_cell {t0}", f"sub {t0} {var}' lookup n_cell"])
    w.lookup("n0_heads", [f"sub {nest.run_start} by {nest.run_start} {nest.row_height0}",
                          f"sub {nest.token('V', 0)} by {nest.token('V', 0)} {nest.row_height0}"])
    ch, hm = [nest.cell_height(b) for b in heights], nest.height_max
    rules = [f"rsub {cls(ch)}' {hm(m)} by {cls(hm(max(b, m)) for b in heights)}" for m in heights]
    rules.append(f"rsub {cls(ch)}' by {cls(hm(b) for b in heights)}")
    w.lookup("n0_hm", rules, "@N1_F_HM")
    w.lookup("n0_rm", [f"rsub {nest.row_height0}' {hm(m)} by {nest.row_m(m)}" for m in heights], "@N1_F_RM")
    lookups = ["n0_cells", "n0_heads", "n0_hm", "n0_rm", *_nest_slots(w, nest, 1, "n0_")]
    rules = [f"sub {g} by NULL" for g in [*(nest.cell_width(a) for a in nest.cell_widths()), *(hm(m) for m in heights),
                                          *(nest.row_m(m) for m in heights), nest.row_height0]]
    w.lookup("n0_clear", rules)
    w.lookup("n0_signs", [f"sub {t0} {var}' lookup n_to_lone", f"sub {var}' lookup n_to_lone {t0}"])
    w.lookup("n0_tokens", [f"sub {nest.token('V', 0)} by {n.joined[L.VERTICAL_JOINER]}",
                           f"sub {nest.token('H', 0)} by {n.joined[L.HORIZONTAL_JOINER]}"])
    w.lookup("n0_start", [f"sub {nest.run_start} by NULL"])
    return lookups + ["n0_clear", "n0_signs", "n0_tokens", "n0_start"]


def _gsub_nest_fallback(n, w, nest):
    """Part B, spliced in after the flat stages' fallback: a group over the
    caps (head Qx) gives its boxes back."""
    c = _nest_classes(n, nest, w)
    return _nest_revert(n, w, nest, c, "n_rv3", n.fallback_head, "flat", extra=[n.fallback])


def _gsub_nest_level(n, w, nest):
    """Part C: Xv, rows and layers take the level of their group."""
    leveled = nest.leveled()
    layers = nest.verticals()
    for name, k in layers:
        leveled.setdefault(name, [None] * len(LEVELS))[k] = layers[(name, k)]
    placeholders = sorted(leveled)
    finals = {k: sorted({leveled[x][k] for x in placeholders if not x.startswith("_nl")}) for k in LEVELS}
    for k in LEVELS:
        w.lookup(f"n_lvl_{k}", [f"sub {x} by {leveled[x][k]}" for x in placeholders])
    rules = []
    for k in LEVELS:
        heads = [n.head(g, j) for g, j in n.head_sizes if j == k]
        rules.append(f"sub {cls([*heads, *finals[k]])} {cls(placeholders)}' lookup n_lvl_{k}")
    members = [*placeholders, *(x for k in LEVELS for x in finals[k])]
    w.lookup("n_level", rules, w.define("N_F_LEVEL", members))
    lookups = ["n_level"]
    for d in nest.depths:  # last, when no fallback can take the box apart: each box one cluster
        w.lookup(f"n{d}_cluster", [f"sub {nest.cluster_start(d)} {nest.cluster_end(d)} by {nest.cluster_start(d)}"],
                 w.define(f"N{d}_F_CL", [nest.cluster_start(d), nest.cluster_end(d)]))
        lookups.append(f"n{d}_cluster")
    return lookups


def _gpos_nest(n, w, nest):
    """GPOS of segments and overlay, defined right before place_cells.
    Returns the lookups (for mkmk).

    The order is parent first, depth by depth, because HarfBuzz (15) takes
    a mark's height from its base when it attaches it (and CoreText applies
    attachments in lookup order): Xv first takes the line of its row from
    the row's head (or from the box before it in the row), then the layers
    of the box, their rows, the rows' left edges and E; place_cells then
    puts Xv in its place across and every sign on its row."""
    lookups = []
    tops, bottoms = defaultdict(set), defaultdict(set)  # (depth, layer): {(name, y)}
    for final in set(nest.verticals().values()):  # _nVt<depth>.<layer>.<y> and _nVb...
        d, layer, y = int(final[4]), int(final.split(".")[1]), int(final.split(".")[2])
        (tops if final.startswith("_nVt") else bottoms)[(d, layer)].add((final, y))
    for d in nest.depths:
        xvs = [(nest.xv(d, g, k), g, k) for g in nest.widths() for k in LEVELS]
        xv_names = [name for name, _, _ in xvs]
        # the line of the row Xv stands in
        if d == 1:
            heads = [n.row(m, k) for k in LEVELS for m in n.cell_heights] + [n.last_row(k) for k in LEVELS]
        else:
            heads = [nest.row(d - 1, m, k) for m in nest.row_heights() for k in LEVELS] + [nest.last_row(d - 1)]
        w.text.append(f"markClass {cls(xv_names)} <anchor 0 0> @nXv{d};")
        w.lookup(f"n_line{d}", [f"pos mark {cls(heads + xv_names)} <anchor 0 0> mark @nXv{d}"],
                 w.define(f"N_F_LINE{d}", heads + xv_names))
        lookups.append(f"n_line{d}")
        for layer in (1, 2):
            for part, found in (("t", tops), ("b", bottoms)):
                names = sorted(x for x, _ in found[(d, layer)])
                cl = f"@nV{part}{d}{layer}"
                w.text.append(f"markClass {cls(names)} <anchor 0 0> {cl};")
                w.lookup(f"n_place_{part}{d}{layer}", [f"pos mark {cls(xv_names)} <anchor 0 0> mark {cl}"],
                         w.define(f"N_F_{part.upper()}{d}{layer}", [*xv_names, *names]))
                lookups.append(f"n_place_{part}{d}{layer}")
        rows = [(nest.row(d, m, k), m * L.unit(k)) for m in nest.row_heights() for k in LEVELS]
        for name, up in rows:
            w.text.append(f"markClass {name} <anchor 0 {up}> @nR{d};")
        all_tops = sorted(x for layer in (1, 2) for x in tops[(d, layer)])
        rules = [f"pos mark {name} <anchor 0 {y}> mark @nR{d}" for name, y in all_tops]
        rules.append(f"pos mark {cls(name for name, _ in rows)} <anchor 0 0> mark @nR{d}")
        w.lookup(f"n_rows{d}", rules, w.define(f"N_F_ROWS{d}", [*(x for x, _ in all_tops), *(x for x, _ in rows)]))
        w.text.append(f"markClass {nest.last_row(d)} <anchor 0 0> @nL{d};")
        all_bottoms = sorted(x for layer in (1, 2) for x in bottoms[(d, layer)])
        w.lookup(f"n_last{d}", [f"pos mark {name} <anchor 0 {y}> mark @nL{d}" for name, y in all_bottoms],
                 w.define(f"N_F_LAST{d}", [*(x for x, _ in all_bottoms), nest.last_row(d)]))
        row_heads = [x for x, _ in rows] + [nest.last_row(d)]
        lefts = [n.row_left(s, k) for k in LEVELS for s in n.widths]
        w.lookup(f"n_left{d}", [f"pos mark {cls(row_heads)} <anchor 0 0> mark @mLEFT"],
                 w.define(f"N_F_LEFT{d}", [*row_heads, *lefts]))
        w.text.append(f"markClass {nest.box_end(d)} <anchor 0 0> @nE{d};")
        rules = []
        for name, g, k in xvs:
            step = L.half_unit(k)
            rules.append(f"pos mark {name} <anchor {g * step - L.half(g, step)} 0> mark @nE{d}")
        w.lookup(f"n_end{d}", rules, w.define(f"N_F_END{d}", [*xv_names, nest.box_end(d)]))
        lookups += [f"n_rows{d}", f"n_last{d}", f"n_left{d}", f"n_end{d}"]
    return lookups


def nest_cells(nest):
    """(glyph, enter, leave) of Xv and E in the flat chain (place_cells):
    Xv is a cell as wide as its box, E only a point to hang from."""
    cells = []
    for d in nest.depths:
        for g in nest.widths():
            for k in LEVELS:
                step = L.half_unit(k)
                cells.append((nest.xv(d, g, k), -L.half(g, step), g * step - L.half(g, step)))
        cells.append((nest.box_end(d), None, 0))
    return cells


def _splice(w, before, write, table="gsub"):
    """Define the lookups write(writer) makes right before the lookup
    `before` (the order of definition is the order HarfBuzz applies them
    in); for GSUB also register them for rlig (the caller registers GPOS
    lookups)."""
    part = Writer()
    names = write(part)
    at = w.text.index(f"lookup {before} {{")
    w.text[at:at] = part.text
    if table == "gsub":
        w.gsub[w.gsub.index(before):w.gsub.index(before)] = names


def nest_categories(nest):
    """GDEF classes of segments and overlay: the run starts are bases, the
    rest marks."""
    found = {name: "mark" for name in nest.markers()}
    found.update({nest.run_start: "base", nest.bad_start: "base"})
    return found


# --- Insertion at middle, top and bottom (layout section 9) ------------------

def _gsub_side(n, w, sides):
    """Side insertion, the corner insertion's stages (_gsub_insert) for
    U+13439..1343B: check, zone, level, mark, cluster; no bird shrinks. It
    runs before the segment stages and the flat stages; its fallback (rule
    S5) is a horizontal joiner, which the flat stages then take. Returns the
    lookups, in order."""
    i = sides
    controls = cls(control_name(c) for c in L.SIDES)
    lone = w.define("S_LONE", [n.lone(c) for c in sorted(n.signs)])
    ign = w.define("S_IGN", n.ignorables)
    cand = w.define("S_CAND", [i.candidate(c) for c in L.SIDES])
    shaped = w.define("S_SHAPED", [i.shaped(c, s) for c in L.SIDES for s in i.shapes])
    others = w.define("S_OTHERS", [control_name(c) for c in CONTROLS] + i.candidates())
    zw = w.define("S_ZW", [i.zone_width(x) for x in i.widths])
    zh = w.define("S_ZH", [i.zone_height(x) for x in i.heights])
    lookups = []

    # 1. check
    w.lookup("side_to_cand", [f"sub {control_name(c)} by {i.candidate(c)}" for c in L.SIDES])
    w.lookup("side_undo", [f"sub {i.candidate(c)} by {control_name(c)}" for c in L.SIDES])
    w.lookup("side_check", [f"ignore sub {ign} {controls}'", f"ignore sub {controls}' {ign}",
                            f"sub {lone} {controls}' lookup side_to_cand {lone}"])
    w.lookup("side_alone_before", [f"ignore sub {others} {ign} {lone} {cand}'",
                                   f"sub {others} {lone} {cand}' lookup side_undo"])
    w.lookup("side_alone_after", [f"ignore sub {cand}' {lone} {ign} {others}",
                                  f"sub {cand}' lookup side_undo {lone} {others}"])
    rules = []
    for s in i.shapes:
        w.lookup(f"side_to_{s}", [f"sub {i.candidate(c)} by {i.shaped(c, s)}" for c in L.SIDES])
        for control in L.SIDES:  # rule S3: what each control takes
            takes = [n.lone(c) for c in i.insertable if i.shape[c] == s and L.side_insertable(control, n.signs[c])]
            rules.append(f"sub {i.candidate(control)}' lookup side_to_{s} {cls(takes)}")
    w.lookup("side_shape", rules)
    lookups += ["side_check", "side_alone_before", "side_alone_after", "side_shape"]

    # 2. zone: width, then height; the height marker ends up first
    for part, sizes, marker in ((0, i.widths, i.zone_width), (1, i.heights, i.zone_height)):
        name = ("side_zone_width", "side_zone_height")[part]
        for x in sizes:
            w.lookup(f"{name}_{x}", [f"sub {c} by {c} {marker(x)}" for c in i.candidates()[len(L.SIDES):]])
        found = defaultdict(list)
        for (base, control, shape), zone in sorted(i.zones.items()):
            found[(control, shape, zone[part])].append(n.lone(base))
        w.lookup(name, [f"sub {cls(bases)} {i.shaped(control, shape)}' lookup {name}_{x}"
                        for (control, shape, x), bases in sorted(found.items())], extension=True)
        lookups.append(name)

    # 3. level: from the first side level down
    first, last = L.SIDE_LEVELS[0], L.SIDE_LEVELS[-1]
    insertable = w.define("S_INS", [n.lone(c) for c in i.insertable])
    w.lookup("side_first", [f"sub {n.lone(c)} by {n.variant(c, first)} {i.cluster_end}" for c in i.insertable])
    w.lookup("side_start", [f"sub {shaped} {zh} {zw} {insertable}' lookup side_first"])
    lookups.append("side_start")
    for k in L.SIDE_LEVELS:
        after = [n.variant(c, k + 1) if k < last else n.lone(c) for c in i.insertable]
        w.lookup(f"side_next_{k}", [f"sub {n.variant(c, k)} by {a}" for c, a in zip(i.insertable, after)])
        rules = []
        wide, high = defaultdict(list), defaultdict(list)
        for c in i.insertable:
            wide[i.size[(c, k)][0]].append(n.variant(c, k))
            high[i.size[(c, k)][1]].append(n.variant(c, k))
        if k == L.INSERT_LEVELS[-1]:  # top and bottom stop here (rule S3): lone again
            w.lookup(f"side_stop_{k}", [f"sub {n.variant(c, k)} by {n.lone(c)}" for c in i.insertable])
            stop = cls(i.shaped(c, s) for c in L.SIDES if c != L.MIDDLE_INSERT for s in i.shapes)
            rules += [f"sub {stop} {zh} {cls(i.zone_width(x) for x in i.widths if x < a)} {cls(wide[a])}' "
                      f"lookup side_stop_{k}" for a in sorted(wide) if a > i.widths[0]]
            rules += [f"sub {stop} {cls(i.zone_height(y) for y in i.heights if y < b)} {zw} {cls(high[b])}' "
                      f"lookup side_stop_{k}" for b in sorted(high) if b > i.heights[0]]
        rules += [f"sub {cls(i.zone_width(x) for x in i.widths if x < a)} {cls(wide[a])}' lookup side_next_{k}"
                  for a in sorted(wide) if a > i.widths[0]]
        rules += [f"sub {cls(i.zone_height(y) for y in i.heights if y < b)} {zw} {cls(high[b])}' "
                  f"lookup side_next_{k}" for b in sorted(high) if b > i.heights[0]]
        w.lookup(f"side_level_{k}", rules)
        lookups.append(f"side_level_{k}")

    # 4. mark
    w.lookup("side_zone_done", [f"sub {i.zone_height(y)} {i.zone_width(x)} by {i.zone_done}"
                                for y in i.heights for x in i.widths])
    rules = []
    for control, shape, seat in i.mark_sizes:
        variants = [n.variant(c, k) for c in i.insertable for k in L.side_levels(control)
                    if i.shape[c] == shape and L.side_insertable(control, n.signs[c])
                    and L.side_seat(control, n.signs[c], k) == seat]
        rules.append(f"rsub {i.shaped(control, shape)}' {i.zone_done} {cls(variants)} by {i.mark(control, shape, seat)}")
    w.lookup("side_mark", rules)
    hj = control_name(L.HORIZONTAL_JOINER)
    w.lookup("side_joiner_zone", [f"sub {c} {i.zone_done} by {hj}" for c in i.candidates()[len(L.SIDES):]])
    w.lookup("side_joiner", [f"sub {cls(i.candidates())} by {hj}"])
    lookups += ["side_zone_done", "side_mark", "side_joiner_zone", "side_joiner"]

    # 5. cluster
    bases = sorted({n.lone(base) for base, _, _ in i.zones})
    w.lookup("side_cluster", [f"sub {b} {i.cluster_end} by {b}" for b in bases],
             w.define("S_END", [i.cluster_end]), extension=True)
    lookups.append("side_cluster")
    return lookups


def _gpos_side(n, w, sides):
    """Side insertion: the mark of the control hangs from the base at the
    anchor of its seat (rule S4), in subtables by control, shape and the
    lowest and highest seat a base takes; the inserted sign hangs from the
    mark by its origin. Returns the lookups, mark to base first."""
    i = sides
    for control, shape, seat in i.mark_sizes:
        w.text.append(f"markClass {i.mark(control, shape, seat)} <anchor 0 0> @S_{control:X}_{shape}_{seat};")
    groups = defaultdict(list)
    for key, seats in sorted(i.anchors.items()):
        groups[(key[1], key[2], min(seats), max(seats))].append(key)
    rules = []
    for _, keys in sorted(groups.items()):
        if rules:
            rules.append("subtable")
        for key in keys:
            base, control, shape = key
            zone, lift = i.zones[key], n.signs[base].lift
            anchors = " ".join(f"<anchor {zone.x} {zone.seats[seat - 1] + lift}> mark @S_{control:X}_{shape}_{seat}"
                               for seat in sorted(i.anchors[key]))
            rules.append(f"pos base {n.lone(base)} {anchors}")
    w.lookup("side_place", rules, extension=True)
    variants = [n.variant(c, k) for c in i.insertable for k in L.SIDE_LEVELS]
    w.text.append(f"markClass {cls(variants)} <anchor 0 0> @S_SIGN;")
    marks = i.marks()
    w.lookup("side_sign_place", [f"pos mark {cls(marks)} <anchor 0 0> mark @S_SIGN"],
             w.define("S_PLACE", marks + variants))
    return ["side_place", "side_sign_place"]


def side_categories(sides):
    found = {name: "mark" for name in sides.markers()}
    found.update({name: "base" for name in sides.candidates()})
    return found
