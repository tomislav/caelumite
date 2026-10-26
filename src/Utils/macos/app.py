"""
Utils.macos.app
Caelumite's identity and per-user locations on macOS.

Upstream's user-visible name ("Amethyst Mod Manager") appears in many
shared strings; the rename keeps those files untouched and swaps the name
at the few places a user actually sees it (window title, About, bundle).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Caelumite"
BUNDLE_ID = "io.github.caelumite"
UPSTREAM_NAME = "Amethyst Mod Manager"
UPSTREAM_URL = "https://github.com/ChrisDKN/Amethyst-Mod-Manager"
REPO_SLUG = "tomislav/caelumite"
REPO_URL = f"https://github.com/{REPO_SLUG}"
# Branch holding the synced resources (game handlers, wizard plugins,
# translations, Ludusavi data, curated profiles) - Caelumite's copy of
# upstream's Resources branch, so only reviewed plugin code reaches users.
RESOURCES_BRANCH = "Resources"
RESOURCES_RAW = f"https://raw.githubusercontent.com/{REPO_SLUG}/{RESOURCES_BRANCH}/"
RESOURCES_API = f"https://api.github.com/repos/{REPO_SLUG}/contents/"

# Nexus Mods OAuth credentials for Caelumite. Empty until Nexus registers the
# app (support@nexusmods.com - see docs/NEXUS.md); until then OAuth login is
# off and Nexus features only work with a personal API key in testing setups
# (Utils/macos/nexus.py). Never fill these with another application's values.
NEXUS_CLIENT_ID = ""
NEXUS_CLIENT_SECRET = ""

# How Caelumite names itself in HTTP requests (GitHub, LOOT, Thunderstore,
# modl:// downloads) and in the Keychain, instead of upstream's name.
from version import __version__ as _version  # noqa: E402

USER_AGENT = f"{APP_NAME}/{_version}"
KEYCHAIN_SERVICE = APP_NAME


def config_dir() -> Path:
    """~/Library/Application Support/Caelumite (not created here)."""
    return Path.home() / "Library" / "Application Support" / APP_NAME


def logs_dir() -> Path:
    """~/Library/Logs/Caelumite (not created here)."""
    return Path.home() / "Library" / "Logs" / APP_NAME


def ipc_socket_path() -> Path:
    """The single-instance socket, in the per-user temp folder launchd gives
    every process of this user (confstr _CS_DARWIN_USER_TEMP_DIR, so it does
    not depend on the caller's TMPDIR) - the macOS counterpart of
    $XDG_RUNTIME_DIR. Short enough for the 104-byte socket path limit."""
    try:
        base = os.confstr(65537)  # _CS_DARWIN_USER_TEMP_DIR
    except (OSError, ValueError):
        base = None
    return Path(base or f"/tmp/caelumite-{os.getuid()}") / "caelumite.sock"
