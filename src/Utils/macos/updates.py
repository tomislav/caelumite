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
import time

MODE = "macos"
# Upstream checks once, at startup; a Mac app often stays open for days.
DAY_SECONDS = 24 * 60 * 60
# A QTimer stops counting while the Mac sleeps, so wake hourly and compare
# the wall clock instead of waiting out 24 hours of awake time.
_WAKE_MS = 60 * 60 * 1000
# Main-window flags upstream sets while files are in use or changing.
_BUSY_FLAGS = ("_deploy_running", "_install_running", "_col_install_running",
               "_tool_busy")


def _busy(window) -> bool:
    """A game or tool is running, or a deploy or install is: no banner now."""
    session = getattr(window, "_play_session", None)
    if session is not None and getattr(session, "active", False):
        return True
    return any(getattr(window, flag, False) for flag in _BUSY_FLAGS)


def start_daily_check(window, *, clock=time.time):
    """Repeat the startup update check once a day while *window* is open,
    the first idle hour after a day has passed. It is the automatic check:
    it honours "Notify about new versions" and shows the banner again for an
    update that is still waiting."""
    from PySide6.QtCore import QTimer

    last = [clock()]    # the startup check

    def wake():
        if clock() - last[0] < DAY_SECONDS or _busy(window):
            return
        check = getattr(window, "_check_for_app_update", None)
        if callable(check):
            last[0] = clock()
            check()

    timer = QTimer(window)
    timer.setInterval(_WAKE_MS)
    timer.timeout.connect(wake)
    timer.start()
    return timer


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
