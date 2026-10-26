#!/usr/bin/env bash
# Build the libloot Python extension for macOS (loot.cpython-3XX-darwin.so)
# from https://github.com/loot/libloot and place it in src/.
#
# Usage:
#   src/LOOT/build_libloot_macos.sh            # latest master
#   src/LOOT/build_libloot_macos.sh 0.29.6     # a specific release tag (flatpak pin)
#
# Requires: git, Rust (cargo), Xcode command line tools, and the project's
# .venv (the extension is built for the venv's Python version).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$(dirname "$SRC_DIR")/.venv/bin/python"
REF="${1:-}"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "error: $VENV_PYTHON not found - create the project .venv first" >&2
    exit 1
fi
command -v cargo >/dev/null 2>&1 || { echo "error: cargo is required" >&2; exit 1; }

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "=== Cloning libloot ${REF:-master} ==="
git clone -q --depth 1 ${REF:+--branch "$REF"} https://github.com/loot/libloot.git "$WORK_DIR/libloot"
export LIBLOOT_REVISION
LIBLOOT_REVISION="$(git -C "$WORK_DIR/libloot" rev-parse --short HEAD)"

echo "=== Building wheel with maturin ==="
"$VENV_PYTHON" -m pip install -q --disable-pip-version-check maturin
(cd "$WORK_DIR/libloot/python" &&
    "$VENV_PYTHON" -m maturin build --release --interpreter "$VENV_PYTHON" --out "$WORK_DIR/wheels")

WHEEL="$(find "$WORK_DIR/wheels" -name '*.whl' | head -1)"
[ -n "$WHEEL" ] || { echo "error: maturin produced no wheel" >&2; exit 1; }
unzip -q -o "$WHEEL" -d "$WORK_DIR/extract"
SO_FILE="$(find "$WORK_DIR/extract" -name 'loot*.so' -type f | head -1)"
[ -n "$SO_FILE" ] || { echo "error: no extension inside $WHEEL" >&2; exit 1; }

EXT_SUFFIX="$("$VENV_PYTHON" -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')"
cp -f "$SO_FILE" "$SRC_DIR/loot${EXT_SUFFIX}"
echo "Installed $SRC_DIR/loot${EXT_SUFFIX}"
