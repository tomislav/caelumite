"""Self-checks for waiting on the bottle's Steam (Utils/macos/launch.py).

Run from src/: python -m Utils.macos._launch_selftest

Steam's connection log and login file live in temporary folders; no Steam,
Wine or bottle is started.
"""

from __future__ import annotations

import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Utils.macos import launch
from Utils.processes import game as game_process


def _ts(when: datetime) -> str:
    return when.strftime("[%Y-%m-%d %H:%M:%S]")


def session_start(when: datetime) -> str:
    return (f"{_ts(when)} Client version: 1792618285\n"
            f"{_ts(when)} [Logged Off, 4, 0] [U:1:1] LogOn() called; not connected yet\n")


def connecting(when: datetime) -> str:
    return (f"{_ts(when)} [Connecting, 4, 0] [U:1:1] PingWebSocketCM() starting...\n"
            f"{_ts(when)} [Connected, 4, 0] [U:1:1] Connected\n"
            f"{_ts(when)} [Logging On, 4, 7] [U:1:1] RecvMsgClientLogOnResponse() : [U:1:1] 'OK'\n")


def signed_in(when: datetime) -> str:
    return (f"{_ts(when)} [Logged On, 4, 7] [U:1:1] "
            "RecvMsgClientLogOnResponse() : processing complete\n"
            f"{_ts(when)} [Logged On, 4, 7] [U:1:1] CClientJobGetClientUpdateHosts\n")


def logged_off(when: datetime) -> str:
    return f"{_ts(when)} [Logged Off, 4, 0] [U:1:1] Disconnected\n"


LONG_AGO = datetime(2026, 10, 27, 17, 11, 13)
OLD_SESSION = session_start(LONG_AGO) + connecting(LONG_AGO) + signed_in(LONG_AGO)


class SteamDir:
    """A bottle's Steam folder with its connection log in *tmp*."""

    def __init__(self, tmp: Path, text: str = "", offline: "bool | None" = None) -> None:
        self.exe = tmp / "Steam" / "steam.exe"
        self.log = tmp / "Steam" / "logs" / "connection_log.txt"
        self.log.parent.mkdir(parents=True)
        self.exe.write_bytes(b"")
        if text:
            self.log.write_text(text, encoding="utf-8")
        if offline is not None:
            self.login(offline)

    def login(self, offline: bool) -> None:
        cfg = self.exe.parent / "config"
        cfg.mkdir(exist_ok=True)
        (cfg / "loginusers.vdf").write_text(
            '"users"\n{\n\t"76561197960265729"\n\t{\n'
            '\t\t"AccountName"\t\t"older"\n\t\t"WantsOfflineMode"\t\t"0"\n'
            '\t\t"timestamp"\t\t"1700000000"\n\t}\n'
            '\t"76561197960265730"\n\t{\n'
            '\t\t"AccountName"\t\t"player"\n'
            f'\t\t"WantsOfflineMode"\t\t"{1 if offline else 0}"\n'
            '\t\t"timestamp"\t\t"1793178289"\n\t}\n}\n', encoding="utf-8")

    def append(self, text: str) -> None:
        with self.log.open("a", encoding="utf-8") as fh:
            fh.write(text)

    def append_later(self, text_fn, delay: float = 0.3) -> threading.Thread:
        def later():
            time.sleep(delay)
            self.append(text_fn())
        thread = threading.Thread(target=later, daemon=True)
        thread.start()
        return thread


def _fast():
    """Patch the waits short enough for a test."""
    return (patch.object(launch, "_STEAM_POLL_SECONDS", 0.05),
            patch.object(launch, "_STEAM_SETTLE_SECONDS", 0),
            patch.object(launch, "_STEAM_OFFLINE_SECONDS", 0))


def _bottle(tmp: Path):
    return SimpleNamespace(name="Starfield", path=tmp / "bottle")


def _steam_patches(steam: SteamDir, running, popen=None):
    patches = [
        patch.object(launch, "_steam_exe", return_value=steam.exe),
        patch.object(launch, "_steam_running", side_effect=running),
        patch.object(launch, "bottle_command", return_value=["wine"]),
        patch.object(launch, "host_to_windows", return_value="C:\\Steam\\steam.exe"),
        patch.object(launch, "bottle_env", return_value={}),
        patch("Utils.executables.launch.effective_steam_id", return_value="1716740"),
    ]
    if popen is not None:
        patches.append(patch("subprocess.Popen", side_effect=popen))
    return patches


def _ensure(steam: SteamDir, tmp: Path, running, popen=None, **kwargs):
    logs: list[str] = []
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in (*_fast(), *_steam_patches(steam, running, popen)):
            stack.enter_context(p)
        ok = launch._ensure_steam(object(), _bottle(tmp), logs.append,
                                  "Starfield.exe", **kwargs)
    return ok, logs


# ---- reading the connection log -------------------------------------------

def test_old_session_is_not_signed_in() -> None:
    now = datetime.now().replace(microsecond=0)
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), OLD_SESSION + session_start(now) + connecting(now))
        assert launch._steam_session(steam.log) == (now, False)


def test_new_session_signed_in() -> None:
    now = datetime.now().replace(microsecond=0)
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), OLD_SESSION + session_start(now)
                         + connecting(now) + signed_in(now))
        assert launch._steam_session(steam.log) == (now, True)


def test_disconnect_after_sign_in_is_not_signed_in() -> None:
    now = datetime.now().replace(microsecond=0)
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), session_start(now) + connecting(now)
                         + signed_in(now) + logged_off(now) + connecting(now))
        assert launch._steam_session(steam.log) == (now, False)
        steam.append(signed_in(now))
        assert launch._steam_session(steam.log) == (now, True)


def test_log_without_a_session_start_is_unknown() -> None:
    now = datetime.now()
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), connecting(now) + signed_in(now))
        assert launch._steam_session(steam.log) == (None, False)
        assert launch._steam_session(Path(tmp) / "missing.txt") == (None, False)


def test_only_the_log_tail_is_read() -> None:
    now = datetime.now().replace(microsecond=0)
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), OLD_SESSION * 200 + session_start(now)
                         + connecting(now) + signed_in(now))
        with patch.object(launch, "_STEAM_LOG_TAIL", 2048):
            assert launch._steam_session(steam.log) == (now, True)


def test_offline_mode_follows_the_most_recent_user() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), offline=True)
        assert launch._steam_offline(steam.exe)
        steam.login(offline=False)
        assert not launch._steam_offline(steam.exe)
    with tempfile.TemporaryDirectory() as tmp:
        assert not launch._steam_offline(SteamDir(Path(tmp)).exe)


# ---- starting Steam -------------------------------------------------------

def test_cold_start_waits_for_the_new_session() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), OLD_SESSION, offline=False)
        writers: list[threading.Thread] = []

        def popen(*_a, **_k):
            now = datetime.now()
            steam.append(session_start(now) + connecting(now))
            writers.append(steam.append_later(lambda: signed_in(datetime.now())))

        ok, logs = _ensure(steam, Path(tmp), lambda _b: bool(writers), popen)
        assert ok and writers and not writers[0].is_alive()
        assert any("signed in after" in line for line in logs), logs


def test_cold_start_launches_anyway_when_steam_never_signs_in() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), OLD_SESSION, offline=False)
        started: list[bool] = []

        def popen(*_a, **_k):
            started.append(True)
            steam.append(session_start(datetime.now()))

        ok, logs = _ensure(steam, Path(tmp), lambda _b: bool(started), popen,
                           timeout=0.3)
        assert ok
        assert any("didn't sign in" in line and "launching anyway" in line
                   for line in logs), logs


def test_cold_start_accepts_a_steam_opened_just_before() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        just_now = datetime.now() - timedelta(seconds=5)
        steam = SteamDir(Path(tmp), session_start(just_now) + connecting(just_now)
                         + signed_in(just_now), offline=False)
        launched: list[bool] = []
        started = time.monotonic()
        ok, logs = _ensure(steam, Path(tmp), lambda _b: bool(launched),
                           lambda *_a, **_k: launched.append(True), timeout=5)
        assert ok and time.monotonic() - started < 2, logs


def test_cold_start_in_offline_mode_doesnt_wait_for_sign_in() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), OLD_SESSION, offline=True)
        launched: list[bool] = []
        started = time.monotonic()
        ok, logs = _ensure(steam, Path(tmp), lambda _b: bool(launched),
                           lambda *_a, **_k: launched.append(True), timeout=5)
        assert ok and time.monotonic() - started < 2
        assert any("offline mode" in line for line in logs), logs


# ---- Steam already running -------------------------------------------------

def test_running_steam_still_signing_in_is_waited_for() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        now = datetime.now()
        steam = SteamDir(Path(tmp), OLD_SESSION + session_start(now) + connecting(now),
                         offline=False)
        writer = steam.append_later(lambda: signed_in(datetime.now()))
        ok, logs = _ensure(steam, Path(tmp), lambda _b: True)
        assert ok and not writer.is_alive()
        assert any("still signing in" in line for line in logs), logs


def test_running_steam_signed_in_isnt_waited_for() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        now = datetime.now()
        steam = SteamDir(Path(tmp), session_start(now) + connecting(now)
                         + signed_in(now), offline=False)
        ok, logs = _ensure(steam, Path(tmp), lambda _b: True)
        assert ok and logs == [], logs


def test_running_steam_offline_isnt_waited_for() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        now = datetime.now()
        steam = SteamDir(Path(tmp), session_start(now), offline=True)
        started = time.monotonic()
        ok, logs = _ensure(steam, Path(tmp), lambda _b: True, timeout=5)
        assert ok and time.monotonic() - started < 1 and logs == [], logs


def test_running_steam_stuck_signed_out_isnt_waited_for() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        hour_ago = datetime.now() - timedelta(hours=1)
        steam = SteamDir(Path(tmp), session_start(hour_ago) + connecting(hour_ago),
                         offline=False)
        started = time.monotonic()
        ok, logs = _ensure(steam, Path(tmp), lambda _b: True, timeout=5)
        assert ok and time.monotonic() - started < 1
        assert any("isn't signed in" in line for line in logs), logs


def test_running_steam_without_a_session_start_isnt_waited_for() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        steam = SteamDir(Path(tmp), connecting(datetime.now()), offline=False)
        started = time.monotonic()
        ok, logs = _ensure(steam, Path(tmp), lambda _b: True, timeout=5)
        assert ok and time.monotonic() - started < 1 and logs == [], logs


# ---- the Play session during the wait --------------------------------------

def test_wait_shows_the_session_running_and_stop_cancels_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        now = datetime.now()
        steam = SteamDir(Path(tmp), session_start(now) + connecting(now), offline=False)
        session = game_process.LaunchSession("Starfield (SFSE)")
        states: list[bool] = []
        session.set_state_callback(states.append)
        result: dict = {}

        def play():
            with game_process.bind(session):
                result["ok"], result["logs"] = _ensure(
                    steam, Path(tmp), lambda _b: True, timeout=10)

        worker = threading.Thread(target=play)
        worker.start()
        deadline = time.monotonic() + 3
        while not session.active and time.monotonic() < deadline:
            time.sleep(0.02)
        assert session.active and states == [True], states
        assert session.stop()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert result["ok"] is False
        assert any("stopped while waiting for Steam" in line
                   for line in result["logs"]), result["logs"]


def test_launch_exe_stops_when_play_was_stopped() -> None:
    spawned: list = []
    with (patch.object(launch, "bottle_for_game",
                       return_value=SimpleNamespace(name="Starfield", path=Path("/x"))),
          patch.object(launch, "script_extender_name", return_value="sfse_loader.exe"),
          patch.object(launch, "_launch_inputs", return_value=([], {})),
          patch.object(launch, "_ensure_steam", return_value=False),
          patch("Utils.executables.launch.resolve_game_exe",
                return_value=Path("/x/Starfield.exe")),
          patch("Utils.executables.launch.spawn_process_watched",
                side_effect=lambda *a, **k: spawned.append(a))):
        launch.launch_exe(Path("/x/sfse_loader.exe"), object())
    assert spawned == []


if __name__ == "__main__":
    test_old_session_is_not_signed_in()
    print("✓ a previous session's sign-in doesn't count")
    test_new_session_signed_in()
    print("✓ a new session's sign-in is found")
    test_disconnect_after_sign_in_is_not_signed_in()
    print("✓ a disconnect after signing in isn't signed in, a reconnect is")
    test_log_without_a_session_start_is_unknown()
    print("✓ a log without a session start is unknown")
    test_only_the_log_tail_is_read()
    print("✓ only the end of the log is read")
    test_offline_mode_follows_the_most_recent_user()
    print("✓ offline mode follows the most recent user")
    test_cold_start_waits_for_the_new_session()
    print("✓ starting Steam waits for its new session to sign in")
    test_cold_start_launches_anyway_when_steam_never_signs_in()
    print("✓ a Steam that never signs in still launches the game")
    test_cold_start_accepts_a_steam_opened_just_before()
    print("✓ a Steam opened just before Play counts")
    test_cold_start_in_offline_mode_doesnt_wait_for_sign_in()
    print("✓ offline mode doesn't wait for a sign-in")
    test_running_steam_still_signing_in_is_waited_for()
    print("✓ a running Steam that is still signing in is waited for")
    test_running_steam_signed_in_isnt_waited_for()
    print("✓ a signed-in Steam isn't waited for")
    test_running_steam_offline_isnt_waited_for()
    print("✓ a running Steam in offline mode isn't waited for")
    test_running_steam_stuck_signed_out_isnt_waited_for()
    print("✓ a Steam that has been signed out for long isn't waited for")
    test_running_steam_without_a_session_start_isnt_waited_for()
    print("✓ a log without a session start isn't waited for")
    test_wait_shows_the_session_running_and_stop_cancels_it()
    print("✓ the wait shows Stop, and Stop cancels the launch")
    test_launch_exe_stops_when_play_was_stopped()
    print("✓ the loader doesn't run after Stop")
