"""
Utils.macos.updates
Update checks for the macOS app against Caelumite's GitHub releases.

Upstream's checker knows how to update an AppImage, a Flatpak or an AUR
package. On macOS a release is a notarized DMG attached to a GitHub release
(scripts/build_release.py), so the check looks for the newest release with a
DMG, and the banner's update button downloads it in the browser; installing
is dragging the new app over the old one.
"""

from __future__ import annotations

import json

MODE = "macos"


def latest_release(allow_prerelease: bool, *, force: bool = False):
    """(version, is_prerelease, DMG URL) of the newest release that carries a
    DMG; False when no release qualifies; None when GitHub can't be read."""
    from Utils.github import app_updates as au

    raw = au._gh_fetch_text(au._APP_UPDATE_RELEASES_LIST_API_URL, timeout=10,
                            min_interval=3600, force=force)
    if raw is None:
        return None
    try:
        releases = json.loads(raw)
    except ValueError:
        return None
    candidates = []
    for release in releases if isinstance(releases, list) else []:
        tag = str(release.get("tag_name", "")).lstrip("v")
        is_pre = bool(release.get("prerelease", False))
        if release.get("draft", False) or not tag or (is_pre and not allow_prerelease):
            continue
        dmg = next((a.get("browser_download_url", "") for a in release.get("assets", [])
                    if str(a.get("name", "")).endswith(".dmg")), "")
        if dmg.startswith("https://"):
            candidates.append((tag, is_pre, dmg))
    if not candidates:
        return False
    candidates.sort(key=lambda c: au._parse_version(c[0]), reverse=True)
    return candidates[0]


def check(current: str, allow_prerelease: bool, force: bool,
          force_downgrade_prompt: bool, emit) -> str:
    """The macOS branch of the app's update check (worker thread). Calls
    *emit* with the banner payload when an update is offered; returns
    "available", "current" or "failed" like upstream's branches."""
    from Utils.github.app_updates import _is_newer_version

    result = latest_release(allow_prerelease, force=force)
    if result is None:
        return "failed"
    if result is False:
        return "current"
    latest, is_pre, dmg_url = result
    newer = _is_newer_version(current, latest)
    if newer or (force_downgrade_prompt and latest != current):
        emit((current, latest, MODE, is_pre, not newer, dmg_url))
        return "available"
    return "current"
