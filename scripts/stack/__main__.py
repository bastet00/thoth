"""Generate the font that gets compiled: SOURCE.ufo -> BUILD_DIR.

    python3 scripts/stack sources/Thoth-Regular.ufo sources/build

Writes BUILD_DIR/Thoth-Regular.ufo and BUILD_DIR/Thoth.designspace, the file
sources/config.yaml points at. The output depends on the source only.
"""

import shutil
import sys
from pathlib import Path

import ufoLib2

from features import add_features
from glyphs import add_controls

# A designspace with one source, because gftools builder can only add the
# transliteration letters (includeSubsets in config.yaml) to a designspace.
DESIGNSPACE = """\
<?xml version='1.0' encoding='UTF-8'?>
<designspace format="4.1">
  <axes>
    <axis tag="wght" name="Weight" minimum="400" maximum="400" default="400"/>
  </axes>
  <sources>
    <source filename="{ufo}" name="{family} {style}" familyname="{family}" stylename="{style}">
      <location><dimension name="Weight" xvalue="400"/></location>
    </source>
  </sources>
  <instances>
    <instance name="{family} {style}" familyname="{family}" stylename="{style}" filename="instance_ufos/{ufo}" stylemapfamilyname="{family}" stylemapstylename="regular">
      <location><dimension name="Weight" xvalue="400"/></location>
    </instance>
  </instances>
</designspace>
"""


def main(source, build_dir):
    source, build_dir = Path(source), Path(build_dir)
    font = ufoLib2.Font.open(source)
    add_controls(font)
    add_features(font)

    shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True)
    font.save(build_dir / source.name)
    designspace = DESIGNSPACE.format(
        ufo=source.name, family=font.info.familyName, style=font.info.styleName
    )
    (build_dir / "Thoth.designspace").write_text(designspace, encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
