"""
Utils.macos.boundary_folders
The file counts on the mod list's Overwrite and Root Folder rows.

The "(N)" after those rows counts the files in their folders
(gui_qt/modlist/data.py count_files_in). Upstream counts every file, so a
folder holding only the hidden restore log (.mm_overwrite_log.txt) shows
"(1)", and Finder's .DS_Store adds another. The file scan already leaves
those out (Utils/filegraph/paths.py); the count leaves out the same names.
"""

from __future__ import annotations

from Utils.filegraph.paths import EXCLUDE_NAMES, is_macos_junk


def counts_as_file(name: str) -> bool:
    """A file or folder named *name* counts in an Overwrite / Root Folder
    count: not Caelumite's bookkeeping and not macOS's (.DS_Store, ._*,
    __MACOSX), the same as for the file scan."""
    return name not in EXCLUDE_NAMES and not is_macos_junk(name)
