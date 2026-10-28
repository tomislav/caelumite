"""Self-checks for the app update entry points (Utils/macos/menubar.py,
Utils/macos/updates.py).

Run from src/: python -m Utils.macos._updates_selftest

Qt runs offscreen; no update check reaches GitHub.
"""

from __future__ import annotations

import os
import time


def _qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window():
    from PySide6.QtWidgets import QMainWindow

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.checks: list[dict] = []

        def _check_for_app_update(self, **kwargs):
            self.checks.append(kwargs)

    return Window()


def test_menu_has_check_for_updates() -> None:
    from PySide6.QtGui import QAction
    from Utils.macos.menubar import install
    _qt_app()
    window = _window()
    install(window)
    actions = [a for a in window.menuBar().findChildren(QAction)
               if a.text() == "Check for Updates…"]
    assert len(actions) == 1, [a.text() for a in window.menuBar().findChildren(QAction)]
    action = actions[0]
    assert action.menuRole() == QAction.ApplicationSpecificRole
    action.trigger()
    assert window.checks == [{"force_fresh": True, "notify_result": True}], window.checks
    window.deleteLater()


class _Clock:
    """A wall clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def _tick(app, timer, times: int = 3) -> None:
    for _ in range(times):
        timer.timeout.emit()
        app.processEvents()


def test_daily_check_follows_the_wall_clock() -> None:
    from Utils.macos.updates import DAY_SECONDS, start_daily_check
    app = _qt_app()
    window = _window()
    clock = _Clock()
    timer = start_daily_check(window, clock=clock)
    assert timer.parent() is window and timer.isActive()
    _tick(app, timer)
    assert window.checks == []
    # A Mac asleep overnight: a day of wall time, little awake time.
    clock.now += DAY_SECONDS
    _tick(app, timer)
    assert window.checks == [{}], window.checks
    clock.now += DAY_SECONDS - 60
    _tick(app, timer)
    assert window.checks == [{}], window.checks
    clock.now += 120
    _tick(app, timer)
    assert window.checks == [{}, {}], window.checks
    window.deleteLater()


def test_daily_timer_wakes_hourly() -> None:
    from Utils.macos.updates import start_daily_check
    _qt_app()
    window = _window()
    timer = start_daily_check(window)
    assert timer.interval() == 60 * 60 * 1000 and window.checks == []
    window.deleteLater()


def test_daily_check_waits_while_busy() -> None:
    from types import SimpleNamespace
    from Utils.macos.updates import DAY_SECONDS, start_daily_check
    app = _qt_app()
    clock = _Clock()
    for busy in ({"_deploy_running": True}, {"_install_running": True},
                 {"_col_install_running": True}, {"_tool_busy": True},
                 {"_play_session": SimpleNamespace(active=True)}):
        window = _window()
        for name, value in busy.items():
            setattr(window, name, value)
        timer = start_daily_check(window, clock=clock)
        clock.now += DAY_SECONDS
        _tick(app, timer)
        assert window.checks == [], (busy, window.checks)
        for name in busy:
            setattr(window, name, None)
        _tick(app, timer)
        assert window.checks == [{}], (busy, window.checks)
        window.deleteLater()


def test_missing_check_method_is_harmless() -> None:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMainWindow
    from Utils.macos.menubar import install
    from Utils.macos.updates import DAY_SECONDS, start_daily_check
    app = _qt_app()
    window = QMainWindow()
    install(window)
    action = next(a for a in window.menuBar().findChildren(QAction)
                  if a.text() == "Check for Updates…")
    action.trigger()
    clock = _Clock()
    timer = start_daily_check(window, clock=clock)
    clock.now += DAY_SECONDS
    _tick(app, timer)
    window.deleteLater()


def test_notify_setting_label_mentions_no_startup() -> None:
    from Utils.macos.branding import rebrand
    assert rebrand("Notify about new versions on startup") == "Notify about new versions"
    help_text = rebrand("Show a notification when a new version of Amethyst "
                        "is available. You can still check for updates manually "
                        "when this is turned off.")
    assert "once a day" in help_text and "Amethyst" not in help_text, help_text


if __name__ == "__main__":
    test_menu_has_check_for_updates()
    print("✓ the app menu has Check for Updates…, which checks right away")
    test_daily_check_follows_the_wall_clock()
    print("✓ the daily check follows the wall clock, sleep included")
    test_daily_timer_wakes_hourly()
    print("✓ the daily timer wakes every hour")
    test_daily_check_waits_while_busy()
    print("✓ the daily check waits while a game, deploy or install runs")
    test_missing_check_method_is_harmless()
    print("✓ a missing update-check method is harmless")
    test_notify_setting_label_mentions_no_startup()
    print("✓ the notify setting says it covers the daily check")
