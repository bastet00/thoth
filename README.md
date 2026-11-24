# Thoth

**Thoth** is an open-source Egyptian hieroglyph font from the [Bastet](https://github.com/bastet00) project that stacks and groups signs into quadrats.

It is named after Thoth (Egyptian *ḏḥwtj*, Djehuty; Arabic تحوت), the god who in Egyptian belief gave people the hieroglyphic script. Google Fonts does not allow script names in a family name, so the name is just "Thoth".

Status: **not started** – no font sources yet. CI skips the build until `sources/` contains a `.glyphs`, `.glyphspackage`, `.designspace` or `.ufo` file.

## What the font should do

Unicode encodes hieroglyph layout with format controls (U+13430–U+1343F). The font has to contain the OpenType rules that turn them into a quadrat:

| Control | Code point | Meaning |
|---|---|---|
| Vertical joiner | U+13430 | next sign goes under this one |
| Horizontal joiner | U+13431 | signs side by side inside a group |
| Insert at corners | U+13432–U+13435 | small sign tucked into a corner |
| Overlay middle | U+13436 | signs drawn on top of each other |
| Begin / end segment | U+13437 / U+13438 | brackets for nested groups |
| Insert at middle/top/bottom, mirror, damage, … | U+13439–U+1345F | Unicode 15 extensions |

Example: `𓂋` U+13430 `𓈖` should render as 𓂋 above 𓈖 in one group.

## Where it will be used

- **bastet-app** (Flutter, Android + iOS): bundled in `assets/fonts/`, so every user gets it with an app update. Flutter shapes text itself, so it does not depend on fonts installed on the phone.
- **bastet-website**: loaded with `@font-face`, so every visitor gets it.
- **simple-keyboard-hiero** (Android): can show stacked groups on the keys. Text typed into other apps still uses that app's own font.

## Building

This repository follows the [Google Fonts project template](https://github.com/googlefonts/googlefonts-project-template), so it can later be submitted to Google Fonts.

```bash
make build   # builds into fonts/ with gftools builder
make test    # runs fontspector with the Google Fonts profile
make proof   # HTML proofs in out/proof
```

Sources go in `sources/` and are listed in `sources/config.yaml`. Built fonts are not committed; GitHub Actions builds them, and tagged releases (e.g. `0.100`) get a zip attached.

## Road to Google Fonts

1. Draw the signs (or start from an existing OFL hieroglyph font, keeping its copyright lines) and write the quadrat rules.
2. Get `make build` and `make test` passing in CI.
3. Make the repository public and tag a release.
4. Open an "Add font" issue at [google/fonts](https://github.com/google/fonts/issues).

## License

[SIL Open Font License 1.1](OFL.txt). Google Fonts accepts only OFL fonts and does not allow a Reserved Font Name, so don't add one.
