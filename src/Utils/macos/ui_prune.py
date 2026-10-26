"""
Utils.macos.ui_prune
Hides Linux-only controls on macOS without editing upstream's UI code.

An application event filter looks at each widget, menu and combo box as it
is shown and hides the ones that only make sense on Linux (Wayland, LSFG,
MangoHud, the VFS deploy method, winetricks...). Matching is by displayed
text, so it follows upstream's UI wherever a control moves. With a non-English
UI language the texts may not match and the controls simply stay visible.

The Linux code behind these controls stays in place, dormant.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QLabel,
                               QLineEdit, QMenu, QWidget)

_HIDE_TEXT = re.compile(
    r"^(?:"
    r"Virtual filesystem \(VFS\)"
    r"|Launch with wayland"
    r"|LSFG.*"
    r"|MangoHud.*"
    r"|Run winetricks"
    r"|Prefix health check.*"
    r"|Launch Options"
    r"|Steam syntax\. When set.*"
    r"|Create case-alias.*"
    # Launcher swap: CrossOver can't run a renamed game exe; Play starts
    # the script extender loader directly on macOS.
    r"|Swap launcher with script extender.*"
    # Proton winetricks installers - CrossOver installs these itself.
    r"|Install Windows component.*"
    r"|Install VC\+\+ Redistributable"
    r"|Install d3dcompiler_47"
    r"|Install XACT audio.*"
    r"|Install LAV Filters.*"
    r"|\.NET runtime"
    # Proton tool prefixes; tools run in the game's bottle on macOS.
    r"|Manage Prefixes.*"
    r")$",
    re.DOTALL,
)
_HIDE_PLACEHOLDER = re.compile(r"%command%")

# Launch-via modes that need a Linux launcher; macOS launches through the
# game's bottle (Auto/Steam) or runs the exe directly (None).
_LINUX_LAUNCH_MODES = {"Heroic", "Lutris", "Faugus", "Bottles"}


def _clean(text: str) -> str:
    return text.replace("&", "").strip()


def _prune_menu(menu: QMenu) -> None:
    for action in menu.actions():
        if _HIDE_TEXT.match(_clean(action.text())):
            action.setVisible(False)


def _prune_combo(combo: QComboBox) -> None:
    items = [combo.itemText(i) for i in range(combo.count())]
    if not {"Lutris", "Faugus"} <= set(items):
        return
    for i in reversed(range(combo.count())):
        if combo.itemText(i) in _LINUX_LAUNCH_MODES:
            combo.removeItem(i)


def _should_hide(widget: QWidget) -> bool:
    if isinstance(widget, (QAbstractButton, QLabel)):
        return bool(_HIDE_TEXT.match(_clean(widget.text())))
    if isinstance(widget, QLineEdit):
        return bool(_HIDE_PLACEHOLDER.search(widget.placeholderText()))
    return False


class _PruneFilter(QObject):
    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        if event.type() == QEvent.Show:
            if isinstance(obj, QMenu):
                _prune_menu(obj)
            elif isinstance(obj, QComboBox):
                _prune_combo(obj)
            elif isinstance(obj, QWidget) and _should_hide(obj):
                _row_of(obj).hide()
        return False


def _row_of(widget: QWidget) -> QWidget:
    """The widget to hide for *widget*: its row when it is the text of a
    "bare checkbox + wrapping label" pair (upstream's option rows), else
    itself - hiding only the label would leave an orphaned checkbox."""
    parent = widget.parentWidget()
    if not isinstance(widget, QLabel) or parent is None or parent.layout() is None:
        return widget
    siblings = [parent.layout().itemAt(i).widget()
                for i in range(parent.layout().count())]
    siblings = [w for w in siblings if w is not None and w is not widget]
    if len(siblings) == 1 and isinstance(siblings[0], QAbstractButton) \
            and not siblings[0].text():
        return parent
    return widget


def install(app: QApplication) -> None:
    app._caelumite_prune_filter = _PruneFilter(app)
    app.installEventFilter(app._caelumite_prune_filter)
