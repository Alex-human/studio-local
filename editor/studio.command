#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
if [[ ! -x 'Studio Local.app/Contents/MacOS/StudioLocal' ]]; then ./build.command; fi
exec './Studio Local.app/Contents/MacOS/StudioLocal'
