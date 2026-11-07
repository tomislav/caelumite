"""
Utils.macos.launch_logs
The play bar's Logs on macOS.

Upstream opens a UMU and a Proton tab with the latest launch's logs. CrossOver
has neither: launches that run an exe in the bottle (a script extender, Run
EXE, a game launched by its exe) send Wine's output to the UMU file, so that
file is shown as one "Wine" tab and the always-empty Proton tab is left out.
A game Play hands to the bottle's Steam runs under Steam, so its own output
isn't captured; the log says so.
"""

from __future__ import annotations

# The launch logs the play bar opens (Utils/executables/logs.py kinds).
KINDS = ("umu",)

STEAM_NOTE = ("Play handed the game to the bottle's Steam: the game's own "
              "output goes to Steam and isn't captured here.")


def tab_title(label: str) -> str:
    return f"Wine — {label}"


def empty_text(editor) -> str:
    return editor.tr("No Wine output is available for the latest launch.\n"
                     "Press Play to capture it.")


def prune_launch_logs(cutoff: float) -> None:
    """Remove the launch logs of a game, profile or exe not launched since
    *cutoff* (a time.time() value), like old session logs. Best-effort."""
    import shutil
    from Utils.macos.app import config_dir
    try:
        folders = list((config_dir() / "logs" / "launch").iterdir())
    except OSError:
        return
    for folder in folders:
        try:
            if (folder.is_dir() and not folder.is_symlink()
                    and folder.stat().st_mtime < cutoff):
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            continue


def note_steam_hand_off() -> None:
    """Add STEAM_NOTE to the current launch's log (during a Play capture)."""
    from Utils.executables import logs
    try:
        output = logs.open_output()
        if output is None:
            return
        with output:
            output.write((STEAM_NOTE + "\n").encode("utf-8"))
    except OSError:
        pass
