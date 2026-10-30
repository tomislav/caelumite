"""
Utils.macos.plugins
Manager plugin versions on macOS.

A plugin names the Amethyst version it needs (min_manager_version). It's
checked against the Amethyst release Caelumite is based on
(Utils.macos.app.AMETHYST_VERSION), and shown as the first Caelumite release
built on a new enough Amethyst (AMETHYST_RELEASES): in the plugin browser
(gui_qt/settings/plugin_store.py) and when a plugin is too new
(amethyst_plugins/catalog.py compatibility_error).
"""

from __future__ import annotations


def _covers(base: str, required: str) -> bool:
    """An Amethyst *base* is new enough for *required*, the way upstream's
    compatibility_error compares: a release requirement ignores prereleases."""
    from amethyst_plugins.catalog import version_key
    current, minimum = version_key(base), version_key(required)
    if minimum[1]:
        current = (current[0], True, ())
    return current >= minimum


def caelumite_for(required: str) -> str | None:
    """The first Caelumite release new enough for a plugin that needs
    Amethyst *required*, or None when no release is yet."""
    from amethyst_plugins.catalog import version_key
    from Utils.macos import app
    fits = [(version_key(caelumite), caelumite)
            for amethyst, caelumite in app.AMETHYST_RELEASES.items()
            if _covers(amethyst, required)]
    return min(fits)[1] if fits else None


def version_error(required: str) -> str:
    """Why this Caelumite is too old for a plugin, or "" when it isn't."""
    from Utils.macos import app
    from version import __version__
    if not required or _covers(app.AMETHYST_VERSION, required):
        return ""
    caelumite = caelumite_for(required)
    if caelumite:
        return f"Requires Caelumite {caelumite} or newer (installed: {__version__})."
    return (f"Requires a newer Caelumite, based on Amethyst {required} or newer "
            f"(installed: {__version__}).")


def minimum_label(required: str, tr) -> str:
    """The plugin browser's minimum-version line, in Caelumite versions."""
    if not required:
        version = tr("Not specified")
    else:
        version = caelumite_for(required) or tr(
            "newer than this one (based on Amethyst {0})").format(required)
    return tr("Minimum Caelumite version: {0}").format(version)


def relabel_minimum(view, lines: list[str], required: str) -> list[str]:
    """Replace upstream's "Minimum manager version" line in the plugin
    browser's details with the Caelumite version."""
    upstream = view.tr("Minimum manager version: {0}").format(
        required or view.tr("Not specified"))
    return [minimum_label(required, view.tr) if line == upstream else line
            for line in lines]
