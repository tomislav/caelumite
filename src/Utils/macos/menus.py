"""
Utils.macos.menus
Frees menus that upstream keeps alive after they close.

Upstream parents its right-click menus to a long-lived widget and rebuilds
some menus with clear(), which leaves their submenus behind. On macOS every
menu that was painted keeps its window surfaces, 1-3 MB each, which added up
to 235 MB after two days of use.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMenu


def delete_closed(menu) -> None:
    """Delete a menu after its exec() returned, unless it went with its parent
    while it was open. The caller may still use it until it returns to the
    event loop."""
    if shiboken6.isValid(menu):
        menu.deleteLater()


def delete_old_submenus(menu) -> None:
    """Delete what clear() leaves behind, before a rebuild. A submenu still open
    stays: a stay-open row's callback can rebuild the menu and then use its
    action. The next rebuild picks it up."""
    only_direct = Qt.FindChildOption.FindDirectChildrenOnly
    for sub in menu.findChildren(QMenu, options=only_direct):
        if not sub.isVisible():
            sub.deleteLater()
    for group in menu.findChildren(QActionGroup, options=only_direct):
        group.deleteLater()
