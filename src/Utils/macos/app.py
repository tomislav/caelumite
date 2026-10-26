"""
Utils.macos.app
Caelumite's identity and per-user locations on macOS.

Upstream's user-visible name ("Amethyst Mod Manager") appears in many
shared strings; the rename keeps those files untouched and swaps the name
at the few places a user actually sees it (window title, About, bundle).
"""

from __future__ import annotations

from pathlib import Path

APP_NAME = "Caelumite"
BUNDLE_ID = "io.github.caelumite"
UPSTREAM_NAME = "Amethyst Mod Manager"
UPSTREAM_URL = "https://github.com/ChrisDKN/Amethyst-Mod-Manager"


def config_dir() -> Path:
    """~/Library/Application Support/Caelumite (not created here)."""
    return Path.home() / "Library" / "Application Support" / APP_NAME


def logs_dir() -> Path:
    """~/Library/Logs/Caelumite (not created here)."""
    return Path.home() / "Library" / "Logs" / APP_NAME
