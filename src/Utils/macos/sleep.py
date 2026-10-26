"""
Utils.macos.sleep
Keep the Mac awake during long tool runs (macOS backend for
``Utils.processes.sleep.inhibit_sleep``).

``caffeinate -i -w <our pid>`` holds an idle-sleep assertion until it is
terminated or this process exits, so a crash never leaves the Mac awake.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import contextmanager


@contextmanager
def keep_awake(reason: str, log):
    caffeinate = shutil.which("caffeinate") or "/usr/bin/caffeinate"
    try:
        proc = subprocess.Popen(
            [caffeinate, "-i", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        log(f"could not keep the Mac awake ({exc}) - it may sleep during this run.")
        yield False
        return
    try:
        yield True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
