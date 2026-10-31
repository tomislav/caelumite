"""Self-checks for the Change Version tab's window reference and its
refresh after installs (Utils/macos/change_version.py keep_replacement and
showing_mod) and their hooks in gui_qt/app.py.

Run from src/: python -m Utils.macos._change_version_selftest

Qt runs offscreen with plain widgets standing in for the tab.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parents[2]


def _app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _delete_later_and_settle(app, widget) -> None:
    """deleteLater, then let the event loop delete it as it does in the app."""
    from PySide6.QtCore import QEvent, QTimer
    widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTimer.singleShot(20, app.quit)
    app.exec()


def _open(window, view) -> None:
    """What _open_change_version_tab does: upstream's slot, then the hook."""
    from Utils.macos.change_version import keep_replacement
    window._change_version_view = view
    view.destroyed.connect(
        lambda *_: setattr(window, "_change_version_view", None))
    keep_replacement(window, view)


def test_replaced_tab_keeps_the_new_one() -> None:
    from PySide6.QtWidgets import QWidget
    app = _app()
    window = SimpleNamespace(_change_version_view=None)
    old = QWidget()
    _open(window, old)
    new = QWidget()
    _open(window, new)      # the old tab is deleted only after this
    _delete_later_and_settle(app, old)
    assert window._change_version_view is new, window._change_version_view


def test_closed_tab_is_forgotten() -> None:
    from PySide6.QtWidgets import QWidget
    app = _app()
    window = SimpleNamespace(_change_version_view=None)
    view = QWidget()
    _open(window, view)
    _delete_later_and_settle(app, view)
    assert window._change_version_view is None


class _Tab:
    def __init__(self, mod_name: str, busy: bool = False) -> None:
        self._mod_name, self._busy = mod_name, busy

    def current_mod_name(self) -> str:
        return self._mod_name

    def busy(self) -> bool:
        return self._busy


def test_tab_follows_its_own_mod_only() -> None:
    from Utils.macos.change_version import showing_mod
    window = SimpleNamespace(_change_version_view=_Tab("ScreenSFSE"))
    assert showing_mod(window, "ScreenSFSE")
    assert not showing_mod(window, "Other mod")
    assert showing_mod(window, "ScreenSFSE old name", "ScreenSFSE"), \
        "a rollback that restores the old name still refreshes the tab"
    assert not showing_mod(window, "Other mod", None)
    assert not showing_mod(SimpleNamespace(_change_version_view=_Tab("ScreenSFSE", busy=True)),
                           "ScreenSFSE"), "a waiting tab must not be refreshed"
    assert not showing_mod(SimpleNamespace(_change_version_view=None), "ScreenSFSE")
    assert not showing_mod(SimpleNamespace(), "ScreenSFSE")


def _method_source(name: str) -> str:
    text = (SRC / "gui_qt" / "app.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node)
    raise AssertionError(f"MainWindow.{name} not found")


UPSTREAM_CONNECT = """        self._change_version_view = view
        view.destroyed.connect(
            lambda *_: setattr(self, "_change_version_view", None))
"""


def test_hook_is_in_place() -> None:
    source = _method_source("_open_change_version_tab")
    assert UPSTREAM_CONNECT in source, "upstream's lines must stay unchanged"
    assert source.index(UPSTREAM_CONNECT) < source.index("keep_replacement(self, view)")


class _Window:
    """MainWindow stand-in: named attributes, everything else a no-op."""

    def __init__(self, tab, **attrs) -> None:
        self._change_version_view = tab
        self.synced: list[str] = []
        self.__dict__.update(attrs)

    def _sync_change_version_after_install(self, name: str) -> None:
        self.synced.append(name)

    def tr(self, text: str) -> str:
        return text

    def _maybe_prompt_rename(self, name, on_done, defer_reload=False):
        on_done(name)    # "Rename mod after install" off, the default

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def _rollback(mod_name: str):
    return SimpleNamespace(operation="rollback", mod_name=mod_name)


def _finish_one_install(tab, name, change=None, prev=None) -> list[str]:
    from gui_qt.app import MainWindow
    window = _Window(tab, _install_ok=[], _install_results={},
                     _install_current_path="a.zip", _install_prev_name=prev,
                     _install_version_changes={"a.zip": change} if change else {})
    MainWindow._finish_one_install(window, name)
    return window.synced


def _wizard_finish(tab, name, change=None, prev=None) -> list[str]:
    from gui_qt.app import MainWindow
    window = _Window(tab, _staged_finish_queue=[], _pending_install_batches=[],
                     _pending_after_staged=[], _pending_thunderstore_meta={},
                     _progress_popup=None, _staged_finish_running=True,
                     _gs=SimpleNamespace(game=None, profile_dir=lambda: None))
    prepared = SimpleNamespace(archive="a.zip", profile_dir=None, version_change=change)
    MainWindow._on_wizard_finish_done(window, name, prepared, prev)
    return window.synced


def test_installs_refresh_the_tab_for_its_mod() -> None:
    _app()
    for finish in (_finish_one_install, _wizard_finish):
        assert finish(_Tab("ScreenSFSE"), "ScreenSFSE") == ["ScreenSFSE"], finish
        assert finish(_Tab("ScreenSFSE"), "Other mod") == [], finish
        assert finish(_Tab("ScreenSFSE", busy=True), "ScreenSFSE") == [], finish
        assert finish(None, "ScreenSFSE") == [], finish
        # A rollback restoring the folder's earlier name follows the mod there.
        renamed = finish(_Tab("FTL 2.0.6 (Beta)"), "FTL", _rollback("FTL 2.0.6 (Beta)"))
        assert renamed == ["FTL"], (finish, renamed)
        # Installs the tab started keep upstream's own refresh.
        assert finish(_Tab("Other"), "FTL", prev="FTL") == ["FTL"], finish


if __name__ == "__main__":
    test_replaced_tab_keeps_the_new_one()
    print("✓ a replaced tab's deletion leaves the new tab connected")
    test_closed_tab_is_forgotten()
    print("✓ a closed tab is forgotten")
    test_hook_is_in_place()
    print("✓ the hook is in place where the tab opens")
    test_tab_follows_its_own_mod_only()
    print("✓ only the tab's own mod refreshes it, and not while it waits")
    test_installs_refresh_the_tab_for_its_mod()
    print("✓ both install paths refresh the tab for its mod, also under a restored name")
