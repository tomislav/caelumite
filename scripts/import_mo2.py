#!/usr/bin/env python3
"""Import a Mod Organizer 2 instance into a Caelumite game.

Caelumite stores mods the way MO2 does (one folder per mod, MO2's
modlist.txt / plugins.txt / loadorder.txt formats, meta.ini for Nexus
info), so an import is a copy:

  * every MO2 mod folder is copied into the game's staging folder as an
    APFS clone (cp -c): instant, no extra disk space until a file changes,
    and fully independent of MO2 - MO2 is never modified;
  * MO2's overwrite folder is cloned into Caelumite's, without replacing
    files already there;
  * the MO2 profile's load-order files replace the Caelumite profile's,
    after a backup into <profile>/backups/; separators are moved to the
    front of their blocks, the order Caelumite reads them in.

Mods whose folder name already exists in Caelumite are skipped (listed at
the end). Close Caelumite before running it.

Usage:
  .venv/bin/python scripts/import_mo2.py MO2_INSTANCE CAELUMITE_GAME_ROOT \
      [--mo2-profile Default] [--profile default] [--dry-run]

  CAELUMITE_GAME_ROOT is the folder holding mods/, overwrite/ and profiles/
  (e.g. ~/Games/Caelumite/Starfield).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROFILE_FILES = ("modlist.txt", "plugins.txt", "loadorder.txt")


def mo2_dirs(instance: Path) -> tuple[Path, Path, Path]:
    """(mods, overwrite, profiles) of an MO2 instance; refuses relocated ones."""
    ini = instance / "ModOrganizer.ini"
    if not ini.is_file():
        raise SystemExit(f"error: {ini} not found - is this an MO2 instance?")
    text = ini.read_text(encoding="utf-8", errors="replace")
    for key in ("base_directory", "mod_directory", "overwrite_directory",
                "profiles_directory"):
        if re.search(rf"^{key}=\S", text, re.MULTILINE):
            raise SystemExit(f"error: this instance sets {key}; relocated MO2 "
                             "folders aren't supported by this script yet.")
    return instance / "mods", instance / "overwrite", instance / "profiles"


PARTIAL = ".caelumite-partial"


def clone(src: Path, dest: Path) -> None:
    """APFS clone of a file or folder tree (cp -c falls back to a copy on
    other filesystems). Copies to a temporary name first and renames it into
    place, so an interrupted copy never looks like a finished one."""
    tmp = dest.with_name(dest.name + PARTIAL)
    remove(tmp)
    try:
        subprocess.run(["cp", "-c", "-R", "-p", str(src), str(tmp)], check=True)
        tmp.rename(dest)
    except BaseException:
        remove(tmp)
        raise


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def remove_partials(root: Path, recursive: bool) -> int:
    """Delete copies a killed run left behind (see clone)."""
    pattern = f"*{PARTIAL}"
    found = (list(root.rglob(pattern) if recursive else root.glob(pattern))
             if root.is_dir() else [])
    for path in sorted(found, key=lambda p: len(p.parts), reverse=True):
        remove(path)
    return len(found)


def merge_clone(src_dir: Path, dest_dir: Path) -> tuple[int, int]:
    """Clone every file under *src_dir* into *dest_dir*, keeping files that
    already exist there. Returns (cloned, kept). (cp -n can't be used: it
    exits non-zero whenever it skips a file.)"""
    cloned = kept = 0
    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue
        dest = dest_dir / src.relative_to(src_dir)
        if dest.exists():
            kept += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        clone(src, dest)
        cloned += 1
    return cloned, kept


def caelumite_modlist(mo2_text: str) -> tuple[str, int]:
    """MO2's modlist.txt converted to Caelumite's separator layout.

    Both list the highest priority first, but MO2 writes a separator after
    its mods (its view is ascending, so the separator lands above them) and
    Caelumite reads a separator as heading the mods after it. Each separator
    moves to the front of its block; mod order, and so priority, is
    unchanged. MO2's ``*`` entries (DLC and other files it doesn't manage)
    are dropped - they aren't mod folders. Returns (text, n) where n counts
    mods below the last separator: ungrouped in MO2, they end up in the last
    separator's block here, since moving them would change their priority.
    """
    out: list[str] = []
    block: list[str] = []
    eol = "\r\n" if "\r\n" in mo2_text else "\n"
    for line in mo2_text.splitlines(keepends=True):
        name = line.rstrip("\r\n")
        line = name + eol   # a last line without a newline gets one
        if name.startswith("#") or not name.strip():
            out.append(line)
        elif name.startswith("*"):
            continue
        elif name[1:].endswith("_separator"):
            out.append(line)
            out.extend(block)
            block = []
        else:
            block.append(line)
    out.extend(block)
    return "".join(out), len(block)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("instance", type=Path)
    ap.add_argument("game_root", type=Path)
    ap.add_argument("--mo2-profile", default="Default")
    ap.add_argument("--profile", default="default")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    mods_src, overwrite_src, profiles_src = mo2_dirs(a.instance.expanduser())
    profile_src = profiles_src / a.mo2_profile
    root = a.game_root.expanduser()
    mods_dst, overwrite_dst = root / "mods", root / "overwrite"
    profile_dst = root / "profiles" / a.profile
    for path in (mods_src, profile_src, mods_dst, profile_dst):
        if not path.is_dir():
            raise SystemExit(f"error: {path} not found")

    if not a.dry_run:
        # Mod folders are cloned whole (top level); overwrite file by file.
        for root, recursive in ((mods_dst, False), (overwrite_dst, True)):
            if n := remove_partials(root, recursive):
                print(f"  removed {n} unfinished copy(ies) from an earlier run in {root}")
    mods = sorted(p for p in mods_src.iterdir() if p.is_dir())
    clashes = [p.name for p in mods if (mods_dst / p.name).exists()]
    todo = [p for p in mods if p.name not in clashes]
    print(f"MO2 mods: {len(mods)} | to import: {len(todo)} | already in "
          f"Caelumite (skipped): {len(clashes)}")
    if a.dry_run:
        for name in clashes:
            print(f"  skip: {name}")
        return 0

    started = time.monotonic()
    for i, src in enumerate(todo, 1):
        clone(src, mods_dst / src.name)
        if i % 25 == 0 or i == len(todo):
            print(f"  cloned {i}/{len(todo)} mods ({time.monotonic() - started:.0f}s)",
                  flush=True)

    if overwrite_src.is_dir():
        cloned, kept = merge_clone(overwrite_src, overwrite_dst)
        print(f"  overwrite: cloned {cloned} file(s), kept {kept} already in Caelumite")

    # Convert the mod list before touching the profile, so nothing is
    # replaced if it can't be read. MO2 lists can hold non-UTF-8 (cp1252)
    # bytes in mod names; surrogateescape carries them through unchanged.
    converted = ungrouped = None
    if (profile_src / "modlist.txt").is_file():
        converted, ungrouped = caelumite_modlist(
            (profile_src / "modlist.txt").read_bytes().decode(
                "utf-8", "surrogateescape"))
    backup = profile_dst / "backups" / time.strftime("pre-mo2-import-%Y%m%d-%H%M%S")
    backup.mkdir(parents=True)
    for name in PROFILE_FILES:
        if (profile_dst / name).is_file():
            shutil.copy2(profile_dst / name, backup / name)
        if name == "modlist.txt" and converted is not None:
            (profile_dst / name).write_bytes(
                converted.encode("utf-8", "surrogateescape"))
        elif (profile_src / name).is_file():
            shutil.copy2(profile_src / name, profile_dst / name)
    if ungrouped:
        print(f"  note: {ungrouped} mod(s) above MO2's first separator now "
              "sit in the last separator's block (same priority)")
    print(f"  profile '{a.profile}' now uses MO2 '{a.mo2_profile}' load order "
          f"(previous files backed up to {backup})")

    for name in clashes:
        print(f"  skipped (already in Caelumite): {name}")
    print(f"Done in {time.monotonic() - started:.0f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
