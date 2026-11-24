"""OpenType layout: GDEF classes and the feature file."""

SIGNS = range(0x13000, 0x13460)  # Egyptian Hieroglyphs and their format controls
DOTTED_CIRCLE = 0x25CC

# ufo2ft writes its anchor-based rules where it finds "# Automatic Code".
# The transliteration letters and their combining marks are positioned this
# way; the stacking lookups will be added to the same two features.
FEATURES = """\
feature mark {
    # Automatic Code
} mark;

feature mkmk {
    # Automatic Code
} mkmk;
"""


def categories(font):
    """GDEF glyph classes, in the form of public.openTypeCategories.

    The Latin letters and marks arrive with their own classes. Every sign
    and control is a base, also U+13440, which Unicode calls a mark: HarfBuzz
    removes the advance of a mark, and the fallback would cover the next sign.
    """
    return {
        glyph.name: "base"
        for glyph in sorted(font, key=lambda glyph: glyph.name)
        if any(u in SIGNS or u == DOTTED_CIRCLE for u in glyph.unicodes)
    }


def add_features(font):
    font.lib["public.openTypeCategories"] = categories(font)
    font.features.text = FEATURES
