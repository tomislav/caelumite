"""
Utils.macos.diagnostics
macOS rows for the System Information report (Settings and the top of each
session log), built from upstream's ``Utils.diagnostics.system.collect``.

Upstream's rows describe a Linux desktop: the distribution, libc, Flatpak and
AppImage packaging, the desktop environment and the X11/Wayland display. None
of them exist on macOS, so they are dropped, and the facts a Caelumite bug
report needs instead (the macOS version, how the app was installed, the
installed CrossOver builds) take their place.
"""

from __future__ import annotations

import platform
from pathlib import Path

# Labels from Utils.diagnostics.system.collect() that only mean something on
# Linux. "Package" is replaced by the CrossOver row rather than dropped.
_LINUX_ONLY = frozenset({
    "Distribution", "libc", "Desktop", "Session", "Display sockets",
    "QPA request",
})


def macos_version() -> str:
    """"macOS 27.0.1", or upstream's platform string if it can't be read."""
    version = platform.mac_ver()[0]
    return f"macOS {version}" if version else platform.platform()


def run_mode() -> str:
    """"App bundle" for a release build, "Source" for a checkout.

    The release bundle keeps the app code in Contents/Resources/app; the
    development bundle from scripts/build-app.sh runs the checkout, so it
    reports "Source" too.
    """
    parts = Path(__file__).resolve().parts
    for i in range(len(parts) - 2):
        if parts[i].endswith(".app") and parts[i + 1:i + 4] == (
                "Contents", "Resources", "app"):
            return "App bundle"
    return "Source"


def crossover_versions() -> str:
    """Installed CrossOver builds, newest first: "26.3.0.39832 (/Applications/CrossOver.app)"."""
    from Utils.macos.crossover import list_crossover_apps
    apps = list_crossover_apps()
    if not apps:
        return "None found"
    return "; ".join(f"{app.version} ({app.path})" for app in apps)


def system_info(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Upstream's (label, value) pairs with the Linux rows swapped for macOS ones."""
    def _safe(fn, fallback: str) -> str:
        try:
            return fn() or fallback
        except Exception:
            return fallback

    out: list[tuple[str, str]] = []
    for label, value in pairs:
        if label in _LINUX_ONLY:
            continue
        if label == "OS":
            value = _safe(macos_version, value)
        elif label == "Run mode":
            value = _safe(run_mode, value)
        elif label == "Package":
            label, value = "CrossOver", _safe(crossover_versions, "Unknown")
        out.append((label, value))
    return out
