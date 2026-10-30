"""Self-checks for manager plugins on macOS: the version a plugin requires is
an Amethyst version, compared with the one Caelumite is based on
(Utils/macos/app.py AMETHYST_VERSION), not Caelumite's own.

Run from src/: python -m Utils.macos._plugins_selftest
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _plugin(minimum: str):
    return SimpleNamespace(min_manager_version=minimum, methods=())


def test_plugins_for_this_amethyst_are_compatible() -> None:
    from amethyst_plugins.catalog import compatibility_error
    from Utils.macos.app import AMETHYST_VERSION
    assert compatibility_error(_plugin("2.6.0")) == ""
    assert compatibility_error(_plugin(AMETHYST_VERSION)) == ""
    assert compatibility_error(_plugin("")) == ""


def test_too_new_plugins_name_caelumite() -> None:
    # The error names Caelumite versions; a plugin for an Amethyst newer than
    # any Caelumite release names that Amethyst instead.
    from amethyst_plugins.catalog import compatibility_error
    from version import __version__
    with patch("Utils.macos.app.AMETHYST_RELEASES", {"2.6.0": "1.2.0", "2.7.0": "1.3.0"}), \
            patch("Utils.macos.app.AMETHYST_VERSION", "2.6.0"):
        error = compatibility_error(_plugin("2.7.0"))
        assert error == f"Requires Caelumite 1.3.0 or newer (installed: {__version__}).", error
        error = compatibility_error(_plugin("99.0.0"))
        assert error == ("Requires a newer Caelumite, based on Amethyst 99.0.0 or newer "
                         f"(installed: {__version__})."), error


def test_minimum_version_is_a_caelumite_version() -> None:
    from Utils.macos.plugins import minimum_label
    tr = lambda text: text
    with patch("Utils.macos.app.AMETHYST_RELEASES", {"2.6.0": "1.2.0", "2.7.0": "1.3.0"}):
        assert minimum_label("2.6.0", tr) == "Minimum Caelumite version: 1.2.0"
        assert minimum_label("2.6.0-beta.2", tr) == "Minimum Caelumite version: 1.2.0"
        assert minimum_label("2.5.5", tr) == "Minimum Caelumite version: 1.2.0"
        assert minimum_label("2.6.1", tr) == "Minimum Caelumite version: 1.3.0"
        assert minimum_label("3.0.0", tr) == \
            "Minimum Caelumite version: newer than this one (based on Amethyst 3.0.0)"
        assert minimum_label("", tr) == "Minimum Caelumite version: Not specified"


def test_releases_include_the_current_amethyst() -> None:
    from Utils.macos.app import AMETHYST_RELEASES, AMETHYST_VERSION
    assert AMETHYST_VERSION in AMETHYST_RELEASES


def test_plugin_browser_shows_caelumite_versions() -> None:
    from PySide6.QtWidgets import QApplication
    from gui_qt.settings import plugin_store
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication.instance() or QApplication([])
    upstream = "Minimum manager version: {0}".format("2.6.0")
    lines = ["Name", "Author: X", upstream, "", "Description"]
    view = SimpleNamespace(tr=lambda text: text)
    from Utils.macos.plugins import relabel_minimum
    assert relabel_minimum(view, lines, "2.6.0") == [
        "Name", "Author: X", minimum_label_for("2.6.0"), "", "Description"]
    source = Path(plugin_store.__file__).read_text(encoding="utf-8")
    assert "relabel_minimum(" in source, "the plugin browser doesn't relabel the version"


def minimum_label_for(version):
    from Utils.macos.plugins import minimum_label
    return minimum_label(version, lambda text: text)


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
    test_too_new_plugins_name_caelumite()
    print("✓ a plugin for a newer Amethyst names the Caelumite release it needs")
    test_minimum_version_is_a_caelumite_version()
    print("✓ the minimum version is shown as a Caelumite version")
    test_releases_include_the_current_amethyst()
    print("✓ the release table includes the Amethyst Caelumite is based on")
    test_plugin_browser_shows_caelumite_versions()
    print("✓ the plugin browser shows the Caelumite version")
    test_plugin_url_schemes_write_no_linux_files()
    print("✓ a plugin's URL scheme writes no Linux desktop files")
