#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"

mkdir -p .build runtime
if command -v node >/dev/null; then
  for script in ui/*.js; do node --check "$script"; done
fi
if [[ "${1:-}" == "--interface" ]]; then
  /usr/bin/uuidgen > .build/interface-version.tmp
  mv .build/interface-version.tmp .build/interface-version
  echo 'Interfaz publicada. La sesión se recuperará al pausar.'
  exit 0
fi
stage=$(mktemp -d "$PWD/.build/app-XXXXXX")
bundle="$stage/Studio Local.app"
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
/usr/bin/xcrun swiftc -swift-version 5 -O -module-cache-path "$PWD/.build/module-cache" native/Studio.swift native/Playback.swift native/VideoCompositor.swift -o "$bundle/Contents/MacOS/StudioLocal" -framework AppKit -framework WebKit -framework AVFoundation -framework MediaToolbox -framework CoreImage
/usr/bin/xcrun swiftc -swift-version 5 -parse-as-library -O -module-cache-path "$PWD/.build/module-cache" native/Probe.swift -o "$stage/probe" -framework AVFoundation
printf '%s' "$PWD" > "$bundle/Contents/Resources/root.txt"
cp assets/app-icon/StudioIcon.icns "$bundle/Contents/Resources/StudioIcon.icns"
/usr/bin/python3 - "$bundle/Contents/Info.plist" "${STUDIO_APP_ID:-local.studiolocal.app}" "${STUDIO_APP_NAME:-Studio Local}" <<'PY'
import plistlib,sys
with open(sys.argv[1],'wb') as f:
    plistlib.dump(dict(CFBundleExecutable='StudioLocal',CFBundleIdentifier=sys.argv[2],CFBundleName=sys.argv[3],CFBundleIconFile='StudioIcon.icns',CFBundlePackageType='APPL',CFBundleVersion='24',CFBundleShortVersionString='1.14.2',NSHighResolutionCapable=True),f)
PY
/usr/bin/codesign --force --sign - "$bundle"
/usr/bin/codesign --verify --deep --strict "$bundle"
/usr/bin/python3 engine/install_update.py --stage "$stage"
