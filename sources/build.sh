#!/bin/sh
# Builds Thoth into fonts/: generates sources/build/ from the source UFO,
# then compiles it. Run it inside the virtual environment; "make build"
# does that.
set -e
cd "$(dirname "$0")/.."
python3 -B scripts/stack sources/Thoth-Regular.ufo sources/build
gftools builder sources/config.yaml
