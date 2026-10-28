"""Self-checks for the missing-master check before LOOT runs
(Utils/macos/loot.py) and the Plugin Rules wording (Utils/macos/branding.py).

Run from src/: python -m Utils.macos._loot_selftest

Qt runs offscreen; LOOT itself isn't started.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2]


def _window():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication([])
    return QWidget()


class _Game:
    def __init__(self, loot_game_type: str) -> None:
        self.loot_game_type = loot_game_type


def _rows(*missing: tuple[str, list[str] | None, bool]):
    from gui_qt.plugin_state import PluginRow
    return [PluginRow(name=name, enabled=enabled, missing_masters=masters)
            for name, masters, enabled in missing]


def _notice(rows, game_type="Starfield") -> tuple[str, list[str]]:
    from Utils.macos import loot
    logged: list[str] = []
    with patch.object(loot, "app_log", logged.append):
        return loot.missing_master_notice(_window(), rows, _Game(game_type)), logged


def _method_source(name: str) -> str:
    text = (SRC / "gui_qt" / "app.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node)
    raise AssertionError(f"MainWindow.{name} not found")


def test_names_the_plugin_and_its_master() -> None:
    rows = _rows(("Starfield.esm", None, True),
                 ("NGBxTSEPatch.esm", ["S1N_TheSpaceEconomy.esm"], True))
    notice, logged = _notice(rows)
    assert "NGBxTSEPatch.esm needs S1N_TheSpaceEconomy.esm" in notice, notice
    assert "more plugin" not in notice, notice
    assert any("S1N_TheSpaceEconomy.esm" in line for line in logged), logged


def test_counts_the_other_plugins() -> None:
    rows = _rows(("A.esm", ["X.esm", "Y.esm"], True),
                 ("B.esp", ["Z.esm"], False),     # disabled: LOOT still loads it
                 ("C.esp", ["Z.esm"], True))
    notice, logged = _notice(rows)
    assert "A.esm needs X.esm, Y.esm" in notice, notice
    assert "2 more plugin(s)" in notice, notice
    assert len(logged) == 3, logged


def test_notice_fits_refresh_and_overlap_too() -> None:
    notice, _ = _notice(_rows(("Patch.esp", ["Missing.esm"], True)))
    assert notice.startswith("LOOT can't run:"), notice
    assert "sort" not in notice.lower(), notice


def test_log_is_restored() -> None:
    from Utils.app_log import app_log
    from Utils.macos import loot
    _notice(_rows(("Patch.esp", ["Missing.esm"], True)))
    assert loot.app_log is app_log, loot.app_log


def test_clean_list_sorts() -> None:
    rows = _rows(("Starfield.esm", None, True), ("FTL.esm", [], True))
    assert _notice(rows)[0] == ""


def test_other_games_still_sort() -> None:
    rows = _rows(("Patch.esp", ["Missing.esm"], True))
    assert _notice(rows, "SkyrimSE")[0] == ""
    assert _notice(rows, "Morrowind")[0] != ""
    assert _notice(rows, "OpenMW")[0] != ""


def test_sort_checks_after_plugins_are_current() -> None:
    body = _method_source("_on_sort_plugins")
    check = body.find("missing_master_notice(")
    assert check != -1, "the sort doesn't call missing_master_notice"
    assert body.find("Plugin sources are being refreshed") < check, \
        "the check runs before the plugin list is current"
    assert check < body.find("run_in_worker("), "the check runs after LOOT starts"


def test_overlap_check_calls_it() -> None:
    body = _method_source("_on_show_overlapping_plugins")
    check = body.find("missing_master_notice(")
    assert check != -1, "the overlap check doesn't call missing_master_notice"
    assert check < body.find("run_in_worker("), "the check runs after LOOT starts"


def test_plugin_rules_points_at_the_plugins_panel() -> None:
    from Utils.macos.branding import rebrand
    source = ("No plugin selected.\n"
              "Right-click a plugin and choose 'Plugin Rules'.")
    view = (SRC / "gui_qt" / "plugin_rules_view.py").read_text(encoding="utf-8")
    assert '"No plugin selected.\\n"\n' in view and \
        "\"Right-click a plugin and choose 'Plugin Rules'.\"" in view, \
        "upstream changed the Plugin Rules hint"
    text = rebrand(source)
    assert "Right-click" not in text and "Plugins panel" in text, text


if __name__ == "__main__":
    test_names_the_plugin_and_its_master()
    print("✓ the notice names the plugin and its missing master")
    test_counts_the_other_plugins()
    print("✓ other plugins with missing masters are counted and logged")
    test_notice_fits_refresh_and_overlap_too()
    print("✓ the notice doesn't say sort, so it fits Refresh and the overlap check")
    test_log_is_restored()
    print("✓ the checks put the app log back")
    test_clean_list_sorts()
    print("✓ a list without missing masters sorts")
    test_other_games_still_sort()
    print("✓ only games whose LOOT needs the masters loaded are checked")
    test_sort_checks_after_plugins_are_current()
    print("✓ the sort checks once the plugin list is current, before LOOT starts")
    test_overlap_check_calls_it()
    print("✓ the overlap check runs the same check")
    test_plugin_rules_points_at_the_plugins_panel()
    print("✓ Plugin Rules says to select a plugin in the Plugins panel")
