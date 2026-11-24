"""Glyphs the generator adds to the source font."""

from ufoLib2.objects import Component, Glyph

# Egyptian hieroglyph format controls (U+13430-U+13440). The source has no
# glyphs for them. Each gets its own glyph, so that features can tell them
# apart, and all of them show one shared outline when no rule replaces them.
CONTROLS = range(0x13430, 0x13441)
FALLBACK = "control.fallback"

SIDE_BEARING = 49  # the side bearing of the signs
BOX, BOTTOM, STROKE = 600, 200, 50  # a square centred on the quadrat (y = 500)
CORNER, DASH, GAP = 100, 125, 50  # one side: corner, gap, dash, gap, dash, gap, corner


def control_name(codepoint):
    return f"u{codepoint:05X}"


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
    """Add the fallback outline and one glyph per control."""
    advance = BOX + 2 * SIDE_BEARING
    fallback = Glyph(FALLBACK, width=advance)
    _dashed_box(fallback.getPen())
    font.addGlyph(fallback)
    names = [control_name(codepoint) for codepoint in CONTROLS]
    for name, codepoint in zip(names, CONTROLS):
        glyph = Glyph(name, width=advance, unicodes=[codepoint])
        glyph.components.append(Component(FALLBACK))
        font.addGlyph(glyph)
    font.lib["public.glyphOrder"] = [*font.lib["public.glyphOrder"], FALLBACK, *names]
