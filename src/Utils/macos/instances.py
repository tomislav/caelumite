"""
Utils.macos.instances
Other running Caelumite instances, found with ``ps`` (macOS has no /proc).

macOS backend for ``Utils.processes.instances``. An instance is identified
by pid plus start time, so a recycled pid is never signalled by mistake.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

_COMMAND = re.compile(r"(?i)python[^/\s]*\s.*\brun_qt\.py(\s|$)")


def _scan() -> list[tuple[int, int]]:
    """(pid, start epoch) of this user's other run_qt.py processes."""
    try:
        result = subprocess.run(
            ["ps", "-axww", "-o", "pid=,uid=,lstart=,args="],
            capture_output=True, text=True, timeout=5,
            env={"LC_ALL": "C", "PATH": "/bin:/usr/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Could not list processes: {exc}") from exc
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "ps failed")
    own_pid, own_uid = os.getpid(), os.getuid()
    found = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        pid, uid = int(parts[0]), int(parts[1])
        if pid == own_pid or uid != own_uid:
            continue
        # Paths may contain spaces, so match the whole command line:
        # a python interpreter running run_qt.py.
        if not _COMMAND.search(parts[7]):
            continue
        try:
            started = int(time.mktime(time.strptime(" ".join(parts[2:7]),
                                                    "%a %b %d %H:%M:%S %Y")))
        except ValueError:
            continue
        found.append((pid, started))
    return found


def running_instances(instance_cls) -> list:
    return sorted((instance_cls(pid, started) for pid, started in _scan()),
                  key=lambda item: item.pid)


def signal_instances(instances, sig: int) -> None:
    live = set(_scan())
    failed = []
    for item in instances:
        if (item.pid, item.started) not in live:
            continue
        try:
            os.kill(item.pid, sig)
        except ProcessLookupError:
            continue
        except OSError:
            failed.append(str(item.pid))
    if failed:
        raise RuntimeError("Could not terminate Caelumite process(es) " + ", ".join(failed))
