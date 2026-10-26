"""
Utils.macos.processes
Find processes by an exact environment entry on macOS (no /proc).

macOS backend for ``Utils.processes.game.matching_pids``, which tracks a
launched game - and stops it - by the marker its process tree inherits.
``sysctl(KERN_PROCARGS2)`` returns a process's argv and environment for
processes of the same user; Wine's game processes carry the marker there.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import struct
import subprocess

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


def environ_of(pid: int) -> set[str] | None:
    """The process's environment as a set of ``KEY=VALUE`` strings.

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
    env = parts[i + argc:]
    return {item.decode(errors="surrogateescape") for item in env if b"=" in item}


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
    wanted_set = set(wanted)
    own_pid = os.getpid()
    found: set[int] = set()
    for pid in pids:
        if pid == own_pid:
            continue
        # sysctl refuses processes we may not inspect (other users, SIP).
        env = environ_of(pid)
        if env is not None and not wanted_set.isdisjoint(env):
            found.add(pid)
    return found
