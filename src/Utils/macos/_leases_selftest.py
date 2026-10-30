"""Self-checks for the launch leases on macOS (Utils/processes/leases.py
through Utils/macos/processes.py): no /proc, so the boot and process
identities come from sysctl.

Run from src/: python -m Utils.macos._leases_selftest

Starts two short-lived child processes; writes only to a temporary folder.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def test_boot_identity_is_stable() -> None:
    from Utils.processes.leases import boot_identity
    first = boot_identity()
    assert first and first == boot_identity(), first


def test_process_identity_names_one_process() -> None:
    from Utils.processes.leases import process_identity
    mine = process_identity(os.getpid())
    assert mine and mine == process_identity(os.getpid()), mine
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        other = process_identity(child.pid)
        assert other and other != mine, (mine, other)
    finally:
        child.kill()
        child.wait()
    assert process_identity(child.pid) is None


def test_zombie_has_no_identity() -> None:
    from Utils.processes.leases import process_identity
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    deadline = time.time() + 5
    # Not waited for yet: it exits and stays a zombie.
    while process_identity(child.pid) is not None and time.time() < deadline:
        time.sleep(0.05)
    try:
        assert process_identity(child.pid) is None
    finally:
        child.wait()


def test_launch_record_round_trip() -> None:
    from types import SimpleNamespace
    from Utils.processes.leases import active_launches, process_identity, save_launch
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        identity = {"markers": [], "startup_deadline": 0,
                    "roots": {str(os.getpid()): process_identity(os.getpid())}}
        game = SimpleNamespace(game_id="starfield", name="Starfield")
        save_launch(folder, "abc", game, ["game:starfield"], identity)
        found = active_launches(folder, ["game:starfield"])
        assert [f.get("id") for f in found] == ["abc"], found


if __name__ == "__main__":
    test_boot_identity_is_stable()
    print("✓ the boot identity is the same for the whole boot")
    test_process_identity_names_one_process()
    print("✓ a process identity tells processes apart and ends with the process")
    test_zombie_has_no_identity()
    print("✓ a zombie has no identity")
    test_launch_record_round_trip()
    print("✓ a saved launch record is found while its process runs")
