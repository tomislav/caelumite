#!/usr/bin/env bash
# Build build/Caelumite.app, a development app bundle that runs this checkout.
#
# macOS names an app (menu bar, Cmd-Tab, Dock) after the bundle its running
# executable lives in. Run from source that is Homebrew's Python.app, so the
# bundle carries its own copy of the framework's GUI interpreter. A
# pyvenv.cfg one level above it makes that copy use the project .venv, and
# the launcher runs src/run_qt.py from this checkout - so the bundle always
# runs the current code; rebuild it only after the Python environment changes
# (scripts/setup-macos.sh, a Homebrew Python upgrade) or to refresh the icon.
#
# Usage: scripts/build-app.sh [destination-dir]   (default: build/)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT/build}"
APP="$DEST/Caelumite.app"
VENV_PY="$ROOT/.venv/bin/python"

[ -x "$VENV_PY" ] || { echo "error: run scripts/setup-macos.sh first" >&2; exit 1; }

BASE_PREFIX="$("$VENV_PY" -c 'import sys; print(sys.base_prefix)')"
PY_BIN="$BASE_PREFIX/Resources/Python.app/Contents/MacOS/Python"
PY_HOME="$("$VENV_PY" -c 'import sys, os; print(os.path.dirname(sys._base_executable))')"
VERSION="$("$VENV_PY" "$ROOT/src/version.py")"
[ -x "$PY_BIN" ] || { echo "error: framework interpreter not found: $PY_BIN" >&2; exit 1; }

echo "=== Building $APP ($VERSION) ==="
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Interpreter + venv redirection (Contents/ acts as the venv prefix).
cp "$PY_BIN" "$APP/Contents/MacOS/caelumite-python"
ln -s "$ROOT/.venv/lib" "$APP/Contents/lib"
cat > "$APP/Contents/pyvenv.cfg" <<EOF
home = $PY_HOME
include-system-site-packages = false
EOF

# Launcher (the bundle's main executable).
cat > "$APP/Contents/MacOS/Caelumite" <<EOF
#!/bin/bash
# Finder/Dock launches get a minimal PATH; tools like 7z live in Homebrew.
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
cd "$ROOT/src" || exit 1
exec "\$(dirname "\$0")/caelumite-python" run_qt.py "\$@"
EOF
chmod +x "$APP/Contents/MacOS/Caelumite"

# Icon: render the 1024 px master and build an .icns from it.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
QT_QPA_PLATFORM=offscreen "$VENV_PY" "$ROOT/scripts/make_icon.py" "$WORK/master.png" >/dev/null
ICONSET="$WORK/Caelumite.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
    sips -z $size $size "$WORK/master.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    sips -z $((size * 2)) $((size * 2)) "$WORK/master.png" \
        --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Caelumite.icns"

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Caelumite</string>
    <key>CFBundleDisplayName</key><string>Caelumite</string>
    <key>CFBundleIdentifier</key><string>io.github.caelumite</string>
    <key>CFBundleExecutable</key><string>Caelumite</string>
    <key>CFBundleIconFile</key><string>Caelumite</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleVersion</key><string>$VERSION</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.games</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSPrincipalClass</key><string>NSApplication</string>
    <key>CFBundleURLTypes</key>
    <array>
        <dict>
            <key>CFBundleURLName</key><string>Nexus Mods download link</string>
            <key>CFBundleURLSchemes</key><array><string>nxm</string></array>
        </dict>
        <dict>
            <key>CFBundleURLName</key><string>Thunderstore install link</string>
            <key>CFBundleURLSchemes</key><array><string>ror2mm</string></array>
        </dict>
        <dict>
            <key>CFBundleURLName</key><string>MODL download link</string>
            <key>CFBundleURLSchemes</key><array><string>modl</string></array>
        </dict>
    </array>
</dict>
</plist>
EOF

# Re-sign the copied interpreter ad hoc (Apple silicon only runs signed code).
# The bundle itself stays unsigned: it holds a venv config and a symlink to
# the checkout, which a bundle signature can't cover, and a locally built app
# carries no quarantine flag that would ask for one.
codesign --force --sign - "$APP/Contents/MacOS/caelumite-python"

# Tell LaunchServices about the bundle (and its nxm:// scheme). Caelumite
# makes itself the default nxm handler when it starts.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP"

echo "Built $APP"
echo "Start it with: open \"$APP\"   (or drag it into /Applications)"
