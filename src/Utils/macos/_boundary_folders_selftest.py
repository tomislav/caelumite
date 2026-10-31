"""Self-checks for the Overwrite / Root Folder file counts
(Utils/macos/boundary_folders.py and its hook in gui_qt/modlist/data.py
count_files_in).

Run from src/: python -m Utils.macos._boundary_folders_selftest

Uses a temporary folder.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def _make(root: Path, *names: str) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


def test_bookkeeping_and_finder_files_dont_count() -> None:
    from gui_qt.modlist.data import count_files_in
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # What Root_Folder held: the restore log, then Finder's .DS_Store.
        _make(root, ".mm_overwrite_log.txt", ".DS_Store", "._sfse_loader.exe",
              "__MACOSX/sfse_loader.exe", "Data/.DS_Store")
        assert count_files_in(root) == 0, count_files_in(root)


def test_real_files_count() -> None:
    from gui_qt.modlist.data import count_files_in
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make(root, ".mm_overwrite_log.txt", ".DS_Store", "Starfield_10-30-15-39.dmp",
              "Data/SFSE/Plugins/plugin.dll", ".hidden_by_a_mod.ini")
        assert count_files_in(root) == 3, count_files_in(root)


def test_counts_as_file() -> None:
    from Utils.macos.boundary_folders import counts_as_file
    for name in (".mm_overwrite_log.txt", ".DS_Store", "._x.dll", "__MACOSX"):
        assert not counts_as_file(name), name
    for name in ("sfse_loader.exe", ".hidden_by_a_mod.ini", "Data"):
        assert counts_as_file(name), name


if __name__ == "__main__":
    test_bookkeeping_and_finder_files_dont_count()
    print("✓ the restore log and Finder's files don't count")
    test_real_files_count()
    print("✓ real files count, also inside folders and hidden ones a mod wrote")
    test_counts_as_file()
    print("✓ the same names the file scan leaves out are left out")
