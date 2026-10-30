"""Self-checks for "is the bottle in use" on macOS.

Tools (xEdit, QuickAutoClean, the LOD tools, Wrye Bash: Utils/bethesda/
xedit_run.py _check_prefix) may run while the bottle's Steam client and
Wine's services keep running after a game; a game or other program in the
bottle still blocks them (Utils/macos/processes.py tool_usage). Registry
repairs and installers keep upstream's strict check (Utils/wine/repair.py
prefix_usage): any process in the bottle, Steam included, because a running
wineserver delays their registry writes.

Run from src/: python -m Utils.macos._prefix_selftest

Compiles a tiny sleeping program (Xcode's cc) and starts it with command
lines that look like Wine processes', with WINEPREFIX naming a temporary
folder.
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


def _start(argv: list[str], prefix: Path | None, **extra: str) -> subprocess.Popen:
    env = {**os.environ, **extra}
    if prefix is not None:
        env["WINEPREFIX"] = str(prefix)
    return subprocess.Popen(argv, executable=_sleeper(), env=env)


def _running(argvs: list[list[str]], check):
    """check(prefix) while processes with *argvs* run in a temporary bottle;
    returns (its result, their pids)."""
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp).resolve()
        procs = [_start(argv, prefix) for argv in argvs]
        try:
            time.sleep(0.3)
            return check(prefix), [p.pid for p in procs]
        finally:
            for p in procs:
                p.kill()
                p.wait()


def _tool_usage(prefix):
    from Utils.macos.processes import tool_usage
    return tool_usage(prefix)


def _strict_usage(prefix):
    from Utils.wine.repair import prefix_usage
    return prefix_usage(prefix)


STEAM = r"C:\Program Files (x86)\Steam"
CROSSOVER = "/Applications/CrossOver.app/Contents/SharedSupport/CrossOver"
BACKGROUND = [
    [rf"{STEAM}\steam.exe", "-applaunch", "1716740"],
    [rf"{STEAM}\bin\cef\cef.win7x64\steamwebhelper.exe", "--type=renderer"],
    [rf"{STEAM}\GameOverlayUI.exe", "-pid", "4242"],
    [r"C:\windows\system32\services.exe"],
    [r"C:\windows\system32\winedevice.exe"],
    [r"C:\windows\explorer.exe", "/desktop"],
    [f"{CROSSOVER}/bin/wineserver"],
    # The wrapper is a Perl script (#!/usr/bin/perl): its path is argv[1].
    ["/usr/bin/perl", f"{CROSSOVER}/bin/wine", "--bottle", "Starfield", "steam.exe"],
]


def test_tools_ignore_steam_and_wine_services() -> None:
    used, _pids = _running(BACKGROUND, _tool_usage)
    assert used == set(), used


def test_tools_wait_for_games_and_programs() -> None:
    used, pids = _running([
        [rf"{STEAM}\steamapps\common\Starfield\Starfield.exe"],
        [r"C:\Modding\SF1Edit\SF1Edit.exe", "-sf1"],
        [r"C:\windows\regedit.exe"],
        [r"C:\windows\system32\msiexec.exe", "/i", "setup.msi"],
        [r"C:\windows\system32\cmd.exe", "/c", "patch.bat"],
        [r"C:\windows\system32\wineboot.exe", "--update"],
        ["/Users/someone/Tools/helper", "--run"],
        [rf"{STEAM}\steam.exe"],
    ], _tool_usage)
    assert used == set(pids[:7]), (used, pids)


def test_repairs_count_every_process() -> None:
    used, pids = _running(BACKGROUND[:3], _strict_usage)
    assert used == set(pids), (used, pids)


def test_xedit_runs_next_to_steam() -> None:
    from Utils.bethesda.xedit_run import _check_prefix
    from Utils.bethesda.tool_run import ToolRunError

    def check(prefix):
        try:
            _check_prefix({"prefix_path": str(prefix), "compat_data": str(prefix)}, "")
            return "ran"
        except ToolRunError as exc:
            return exc.name

    assert _running(BACKGROUND[:1], check)[0] == "ran"
    assert _running([[rf"{STEAM}\steamapps\common\Starfield\Starfield.exe"]],
                    check)[0] == "wine_prefix_in_use"


def test_blocked_tools_name_the_programs() -> None:
    from Utils.bethesda.xedit_run import _check_prefix
    from Utils.bethesda.tool_run import ToolRunError

    def check(prefix):
        try:
            _check_prefix({"prefix_path": str(prefix), "compat_data": str(prefix)}, "")
            return ""
        except ToolRunError as exc:
            return str(exc)

    message = _running([[r"C:\Modding\SF1Edit\SF1Edit.exe"]], check)[0]
    assert "SF1Edit.exe" in message, message


def test_bottle_found_through_a_linked_bottles_folder() -> None:
    # Bottles moved to another disk and linked back: the resolved prefix a
    # tool passes still finds its bottle, so CX_BOTTLE=<name> counts.
    from unittest.mock import patch
    from Utils.macos.processes import bottle_markers
    with tempfile.TemporaryDirectory() as tmp:
        real = Path(tmp).resolve() / "Disk" / "Bottles"
        bottle = real / "Starfield"
        (bottle / "drive_c").mkdir(parents=True)
        (bottle / "cxbottle.conf").write_text("[Bottle]\n")
        (bottle / "pfx").symlink_to(bottle)
        link = Path(tmp).resolve() / "Bottles"
        link.symlink_to(real)
        with patch.dict(os.environ, {"CX_BOTTLE_PATH": str(link)}):
            for prefix in (link / "Starfield", link / "Starfield" / "pfx",
                           (link / "Starfield" / "pfx").resolve()):
                assert "CX_BOTTLE=Starfield" in bottle_markers(prefix), prefix
            assert not any(m.startswith("CX_BOTTLE=") for m in bottle_markers(Path(tmp)))


def test_bottle_name_alone_counts() -> None:
    # A process CrossOver marks only with CX_BOTTLE=<name>.
    from unittest.mock import patch
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp).resolve()
        proc = _start([r"C:\Games\Game.exe"], None, CX_BOTTLE="TestBottle")
        try:
            time.sleep(0.3)
            with patch("Utils.macos.crossover.bottle_for_path",
                       return_value=SimpleNamespace(name="TestBottle")):
                assert _tool_usage(prefix) == {proc.pid}
                assert _strict_usage(prefix) == {proc.pid}
        finally:
            proc.kill()
            proc.wait()


class _Game:
    """Just enough of a game for the registry repair's locks."""
    name = "Test"
    game_id = "test"

    def __init__(self, root: Path, prefix: Path):
        self.root, self.prefix = root, prefix

    def get_prefix_path(self):
        return self.prefix

    def __getattr__(self, name):
        if name.startswith("get_"):
            return lambda *args, **kwargs: self.root / name
        raise AttributeError(name)


def test_repairs_say_to_quit_the_bottles_steam() -> None:
    from unittest.mock import patch
    from Utils.wine.repair import PrefixRepairError, prefix_repair_operation

    with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home}):
        def check(prefix):
            (prefix / "drive_c").mkdir()
            for hive in ("user.reg", "system.reg"):
                (prefix / hive).write_text("")
            try:
                with prefix_repair_operation(_Game(Path(home), prefix)):
                    return "ran"
            except PrefixRepairError as exc:
                return exc.name, str(exc)

        result = _running(BACKGROUND[:1], check)[0]
    assert result[0] == "wine_prefix_in_use", result
    assert "steam.exe" in result[1] and "Force Quit" in result[1], result


def test_messages_name_what_can_be_closed() -> None:
    # Wine's services and CrossOver's own programs are summed up; the
    # wrapper is named by the exe it starts, never as "perl".
    from Utils.macos.processes import busy_message
    message, _pids = _running(BACKGROUND, lambda prefix: busy_message(_strict_usage(prefix),
                                                                       steam=True))
    assert "steam.exe" in message and "GameOverlayUI.exe" in message, message
    assert "Wine services" in message, message
    names = message.split("first: ", 1)[1].split(". ", 1)[0].rstrip(".").split(", ")
    for hidden in ("perl", "wineserver", "services.exe", "explorer.exe", "winedevice.exe"):
        assert hidden not in names, (hidden, message)


def test_other_bottles_dont_count() -> None:
    with tempfile.TemporaryDirectory() as other:
        proc = _start([r"C:\Games\Other.exe"], Path(other).resolve())
        try:
            time.sleep(0.3)
            with tempfile.TemporaryDirectory() as tmp:
                assert _tool_usage(Path(tmp).resolve()) == set()
                assert _strict_usage(Path(tmp).resolve()) == set()
        finally:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    test_tools_ignore_steam_and_wine_services()
    print("✓ tools may run while the bottle's Steam and Wine's services do")
    test_tools_wait_for_games_and_programs()
    print("✓ a game, tool, regedit, installer or macOS program in the bottle blocks tools")
    test_repairs_count_every_process()
    print("✓ registry repairs and installers wait for every process, Steam included")
    test_xedit_runs_next_to_steam()
    print("✓ xEdit's prefix check uses the tool rule")
    test_blocked_tools_name_the_programs()
    print("✓ a blocked tool names the programs to close")
    test_bottle_found_through_a_linked_bottles_folder()
    print("✓ a bottle is found through a linked Bottles folder")
    test_messages_name_what_can_be_closed()
    print("✓ messages name what can be closed and sum up Wine's services")
    test_bottle_name_alone_counts()
    print("✓ a process marked only with the bottle's name counts")
    test_repairs_say_to_quit_the_bottles_steam()
    print("✓ a registry repair blocked by the bottle's Steam says how to quit it")
    test_other_bottles_dont_count()
    print("✓ programs in other bottles don't count")
