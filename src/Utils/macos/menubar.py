"""
Utils.macos.menubar
The native macOS menu bar for Caelumite's main window.

Qt moves actions with an About/Preferences/Quit role into the application
menu and adds Services, Hide, Hide Others and Show All there itself. The
other menus forward to the main window's existing handlers, so they behave
exactly like the toolbar buttons they mirror.

Shortcuts: only the standard macOS ones are bound here. Upstream's own
shortcuts (Deploy, Restore, Select All, ... - see Utils.ui.shortcut_bindings) stay
with upstream; binding them twice would make both ambiguous. Upstream's
default Install Mod shortcut moves from Ctrl+M (Cmd+M) to Cmd+I on macOS so
Cmd+M can minimize, as on every Mac app.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMenuBar, QMessageBox

from Utils.macos.app import APP_NAME, REPO_URL, UPSTREAM_NAME, UPSTREAM_URL


def _focused(method: str):
    """Run *method* (cut, copy, undo, ...) on the focused widget, if it has one."""
    def run():
        widget = QApplication.focusWidget()
        fn = getattr(widget, method, None)
        if callable(fn):
            fn()
    return run


def _action(menu, text, slot=None, shortcut=None, role=None):
    action = QAction(text, menu)
    if shortcut is not None:
        action.setShortcut(QKeySequence(shortcut))
    if role is not None:
        action.setMenuRole(role)
    if slot is not None:
        action.triggered.connect(lambda _checked=False: slot())
    menu.addAction(action)
    return action


def _call(window, name: str, **kwargs):
    """A slot calling the main window's handler *name* when it exists."""
    def run():
        fn = getattr(window, name, None)
        if callable(fn):
            fn(**kwargs)
    return run


def _open(url: str) -> None:
    from Utils.environment.xdg import open_url
    open_url(url)


def _about(window) -> None:
    from version import __version__
    QMessageBox.about(
        window, f"About {APP_NAME}",
        f"<h3>{APP_NAME} {__version__}</h3>"
        f"<p>A mod manager for Windows games running in CrossOver on macOS.</p>"
        f"<p><a href='{REPO_URL}'>{REPO_URL.removeprefix('https://')}</a></p>"
        f"<p>{APP_NAME} is a fork of <a href='{UPSTREAM_URL}'>{UPSTREAM_NAME}</a> "
        f"by ChrisDKN, which provides nearly all of its mod management.</p>"
        f"<p>Licensed under the GNU General Public License v3.</p>")


def install(window) -> QMenuBar:
    """Build the menu bar on *window* (the upstream MainWindow)."""
    bar = window.menuBar()

    # Application menu (Qt relocates these by role).
    app_menu = bar.addMenu(APP_NAME)
    _action(app_menu, f"About {APP_NAME}", lambda: _about(window),
            role=QAction.AboutRole)
    # The same check as Settings ▸ Updates ▸ Check for updates.
    _action(app_menu, "Check for Updates…",
            _call(window, "_check_for_app_update", force_fresh=True, notify_result=True),
            role=QAction.ApplicationSpecificRole)
    _action(app_menu, "Settings…", _call(window, "_open_settings_modal"),
            "Ctrl+,", QAction.PreferencesRole)
    _action(app_menu, f"Quit {APP_NAME}", window.close,
            "Ctrl+Q", QAction.QuitRole)

    file_menu = bar.addMenu("File")
    _action(file_menu, "Install Mod…", _call(window, "_on_install_mod"))
    file_menu.addSeparator()
    _action(file_menu, "Deploy", _call(window, "_on_deploy"))
    _action(file_menu, "Restore", _call(window, "_on_restore"))

    edit_menu = bar.addMenu("Edit")
    _action(edit_menu, "Undo", _focused("undo"), QKeySequence.Undo)
    _action(edit_menu, "Redo", _focused("redo"), QKeySequence.Redo)
    edit_menu.addSeparator()
    _action(edit_menu, "Cut", _focused("cut"), QKeySequence.Cut)
    _action(edit_menu, "Copy", _focused("copy"), QKeySequence.Copy)
    _action(edit_menu, "Paste", _focused("paste"), QKeySequence.Paste)
    _action(edit_menu, "Select All", _focused("selectAll"))

    window_menu = bar.addMenu("Window")
    _action(window_menu, "Minimize", window.showMinimized, "Ctrl+M")
    _action(window_menu, "Zoom",
            lambda: window.showNormal() if window.isMaximized()
            else window.showMaximized())
    window_menu.addSeparator()
    _action(window_menu, "Bring All to Front",
            lambda: (window.raise_(), window.activateWindow()))

    help_menu = bar.addMenu("Help")
    _action(help_menu, f"{APP_NAME} on GitHub", lambda: _open(REPO_URL))
    _action(help_menu, "Report an Issue…", lambda: _open(f"{REPO_URL}/issues"))
    help_menu.addSeparator()
    _action(help_menu, f"{APP_NAME} Wiki", _call(window, "_open_wiki_tab"))
    _action(help_menu, f"{APP_NAME} Changelog", _call(window, "_open_changelog_tab"))
    _action(help_menu, f"{UPSTREAM_NAME} on GitHub", lambda: _open(UPSTREAM_URL))

    # nxm:// links that arrived while the window was being built.
    from Utils.macos import urls
    urls.attach(window)
    return bar
