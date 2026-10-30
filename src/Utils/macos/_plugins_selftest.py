"""Self-checks for manager plugins on macOS: the version a plugin requires is
an Amethyst version, compared with the one Caelumite is based on
(Utils/macos/app.py AMETHYST_VERSION), not Caelumite's own.

Run from src/: python -m Utils.macos._plugins_selftest
"""

from __future__ import annotations

from types import SimpleNamespace


def _plugin(minimum: str):
    return SimpleNamespace(min_manager_version=minimum, methods=())


def test_plugins_for_this_amethyst_are_compatible() -> None:
    from amethyst_plugins.catalog import compatibility_error
    from Utils.macos.app import AMETHYST_VERSION
    assert compatibility_error(_plugin("2.6.0")) == ""
    assert compatibility_error(_plugin(AMETHYST_VERSION)) == ""
    assert compatibility_error(_plugin("")) == ""


def test_newer_plugins_name_the_amethyst_version() -> None:
    from amethyst_plugins.catalog import compatibility_error
    from Utils.macos.app import AMETHYST_VERSION
    error = compatibility_error(_plugin("99.0.0"))
    assert f"installed: {AMETHYST_VERSION}" in error, error


def test_plugin_url_schemes_write_no_linux_files() -> None:
    # Only schemes the app bundle declares reach Caelumite, so a plugin's
    # own scheme is skipped (and said so) instead of written as .desktop
    # files and mimeapps.list entries.
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    from amethyst_plugins import protocols
    provider = SimpleNamespace(protocols=("examplemods",))
    plugin = SimpleNamespace(download_providers=(provider,))
    logs: list[str] = []
    with tempfile.TemporaryDirectory() as home, \
            patch.dict(os.environ, {"HOME": home}), \
            patch.object(protocols, "discover", return_value=([plugin], [])), \
            patch.object(protocols, "load_settings", return_value={}):
        protocols.register_all(logs.append)
        written = [p for p in Path(home).rglob("*") if p.is_file()
                   and (p.suffix == ".desktop" or p.name == "mimeapps.list")]
    assert not written, written
    assert any("examplemods://" in line for line in logs), logs


if __name__ == "__main__":
    test_plugins_for_this_amethyst_are_compatible()
    print("✓ plugins made for Caelumite's Amethyst version are compatible")
    test_newer_plugins_name_the_amethyst_version()
    print("✓ a plugin for a newer Amethyst names the version Caelumite is based on")
    test_plugin_url_schemes_write_no_linux_files()
    print("✓ a plugin's URL scheme writes no Linux desktop files")
