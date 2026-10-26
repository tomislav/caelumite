#!/usr/bin/env bash
# One-time setup for running Caelumite from source on macOS:
# creates .venv, installs the Python dependencies and builds the two native
# extensions (amethyst_filegraph and libloot) into src/.
#
# Needs: Homebrew Python 3.12+ (python3.14 preferred), Rust (brew install rust)
# and the Xcode command line tools (xcode-select --install).
#
# Usage: scripts/setup-macos.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIBLOOT_REF="0.29.6"

PYTHON=""
for candidate in python3.14 python3.13 python3.12; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$(command -v "$candidate")"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "error: Python 3.12-3.14 not found - install it with: brew install python@3.14" >&2
    exit 1
fi
if ! command -v cargo >/dev/null 2>&1; then
    echo "error: cargo not found - install Rust with: brew install rust" >&2
    exit 1
fi
if ! xcode-select -p >/dev/null 2>&1; then
    echo "error: Xcode command line tools missing - run: xcode-select --install" >&2
    exit 1
fi

echo "=== Python environment ($PYTHON) ==="
if [ ! -x "$ROOT/.venv/bin/python" ]; then
    "$PYTHON" -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install -q --disable-pip-version-check -r "$ROOT/src/requirements.txt"

echo "=== amethyst_filegraph (deployment catalog) ==="
"$ROOT/.venv/bin/python" "$ROOT/native/amethyst_filegraph/build_extension.py"

echo "=== libloot $LIBLOOT_REF (plugin sorting) ==="
"$ROOT/src/LOOT/build_libloot_macos.sh" "$LIBLOOT_REF"

echo
echo "Done. Start Caelumite with: $ROOT/caelumite"
