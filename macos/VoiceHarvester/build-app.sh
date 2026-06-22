#!/usr/bin/env bash
# Build "Voice Harvester.app" — a real, double-clickable macOS app.
#   ./build-app.sh && open "Voice Harvester.app"
set -euo pipefail
cd "$(dirname "$0")"

APP="Voice Harvester.app"
BIN="VoiceHarvester"

echo "[1/4] Compiling (release)..."
swift build -c release
BINPATH="$(swift build -c release --show-bin-path)/$BIN"
[ -f "$BINPATH" ] || { echo "build failed: $BINPATH missing" >&2; exit 1; }

echo "[2/4] Assembling $APP..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BINPATH" "$APP/Contents/MacOS/$BIN"

if [ ! -f AppIcon.icns ]; then echo "  (generating icon)"; python3 make-icon.py >/dev/null 2>&1 || true; fi
[ -f AppIcon.icns ] && cp AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

echo "[3/4] Writing Info.plist..."
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>            <string>Voice Harvester</string>
  <key>CFBundleDisplayName</key>     <string>Voice Harvester</string>
  <key>CFBundleIdentifier</key>      <string>com.sinhaankur.voiceharvester</string>
  <key>CFBundleVersion</key>         <string>1.0.0</string>
  <key>CFBundleShortVersionString</key> <string>1.0.0</string>
  <key>CFBundlePackageType</key>     <string>APPL</string>
  <key>CFBundleExecutable</key>      <string>VoiceHarvester</string>
  <key>CFBundleIconFile</key>        <string>AppIcon</string>
  <key>LSMinimumSystemVersion</key>  <string>13.0</string>
  <key>NSHighResolutionCapable</key> <true/>
  <key>LSApplicationCategoryType</key> <string>public.app-category.utilities</string>
</dict>
</plist>
PLIST

echo "[4/4] Code-signing (ad-hoc)..."
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "  (codesign skipped — still runs locally)"

echo ""
echo "Built: $(pwd)/$APP"
echo "  open \"$APP\""
echo "  Requires ffmpeg (brew install ffmpeg). Demucs optional for best isolation."
