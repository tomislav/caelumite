"""
Utils.macos.launch
Runs games and Windows tools inside a game's CrossOver bottle.

Upstream resolves a Proton script plus a prefix for every launch. On macOS
the prefix is the game's bottle (see Utils.macos.crossover.prefix_for_game)
and the "Proton script" is the bottle's CrossOver ``wine`` wrapper, invoked
as ``wine --bottle <name> --no-convert <windows exe> <args>``. Shared code
reaches this module from small darwin branches in:

  * ``Utils.launchers.steam.proton_run_command`` - every command upstream
    builds for a prefix (tools, ``reg add``, wineboot) becomes a bottle
    command;
  * ``Utils.executables.launch.launch_game`` / ``launch_exe_via_proton`` -
    the Play button and Run EXE entries;
  * ``Utils.executables.launch.resolve_tool_prefix`` /
    ``prepare_tool_prefix`` - wizard tools (always the game's bottle);
  * ``Utils.executables.launch.shutdown_prefix_wineserver`` - skipped: a
    bottle's wineserver also serves Steam and the game.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path, PureWindowsPath

from Utils.macos.crossover import (
    Bottle,
    app_for_bottle,
    bottle_for_path,
    prepare_bottle,
    windows_to_host,
    _registry_steam_path,
)

# Env marker: the "Proton script" in this env is a CrossOver wine wrapper and
# CAELUMITE_BOTTLE names the bottle it runs in.
BOTTLE_ENV = "CAELUMITE_BOTTLE"

_PROTON_VERBS = ("run", "runinprefix", "waitforexitandrun")


def _noop_log(_msg: str) -> None:
    pass


# ---------------------------------------------------------------------------
# Paths and commands
# ---------------------------------------------------------------------------

def host_to_windows(bottle: Bottle, path: "Path | str") -> str:
    """Translate a host path to the Windows path the bottle sees it as.

    Picks the drive whose ``dosdevices`` target is the longest prefix of
    *path* (so a game under ``drive_c`` maps to ``C:`` rather than ``Z:``).
    """
    host = Path(os.path.abspath(path))
    best: tuple[int, str, Path] | None = None
    dosdevices = bottle.path / "dosdevices"
    try:
        links = list(dosdevices.iterdir())
    except OSError:
        links = []
    for link in links:
        name = link.name.lower()
        if len(name) != 2 or name[1] != ":":
            continue
        target = windows_to_host(bottle.path, name + "\\")
        if target is None:
            continue
        try:
            rel = host.relative_to(target)
        except ValueError:
            continue
        depth = len(target.parts)
        if best is None or depth > best[0]:
            best = (depth, name.upper(), rel)
    if best is None:
        return str(host)
    _depth, drive, rel = best
    return str(PureWindowsPath(drive + "\\", *rel.parts))


def bottle_command(bottle: Bottle, program: str, args=(), *,
                   wait: bool = True) -> list[str] | None:
    """``wine --bottle <bottle> --no-convert [--no-wait] <program> <args>``.

    *program* is a Windows path or a builtin (``reg``, ``wineboot``).
    Arguments are passed through untouched: upstream already converts any
    path it hands a tool to a Windows path.
    """
    app = app_for_bottle(bottle)
    if app is None:
        return None
    cmd = [str(app.wine), "--bottle", bottle.name, "--no-convert"]
    if not wait:
        cmd.append("--no-wait")
    return cmd + [_quote_safe(program), *(_quote_safe(str(a)) for a in args)]


def _quote_safe(arg: str) -> str:
    """Protect an argument from the wrapper's Windows command-line quoting.

    The wrapper wraps arguments containing whitespace in double quotes, and
    under Windows parsing rules a backslash run before the closing quote
    escapes it: ``"C:\\Game Dir\\"`` became the value ``C:\\Game Dir" /f``,
    swallowing the next arguments (a ``reg add`` then lost its ``/f`` and hung
    on an overwrite prompt). Doubling the trailing run keeps it literal.
    """
    if not any(ch.isspace() for ch in arg):
        return arg
    trailing = len(arg) - len(arg.rstrip("\\"))
    return arg + "\\" * trailing


def exe_command(bottle: Bottle, exe: Path, args=(), *, wait: bool = True) -> list[str] | None:
    return bottle_command(bottle, host_to_windows(bottle, exe), args, wait=wait)


def proton_run_command(args, env: "dict | None") -> list[str] | None:
    """Darwin replacement for ``proton <verb> <program> <args>``.

    The bottle comes from the env's CAELUMITE_BOTTLE, WINEPREFIX or
    STEAM_COMPAT_DATA_PATH. Returns None when no bottle can be resolved.
    """
    env = env or {}
    bottle = None
    for key in ("WINEPREFIX", "STEAM_COMPAT_DATA_PATH"):
        bottle = bottle or bottle_for_path(env.get(key))
    if bottle is None:
        return None
    payload = list(map(str, args))
    if payload and payload[0] in _PROTON_VERBS:
        payload.pop(0)
    if not payload:
        return None
    program, rest = payload[0], payload[1:]
    if os.path.isabs(program):
        program = host_to_windows(bottle, program)
    return bottle_command(bottle, program, rest)


# ---------------------------------------------------------------------------
# Game bottle
# ---------------------------------------------------------------------------

def bottle_for_game(game, log_fn=_noop_log) -> Bottle | None:
    """The game's bottle: its configured prefix, else the bottle its files
    live in. Logs why when there is none."""
    prefix = game.get_prefix_path() if hasattr(game, "get_prefix_path") else None
    game_path = game.get_game_path() if hasattr(game, "get_game_path") else None
    bottle = bottle_for_path(prefix) or bottle_for_path(game_path)
    if bottle is None:
        log_fn("this game is not in a CrossOver bottle - set its prefix to "
               "the bottle in Configure Game, or install the game in "
               "CrossOver first.")
        return None
    if app_for_bottle(bottle) is None:
        log_fn("CrossOver is not installed in /Applications or ~/Applications.")
        return None
    prepare_bottle(bottle.path, log_fn)
    return bottle


def bottle_env(bottle: Bottle, base: "dict | None" = None) -> dict:
    """Environment for a bottle command. WINEPREFIX lets upstream code that
    reads the prefix back out of the env (registry edits, logging) find it."""
    from Utils.environment.xdg import host_env
    env = dict(base) if base is not None else host_env()
    env["WINEPREFIX"] = str(bottle.path)
    env[BOTTLE_ENV] = bottle.name
    return env


def tool_prefix_env(exe: Path, game, log_fn=_noop_log, *, prefix_mode: str = ""):
    """(wine wrapper, bottle path, env) for a wizard tool, in the upstream
    resolve_tool_prefix tuple order. Every tool runs in the game's bottle:
    isolated/shared tool prefixes are not supported on macOS yet."""
    if prefix_mode and prefix_mode != "game":
        log_fn(f"prefix mode '{prefix_mode}' is not available on macOS - "
               "running the tool in the game's CrossOver bottle.")
    bottle = bottle_for_game(game, log_fn)
    if bottle is None:
        return None
    app = app_for_bottle(bottle)
    log_fn(f"using CrossOver bottle '{bottle.name}' ({app.name} {app.version})")
    return app.wine, bottle.path, bottle_env(bottle)


# ---------------------------------------------------------------------------
# Play / Run EXE
# ---------------------------------------------------------------------------

def _steam_exe(bottle: Bottle) -> Path | None:
    reg = _registry_steam_path(bottle)
    roots = [windows_to_host(bottle.path, reg)] if reg else []
    roots += [bottle.drive_c / "Program Files (x86)" / "Steam", bottle.drive_c / "Steam"]
    for root in roots:
        if root is not None and (root / "steam.exe").is_file():
            return root / "steam.exe"
    return None


def script_extender_name(game) -> str:
    """The script extender loader's file name (``sfse_loader.exe``), or ""."""
    if not getattr(game, "supports_script_extender_swap", False):
        return ""
    return getattr(game, "_script_extender_exe", "") or ""


def play_label(game, label: str) -> str:
    """Text shown for a play-bar entry: the script extender loader reads
    "Starfield (SFSE)" (from ``sfse_loader.exe``; SKSE64, F4SE, ... alike).
    The entry's label itself stays the exe name, which keys its saved
    selection and settings."""
    se = script_extender_name(game) if game is not None else ""
    if se and label.lower() == se.lower():
        short = Path(se).stem.lower().removesuffix("_loader").upper()
        return f"{game.name} ({short})"
    return label


def play_menu(game, items: list[str], saved: str | None) -> tuple[list[str], str]:
    """Order and default of the play-bar dropdown on macOS.

    A detected script extender loader is listed first and is the default;
    the game entry starts the game without it. *saved* is the profile's
    explicit choice, the game entry included (see the app.py hook)."""
    se = script_extender_name(game)
    loader = next((i for i in items if se and i.lower() == se.lower()), None)
    if loader is not None:
        items = [loader, *(i for i in items if i != loader)]
    current = saved if saved in items else (loader or game.name)
    return items, current


def _steam_running(bottle: Bottle) -> bool:
    """True when Windows Steam itself is running in *bottle* (not CrossOver's
    wrapper that starts it, whose arguments also name steam.exe)."""
    from Utils.macos.processes import exe_marker, matching_pids

    return bool(matching_pids((exe_marker(bottle.name, bottle.path, "steam.exe"),)))


def _start_steam(bottle: Bottle, steam_exe: Path, log_fn, timeout: float = 90) -> None:
    """Start the bottle's Steam and give it time to sign in (worker thread).

    Started outside the Play session (plain Popen, no launch marker), so
    Steam is not tracked as the game and Stop never terminates it."""
    import subprocess
    import time

    log_fn(f"Play: starting Steam in bottle '{bottle.name}' first ...")
    cmd = bottle_command(bottle, host_to_windows(bottle, steam_exe), ["-silent"],
                         wait=False)
    env = bottle_env(bottle)
    from Utils.processes.game import LAUNCH_ID_ENV
    env.pop(LAUNCH_ID_ENV, None)
    subprocess.Popen(cmd, env=env, cwd=steam_exe.parent,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not _steam_running(bottle):
        time.sleep(1)
    if not _steam_running(bottle):
        log_fn(f"Play: Steam did not start within {timeout:.0f} s - "
               "launching anyway.")
        return
    # Running is not signed in; the client needs a moment before games can
    # check ownership.
    time.sleep(10)


def _ensure_steam(game, bottle: Bottle, log_fn) -> None:
    """Start the bottle's Steam unless it is running. Before a script
    extender loader, which starts the game exe directly: without Steam up,
    the game's Steam check relaunches it through Steam, without the script
    extender. Before a Steam hand-off, so the hand-off doesn't become Steam
    itself (and the Play session doesn't track Steam as the game)."""
    from Utils.executables.launch import effective_steam_id

    steam_exe = _steam_exe(bottle)
    if effective_steam_id(game) and steam_exe and not _steam_running(bottle):
        _start_steam(bottle, steam_exe, log_fn)


def _launch_inputs(game, settings_key: str, exe_name: str, launches_game: bool,
                   log_fn, prefix: str):
    """(args, env updates) as upstream's launch routes build them: the
    saved arguments, plus the game's default arguments (Cyberpunk's
    ``-modded``, ...) when the exe starts the game, plus the variables from
    the saved Launch Options. Wrapper commands there (``%command%``) are not
    supported on macOS and are ignored. None when the arguments don't parse."""
    from Utils.executables.launch import (
        load_exe_args, load_launch_options, parse_launch_options)

    try:
        args = shlex.split(load_exe_args(game, settings_key))
    except ValueError as exc:
        _fail(log_fn, f"invalid launch arguments: {exc}")
        return None
    if launches_game:
        try:
            declared = game.default_launch_args_for_exe(exe_name)
        except AttributeError:
            declared = getattr(game, "default_launch_args", []) or []
        defaults = [str(a) for a in declared if str(a) not in args]
        if defaults:
            log_fn(f"{prefix}: adding default launch args: {' '.join(defaults)}")
            args = defaults + args
    env_updates, rest = parse_launch_options(
        load_launch_options(game, settings_key), ["%cmd%"])
    if "%cmd%" in rest:
        at = rest.index("%cmd%")
        args += rest[at + 1:]   # arguments after %command% still apply
        rest = rest[:at + 1]
    if rest != ["%cmd%"]:
        log_fn(f"{prefix}: wrapper commands in Launch Options are not "
               "supported on macOS; only their variables and arguments are used.")
    return args, env_updates


def _fail(log_fn, reason: str) -> None:
    from Utils.processes import report as launch_report
    log_fn(f"Play: {reason}")
    launch_report.mark_failed(launch_report.actionable(reason))


def launch_exe(exe_path: Path, game, log_fn=_noop_log, *,
               launch_settings_key: "str | None" = None, label: str = "") -> None:
    """Run a Windows exe in the game's bottle and watch it (worker thread)."""
    from Utils.executables.launch import is_game_launch_exe, spawn_process_watched

    bottle = bottle_for_game(game, log_fn)
    if bottle is None:
        _fail(log_fn, "no CrossOver bottle for this game.")
        return
    se = script_extender_name(game)
    is_loader = bool(se) and exe_path.name.lower() == se.lower()
    try:
        launches_game = is_loader or is_game_launch_exe(game, exe_path)
    except Exception:
        launches_game = is_loader
    inputs = _launch_inputs(game, launch_settings_key or exe_path.name,
                            exe_path.name, launches_game, log_fn, "Run EXE")
    if inputs is None:
        return
    args, env_updates = inputs
    if is_loader:
        _ensure_steam(game, bottle, log_fn)
    cmd = exe_command(bottle, exe_path, args)
    label = label or f"Run EXE {exe_path.name}"
    log_fn(f"{label}: {' '.join(shlex.quote(c) for c in cmd)}")
    env = bottle_env(bottle)
    env.update(env_updates)
    spawn_process_watched(cmd, env=env, cwd=exe_path.parent,
                          label=label, log_fn=log_fn)


def launch_game(game, log_fn=_noop_log) -> None:
    """The Play button on macOS (worker thread).

    Launch mode "auto"/"steam" with a Steam app id hands the launch to the
    bottle's Windows Steam (``steam.exe -applaunch``), which the Steam API
    needs; the game is then tracked by the app id Steam gives its processes.
    The game's preferred launch exe or mode "none" runs the exe directly in
    the bottle. A script extender loader is not used here: it is its own
    play-bar entry, run by launch_exe.
    """
    from Utils.executables.launch import (
        effective_steam_id, game_exe_key, load_launch_mode, resolve_game_exe,
        spawn_process_watched,
    )
    from Utils.processes import game as game_process

    bottle = bottle_for_game(game, log_fn)
    if bottle is None:
        _fail(log_fn, "no CrossOver bottle for this game.")
        return
    exe = resolve_game_exe(game)
    key = game_exe_key(game)
    mode = load_launch_mode(game, key)
    inputs = _launch_inputs(game, key, exe.name if exe is not None else "",
                            True, log_fn, "Play")
    if inputs is None:
        return
    args, env_updates = inputs
    env = bottle_env(bottle)
    env.update(env_updates)

    preferred = getattr(game, "preferred_launch_exe", "") or ""
    direct = mode == "none" or (exe is not None and preferred
                                and exe.name.lower() == Path(preferred).name.lower())
    steam_id = effective_steam_id(game)
    steam_exe = _steam_exe(bottle)

    # Bethesda script extenders: upstream swaps the loader in for the game
    # exe, which CrossOver can't run (see the pipeline hook). On macOS the
    # loader is its own play-bar entry instead (play_menu, launch_exe), so
    # the game entry always starts the game without it.
    if not direct and mode in ("auto", "steam") and steam_id and steam_exe:
        # Steam owns the game's process tree; the hand-off below exits once
        # it has passed the request on. Upstream watches the app id Steam
        # stamps on the game's environment, but under Wine that stays on the
        # Windows side - so watch for the game's exe in the bottle instead.
        _ensure_steam(game, bottle, log_fn)
        from Utils.macos.processes import exe_marker
        game_process.arm_external(
            [exe_marker(bottle.name, bottle.path, exe.name)] if exe is not None else [],
            "Steam")
        if env_updates:
            log_fn("Play: Launch Options variables don't reach a game that "
                   "Steam starts; use launch mode None to apply them.")
        cmd = bottle_command(bottle, host_to_windows(bottle, steam_exe),
                             ["-applaunch", steam_id, *args], wait=False)
        log_fn(f"Play: handing off to Steam in bottle '{bottle.name}' "
               f"(app {steam_id})")
        spawn_process_watched(cmd, env=env, cwd=steam_exe.parent,
                              label="Play (Steam in CrossOver)", log_fn=log_fn)
        return
    if exe is None:
        _fail(log_fn, "could not find the game's executable - check the game "
                      "path in Configure Game.")
        return
    log_fn(f"Play: launching {exe.name} in bottle '{bottle.name}'")
    cmd = exe_command(bottle, exe, args)
    spawn_process_watched(cmd, env=env, cwd=exe.parent,
                          label="Play (CrossOver)", log_fn=log_fn)
