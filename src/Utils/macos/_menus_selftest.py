"""Self-checks for freeing closed menus.

Upstream's right-click menus are parented to a long-lived widget, so without
deleteLater() they stay alive after closing. On macOS each one painted also
keeps its window surfaces (1-3 MB each, 235 MB after two days of use).

Run from src/: python -m Utils.macos._menus_selftest

Qt runs offscreen. The source scan also catches a leaking menu that a future
upstream merge adds.
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


def _settle(app) -> None:
    from PySide6.QtCore import QEvent
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _receiver(call) -> str:
    """Source text of what ``.exec(...)`` is called on, or "" if it isn't a menu:
    a name mentioning a menu (``menu``, ``self._menu``), never a dialog or a drag."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "exec"):
        return ""
    return ast.unparse(func.value)


def _menu_names(tree) -> set[str]:
    """Variables assigned from a menu constructor: ``m = QMenu(self)``."""
    names = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and "menu" in ast.unparse(node.value.func).lower()):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return names


def _deletes(statement, receiver: str) -> bool:
    if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)):
        return False
    call = statement.value
    return (ast.unparse(call.func) == f"{receiver}.deleteLater"
            or (ast.unparse(call.func) == "delete_closed"
                and [ast.unparse(a) for a in call.args] == [receiver]))


def _following(tree, statement) -> tuple[list, object]:
    """The statements after *statement* in its block, and the block's owner."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and statement in block:
                return block[block.index(statement) + 1:], node
    return [], None


def undeleted_menus(tree) -> list[int]:
    """Lines where a menu is shown with ``exec`` and not deleted afterwards, in
    the same block or right after the ``if`` that guards it."""
    names = _menu_names(tree)
    found = []
    for statement in ast.walk(tree):
        if not isinstance(statement, ast.stmt) or isinstance(
                statement, (ast.FunctionDef, ast.ClassDef, ast.If, ast.For, ast.While,
                            ast.Try, ast.With)):
            continue
        for call in (n for n in ast.walk(statement) if isinstance(n, ast.Call)):
            receiver = _receiver(call)
            if not receiver or not ("menu" in receiver.lower() or receiver in names):
                continue
            after, owner = _following(tree, statement)
            if not after and isinstance(owner, ast.If):
                after, _ = _following(tree, owner)
            if not any(_deletes(s, receiver) for s in after):
                found.append(statement.lineno)
    return found


def _scan(source: str) -> list[int]:
    return undeleted_menus(ast.parse(source))


def test_the_scan_tells_leaks_from_fixed_menus() -> None:
    assert _scan("def f(menu):\n    menu.exec(1)\n") == [2]
    assert _scan("def f(menu):\n    menu.exec(1)\n    menu.deleteLater()\n") == []
    assert _scan("def f(menu):\n    menu.exec(1)\n    x = 1\n    delete_closed(menu)\n") == []
    assert _scan("def f(menu):\n    if menu.actions():\n        menu.exec(1)\n"
                 "    menu.deleteLater()\n") == []
    assert _scan("def f(menu):\n    if menu:\n        menu.exec(1)\n") == [3]


def test_the_scan_sees_every_way_of_showing_a_menu() -> None:
    assert _scan("def f(menu):\n    chosen = menu.exec(1)\n") == [2]
    assert _scan("def f(self):\n    m = QMenu(self)\n    m.exec(1)\n") == [3]
    assert _scan("def f(self):\n    m = _StayOpenMenu(self)\n    m.exec(1)\n") == [3]
    assert _scan("def f(self):\n    self._menu.exec(1)\n") == [2]
    assert _scan("def f(self):\n    m = QMenu(self)\n    m.exec(1)\n    m.deleteLater()\n") == []
    assert _scan("def f(a, b):\n    a.exec(1)\n    b.deleteLater()\n") == []
    for other in ("dlg", "box", "drag", "loop", "app"):
        assert _scan(f"def f({other}):\n    {other}.exec(1)\n") == [], other


def test_a_menu_whose_parent_is_gone_is_left_alone() -> None:
    import shiboken6
    from PySide6.QtWidgets import QMenu, QWidget
    from Utils.macos.menus import delete_closed
    _app()
    owner = QWidget()
    menu = QMenu(owner)
    shiboken6.delete(owner)
    delete_closed(menu)         # must not raise "already deleted"


def test_every_shown_menu_is_deleted() -> None:
    leaks = []
    for path in sorted((SRC / "gui_qt").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        leaks += [f"{path.relative_to(SRC)}:{line}" for line in undeleted_menus(tree)]
    assert not leaks, "\n  ".join(["menus that stay alive after closing:", *leaks])


def test_context_menu_is_gone_after_closing() -> None:
    from unittest.mock import patch
    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtWidgets import QMenu, QWidget
    from gui_qt.modlist import menu as modlist_menu
    app = _app()
    owner = QWidget()

    def build(_view, _index):
        built = QMenu(owner)
        built.addAction("Rename")
        built.addMenu("Category")
        QTimer.singleShot(0, built.close)
        return built

    with patch.object(modlist_menu, "build_context_menu", build):
        modlist_menu.show_context_menu(None, QPoint(0, 0), None)
    _settle(app)
    assert not owner.findChildren(QMenu), owner.findChildren(QMenu)


class _Wizard:
    """MainWindow stand-in with no game selected: the Wizard menu's first branch."""

    def __init__(self, menu) -> None:
        self._wizard_btn = SimpleNamespace(_menu=menu)
        self._gs = SimpleNamespace(game=None)

    def tr(self, text: str) -> str:
        return text

    def _add_wizard_management_actions(self, menu) -> None:
        menu.addMenu("Manage")      # the rebuild adds a new submenu every time


def test_wizard_rebuild_leaves_one_set_of_submenus() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMenu
    from gui_qt.app import MainWindow
    app = _app()
    menu = QMenu()
    window = _Wizard(menu)
    for _ in range(5):
        MainWindow._rebuild_wizard_menu(window)
        _settle(app)
    children = menu.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert len(children) == 1, len(children)


def _selector():
    from gui_qt.widgets.selector_button import SelectorButton
    button = SelectorButton()
    button.set_actions([("Manage", [("Rename", lambda: None)])])
    return button


def _direct_children(menu, kind):
    from PySide6.QtCore import Qt
    return menu.findChildren(kind, options=Qt.FindChildOption.FindDirectChildrenOnly)


def test_selector_rebuild_leaves_one_set_of_submenus() -> None:
    from PySide6.QtGui import QActionGroup
    from PySide6.QtWidgets import QMenu
    app = _app()
    button = _selector()
    for _ in range(5):
        button.set_actions([("Manage", [("Rename", lambda: None)])])
        _settle(app)
    assert len(_direct_children(button._menu, QMenu)) == 1
    assert _direct_children(button._menu, QActionGroup) == [button._group]


def test_selector_rebuild_keeps_an_open_submenu() -> None:
    """A stay-open row's callback can rebuild the selector while its submenu is
    open, and then uses its action."""
    from PySide6.QtWidgets import QMenu
    app = _app()
    button = _selector()
    opened = _direct_children(button._menu, QMenu)[0]
    opened.show()
    action = opened.actions()[0]
    button.set_actions([("Manage", [("Rename", lambda: None)])])
    _settle(app)
    assert action.text() == "Rename"    # raises if the submenu was deleted
    opened.hide()
    button.set_actions([("Manage", [("Rename", lambda: None)])])
    _settle(app)
    assert len(_direct_children(button._menu, QMenu)) == 1, "picked up by the next rebuild"


if __name__ == "__main__":
    test_the_scan_tells_leaks_from_fixed_menus()
    print("✓ the scan tells leaking menus from fixed ones")
    test_the_scan_sees_every_way_of_showing_a_menu()
    print("✓ the scan sees other variable names and assigned results, and skips dialogs")
    test_every_shown_menu_is_deleted()
    print("✓ every menu shown with exec() is deleted afterwards")
    test_a_menu_whose_parent_is_gone_is_left_alone()
    print("✓ a menu deleted with its parent is left alone")
    test_context_menu_is_gone_after_closing()
    print("✓ the mod list's context menu and its submenus are gone after closing")
    test_wizard_rebuild_leaves_one_set_of_submenus()
    print("✓ rebuilding the Wizard menu leaves only the current submenus")
    test_selector_rebuild_leaves_one_set_of_submenus()
    print("✓ rebuilding a selector leaves only the current submenus and action group")
    test_selector_rebuild_keeps_an_open_submenu()
    print("✓ a selector rebuild keeps a submenu that is open")
