"""
Utils.macos.registry
Wine DLL overrides for CrossOver bottles, written through the bottle's Wine.

Upstream edits the prefix's ``user.reg`` file directly. That's safe for a
Proton prefix nobody is using, but a CrossOver bottle often has Wine running
- Steam lives in it - and Wine rewrites ``user.reg`` from memory when it
shuts down, dropping a direct edit. ``reg import`` talks to the running Wine
instead (or starts it), so the change sticks and applies at once.
"""

from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path

from Utils.macos.crossover import Bottle

_KEY = r"HKEY_CURRENT_USER\Software\Wine\DllOverrides"
_SECTION = re.compile(r"^\[Software\\\\Wine\\\\DllOverrides\]", re.IGNORECASE)
_VALUE = re.compile(r'^"([^"]+)"="([^"]*)"')


def current_overrides(bottle: Bottle) -> dict[str, str]:
    """The overrides recorded in the bottle's user.reg (lowercase names)."""
    try:
        lines = (bottle.path / "user.reg").read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    found: dict[str, str] = {}
    inside = False
    for line in lines:
        if line.startswith("["):
            inside = bool(_SECTION.match(line))
            continue
        if inside:
            m = _VALUE.match(line)
            if m:
                found[m.group(1).lower()] = m.group(2)
    return found


def _import(bottle: Bottle, body: list[str], log) -> bool:
    """Import *body* (lines under the DllOverrides key) with ``reg import``."""
    from Utils.macos.launch import bottle_command, bottle_env

    temp = bottle.drive_c / "windows" / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    reg_file = temp / f"caelumite-{uuid.uuid4().hex[:8]}.reg"
    text = "\r\n".join(["Windows Registry Editor Version 5.00", "",
                        f"[{_KEY}]", *body, "", ""])
    try:
        # reg import reads Version 5.00 files as UTF-16 LE with a BOM.
        reg_file.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
        cmd = bottle_command(bottle, "reg",
                             ["import", rf"C:\windows\temp\{reg_file.name}"])
        if cmd is None:
            log("Wine DLL overrides: CrossOver is not installed.")
            return False
        result = subprocess.run(cmd, env=bottle_env(bottle), capture_output=True,
                                text=True, timeout=180, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"Wine DLL overrides: reg import failed: {exc}")
        return False
    finally:
        reg_file.unlink(missing_ok=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
        log(f"Wine DLL overrides: reg import exited {result.returncode}: "
            f"{' '.join(detail)}")
        return False
    return True


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def apply_dll_overrides(bottle: Bottle, overrides: dict[str, str], log) -> bool:
    current = current_overrides(bottle)
    changes = {dll: value for dll, value in overrides.items()
               if current.get(dll.lower()) != value}
    if not changes:
        log("  DLL overrides already set correctly; skipping write.")
        return True
    ok = _import(bottle, [f'"{_quote(d)}"="{_quote(v)}"'
                          for d, v in sorted(changes.items())], log)
    if ok:
        for dll, value in sorted(changes.items()):
            log(f"  DLL override set: {dll} = {value}")
    return ok


def remove_dll_overrides(bottle: Bottle, dlls, log) -> bool:
    # Not filtered by user.reg: Wine writes the file lazily, so a value it
    # already holds may not be on disk yet. Deleting an absent value is a no-op.
    names = sorted(set(dlls))
    if not names:
        return True
    ok = _import(bottle, [f'"{_quote(d)}"=-' for d in names], log)
    if ok:
        for dll in names:
            log(f"  DLL override removed: {dll}")
    return ok
