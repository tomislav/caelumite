"""
Utils.macos.processes
Find processes by an exact environment entry on macOS (no /proc).

macOS backend for ``Utils.processes.game.matching_pids``, which tracks a
launched game - and stops it - by the marker its process tree inherits.

A game that the bottle's Steam starts inherits Steam's environment, not the
Play session's, and Wine doesn't copy the variables Steam sets on the
Windows side (SteamAppId, ...) into it. Those games are matched by an exe
marker instead (:func:`exe_marker`): a process in the bottle whose Windows
command line runs that exe.
``sysctl(KERN_PROCARGS2)`` returns a process's argv and environment for
processes of the same user; Wine's game processes carry the marker there.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import struct
import subprocess
from pathlib import PureWindowsPath

_CTL_KERN = 1
_KERN_PROCARGS2 = 49

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


def _procargs(pid: int) -> bytes | None:
    mib = (ctypes.c_int * 3)(_CTL_KERN, _KERN_PROCARGS2, pid)
    size = ctypes.c_size_t(0)
    if _libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if _libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return None
    return buf.raw[:size.value]


def _argv_env(pid: int) -> tuple[list[str], set[str]] | None:
    """(argv, environment as ``KEY=VALUE`` strings) of a process.

    KERN_PROCARGS2 layout: int argc, the exec path, NUL padding, argc argv
    strings, then the environment strings, each NUL-terminated.
    """
    raw = _procargs(pid)
    if raw is None or len(raw) < 4:
        return None
    argc = struct.unpack_from("i", raw)[0]
    parts = raw[4:].split(b"\0")
    # parts: exec path, padding empties, argv..., env..., trailing empties
    i = 1
    while i < len(parts) and parts[i] == b"":
        i += 1
    argv = [a.decode(errors="surrogateescape") for a in parts[i:i + argc]]
    env = parts[i + argc:]
    return argv, {item.decode(errors="surrogateescape") for item in env if b"=" in item}


def environ_of(pid: int) -> set[str] | None:
    """The process's environment as a set of ``KEY=VALUE`` strings."""
    info = _argv_env(pid)
    return None if info is None else info[1]


# Launch leases (Utils/processes/leases.py) tell a process from a later one
# with the same pid, and a boot from the next, by these identities.
_KERN_PROC = 14
_KERN_PROC_PID = 1
# struct kinfo_proc on arm64: kp_proc (struct extern_proc) starts with
# p_starttime (timeval: 8-byte seconds, 4-byte microseconds), p_stat is at
# offset 36 and p_pid at 40.
_KINFO_PROC_SIZE = 648
_SZOMB = 5


def boot_identity() -> str:
    """This boot's session UUID (kern.bootsessionuuid)."""
    size = ctypes.c_size_t(0)
    if _libc.sysctlbyname(b"kern.bootsessionuuid", None, ctypes.byref(size), None, 0) != 0:
        raise OSError(ctypes.get_errno(), "sysctl kern.bootsessionuuid failed")
    buf = ctypes.create_string_buffer(size.value)
    if _libc.sysctlbyname(b"kern.bootsessionuuid", buf, ctypes.byref(size), None, 0) != 0:
        raise OSError(ctypes.get_errno(), "sysctl kern.bootsessionuuid failed")
    return buf.value.decode()


def process_identity(pid: int) -> str | None:
    """The process's start time as "seconds.microseconds", or None when
    there's no such process or it's a zombie."""
    mib = (ctypes.c_int * 4)(_CTL_KERN, _KERN_PROC, _KERN_PROC_PID, pid)
    buf = ctypes.create_string_buffer(_KINFO_PROC_SIZE)
    size = ctypes.c_size_t(_KINFO_PROC_SIZE)
    if _libc.sysctl(mib, 4, buf, ctypes.byref(size), None, 0) != 0 or size.value == 0:
        return None
    raw = buf.raw
    seconds, micros = struct.unpack_from("qi", raw, 0)
    stat, found = struct.unpack_from("b", raw, 36)[0], struct.unpack_from("i", raw, 40)[0]
    if found != pid or stat == _SZOMB:
        return None
    return f"{seconds}.{micros:06d}"


EXE_MARKER = "CAELUMITE_EXE="
# The program of a command line: a quoted path; a macOS program (CrossOver's
# Perl wine wrapper, whose arguments name the exe it starts); a Windows path
# up to the first ".exe"; else the first word.
_PROGRAM = re.compile(r'(?i)^\s*(?:"([^"]+)"|(/\S*)|(.*?\.exe)(?=\s|$)|(\S+))')


def exe_marker(bottle_name: str, bottle_path, exe_name: str) -> str:
    """A matching_pids marker for processes in the bottle running *exe_name*."""
    return f"{EXE_MARKER}{bottle_name}|{bottle_path}|{exe_name}"


def _runs_exe(argv: list[str], env: set[str], marker: str) -> bool:
    name, path, exe = marker[len(EXE_MARKER):].split("|", 2)
    if f"CX_BOTTLE={name}" not in env and f"WINEPREFIX={path}" not in env:
        return False
    m = _PROGRAM.match(" ".join(argv))
    program = next((g for g in m.groups() if g), "") if m else ""
    found = PureWindowsPath(program).name.lower()
    want = exe.lower()
    return found == want or found == want.removesuffix(".exe")


def _all_pids() -> list[int] | None:
    try:
        out = subprocess.run(["/bin/ps", "-axo", "pid="], capture_output=True,
                             text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return [int(tok) for tok in out.split() if tok.isdigit()]


def matching_pids(wanted: tuple[str, ...]) -> set[int] | None:
    """Pids whose environment contains any of the exact *wanted* entries.
    None when the process list itself could not be read."""
    pids = _all_pids()
    if pids is None:
        return None
    exes = [w for w in wanted if w.startswith(EXE_MARKER)]
    wanted_set = set(wanted) - set(exes)
    own_pid = os.getpid()
    found: set[int] = set()
    for pid in pids:
        if pid == own_pid:
            continue
        # sysctl refuses processes we may not inspect (other users, SIP).
        info = _argv_env(pid)
        if info is None:
            continue
        argv, env = info
        if not wanted_set.isdisjoint(env) or any(_runs_exe(argv, env, m) for m in exes):
            found.add(pid)
    return found
