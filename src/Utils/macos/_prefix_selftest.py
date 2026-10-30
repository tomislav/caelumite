"""Self-checks for "is the bottle in use" on macOS (Utils/wine/repair.py
prefix_usage through Utils/macos/processes.py bottle_usage).

A CrossOver bottle keeps Wine's own services and the bottle's Steam client
running after a game exits; tools like xEdit and the registry repairs may
still run then. Games and other Windows programs in the bottle count.

Run from src/: python -m Utils.macos._prefix_selftest

Compiles a tiny sleeping program (Xcode's cc) and starts it with command
lines that look like Wine processes' and whose WINEPREFIX names a temporary folder.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path


_SLEEPER: Path | None = None


def _sleeper() -> Path:
    """A tiny sleeping program. Not /bin/sleep (macOS hides the environment
    of its own binaries) and not Python (Homebrew's re-executes itself and
    loses argv[0])."""
    global _SLEEPER
    if _SLEEPER is None:
        folder = Path(tempfile.mkdtemp())
        _SLEEPER = folder / "sleeper"
        subprocess.run(["cc", "-x", "c", "-", "-o", str(_SLEEPER)], check=True,
                       input=b"#include <unistd.h>\nint main(void){sleep(30);return 0;}\n")
    return _SLEEPER


def _start(command_line: str, prefix: Path) -> subprocess.Popen:
    env = {**os.environ, "WINEPREFIX": str(prefix)}
    return subprocess.Popen([command_line], executable=_sleeper(), env=env)


def _usage(command_lines: list[str]) -> tuple[set[int] | None, list[int]]:
    from Utils.wine.repair import prefix_usage
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp).resolve()
        procs = [_start(line, prefix) for line in command_lines]
        try:
            time.sleep(0.3)   # let exec -a take effect
            return prefix_usage(prefix), [p.pid for p in procs]
        finally:
            for p in procs:
                p.kill()
                p.wait()


STEAM = r"C:\Program Files (x86)\Steam"


def test_steam_and_wine_services_dont_count() -> None:
    used, _pids = _usage([
        rf"{STEAM}\steam.exe -applaunch 1716740",
        rf"{STEAM}\bin\cef\cef.win7x64\steamwebhelper.exe --type=renderer",
        r"C:\windows\system32\services.exe",
        r"C:\windows\system32\winedevice.exe",
        "/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wineserver",
    ])
    assert used == set(), used


def test_games_and_tools_count() -> None:
    used, pids = _usage([
        rf"{STEAM}\steamapps\common\Starfield\Starfield.exe",
        r"C:\Modding\SF1Edit\SF1Edit.exe -sf1",
        rf"{STEAM}\steam.exe",
    ])
    assert used == set(pids[:2]), (used, pids)


def test_other_bottles_dont_count() -> None:
    from Utils.wine.repair import prefix_usage
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        proc = _start(r"C:\Games\Other.exe", Path(b).resolve())
        try:
            time.sleep(0.3)
            assert prefix_usage(Path(a).resolve()) == set()
        finally:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    test_steam_and_wine_services_dont_count()
    print("✓ the bottle's Steam and Wine's services don't make it busy")
    test_games_and_tools_count()
    print("✓ a game or tool running in the bottle makes it busy")
    test_other_bottles_dont_count()
    print("✓ programs in other bottles don't count")
