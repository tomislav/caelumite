"""Self-checks for the play bar's Logs on macOS (Utils/macos/launch_logs.py).

Run from src/: python -m Utils.macos._launch_logs_selftest

Logs go to a temporary home folder; no Steam, Wine or bottle is started.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2]


def _qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_logs_open_one_wine_tab() -> None:
    # CrossOver has no UMU or Proton: the play bar opens one tab, named Wine.
    from Utils.macos.launch_logs import KINDS
    assert KINDS == ("umu",)
    app = (SRC / "gui_qt" / "app.py").read_text(encoding="utf-8")
    assert "from Utils.macos.launch_logs import KINDS" in app


def test_wine_tab_title_and_empty_text() -> None:
    _qt_app()
    from gui_qt.launchers.logs import LaunchLogEditor
    with tempfile.TemporaryDirectory() as tmp:
        editor = LaunchLogEditor(Path(tmp), "umu", "Starfield")
        assert editor.name == "Wine — Starfield", editor.name
        assert editor._label.text() == "Wine — Starfield", editor._label.text()
        assert "No Wine output" in editor._original, editor._original
        assert "Proton" not in editor._original, editor._original


def test_steam_hand_off_notes_where_the_output_goes() -> None:
    from Utils.executables import logs
    from Utils.macos import launch
    from Utils.macos.launch_logs import STEAM_NOTE
    with tempfile.TemporaryDirectory() as tmp, \
            patch.dict(os.environ, {"HOME": tmp}):
        game = SimpleNamespace(name="Starfield")
        done = subprocess.CompletedProcess([], 0, "", "")
        with logs.capture(game, label="Play", log_fn=lambda _m: None), \
                patch("subprocess.run", return_value=done):
            launch._hand_off_to_steam(["wine"], {}, Path(tmp), lambda _m: None)
        text = logs.latest_log(logs.log_directory(game), "umu").read_text()
        assert STEAM_NOTE in text, text


if __name__ == "__main__":
    test_logs_open_one_wine_tab()
    print("✓ the play bar's Logs opens one Wine tab")
    test_wine_tab_title_and_empty_text()
    print("✓ the tab is titled Wine and its empty text doesn't mention Proton")
    test_steam_hand_off_notes_where_the_output_goes()
    print("✓ a Steam hand-off says the game's output goes to Steam")
