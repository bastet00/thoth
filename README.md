# Thoth

**Thoth** is an open-source Egyptian hieroglyph font from the [Bastet](https://github.com/bastet00) project that stacks and groups signs into quadrats.

It is named after Thoth (Egyptian *ḏḥwtj*, Djehuty; Arabic تحوت), the god who in Egyptian belief gave people the hieroglyphic script. Google Fonts does not allow script names in a family name, so the name is just "Thoth".

Status: **work in progress** – the font builds and contains the signs, imported from Noto Sans Egyptian Hieroglyphs (see [Credits](#credits)). It does not stack signs yet; the quadrat rules are the next step.

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

The source is `sources/Thoth-Regular.ufo`, listed in `sources/config.yaml`. The font is a static TTF and stays unhinted. Built fonts are not committed; GitHub Actions builds them, and tagged releases (e.g. `0.100`) get a zip attached.

## Road to Google Fonts

1. Write the quadrat rules.
2. Get `make build` and `make test` passing in CI.
3. Make the repository public and tag a release.
4. Open an "Add font" issue at [google/fonts](https://github.com/google/fonts/issues).

## Credits

The sign outlines come from [Noto Sans Egyptian Hieroglyphs](https://github.com/notofonts/egyptian-hieroglyphs), designed by the Monotype Design Team for the Noto project and published under the SIL Open Font License (imported at commit `209775d`). Its copyright notice is kept in `OFL.txt` and in the font.

## License

[SIL Open Font License 1.1](OFL.txt). Google Fonts accepts only OFL fonts and does not allow a Reserved Font Name, so don't add one.
