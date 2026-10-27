"""
Utils.macos.creations
Bethesda Creations downloaded through the game's in-game Creations menu.

The game writes them straight into ``Data`` and lists them in
``ContentCatalog.txt``, next to ``Plugins.txt``. Upstream treats such files
as runtime output (Overwrite) or, when they appear while the game is
restored, as vanilla files. This module reads the catalog and turns each
Creation into a mod of its own.
"""

from __future__ import annotations

import configparser
import filecmp
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CATEGORY = "Creations"
_NAME_PREFIX = "[Creations]"
_STAMP = "%Y-%m-%dT%H:%M:%S"
_FINGERPRINT_FILE = "creations_catalog.txt"
_STAGED_SUFFIX = ".caelumite-new"
# Nexus game domain → the game's path on creations.bethesda.net.
_SITE_GAMES = {"starfield": "starfield",
               "skyrimspecialedition": "skyrim",
               "fallout4": "fallout4"}


@dataclass(frozen=True)
class Creation:
    id: str
    title: str
    version: str
    files: tuple[str, ...]
    achievement_safe: bool


def catalog_path(game) -> Path | None:
    """The game's ContentCatalog.txt, next to its Plugins.txt."""
    target_fn = getattr(game, "_plugins_txt_target", None)
    if target_fn is None:
        return None
    try:
        target = target_fn()
    except Exception:
        return None
    return target.parent / "ContentCatalog.txt" if target is not None else None


def read_catalog(path: Path | None, log_fn=None) -> dict[str, Creation]:
    """The catalog's Creations by id; ``{}`` when it is missing or unreadable."""
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        if log_fn is not None:
            log_fn(f"Creations: WARN: could not read {path.name}: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    catalog: dict[str, Creation] = {}
    for cid, entry in data.items():
        if cid == "ContentCatalog" or not isinstance(entry, dict):
            continue
        files = entry.get("Files")
        if not files or not isinstance(files, list):
            continue
        catalog[cid] = Creation(
            id=cid,
            title=str(entry.get("Title") or cid),
            version=str(entry.get("Version") or ""),
            files=tuple(str(f) for f in files if f),
            achievement_safe=bool(entry.get("AchievementSafe", False)),
        )
    return catalog


def files_index(catalog: dict[str, Creation]) -> dict[str, Creation]:
    """The catalog's Creations by lowercased file name."""
    return {name.lower(): creation
            for creation in catalog.values() for name in creation.files}


def creation_mod_name(title: str) -> str:
    """A mod folder name for *title*, the way the user names them by hand."""
    from Utils.mods.names import sanitize_mod_folder_name
    name = re.sub(r" {2,}", " ", title.replace(":", "-").replace("|", "-"))
    return sanitize_mod_folder_name(name)


def display_version(version: str) -> str:
    """The version without the catalog's leading timestamp part."""
    head, sep, rest = version.partition(".")
    if sep and rest and head.isdigit() and len(head) >= 9:
        return rest
    return version


_plugin_cache: dict = {}


def plugin_creations(game) -> dict[str, Creation]:
    """The Creations of plugins that a Creation mod holds, by lowercased
    plugin name; ``{}`` on any error.

    Nexus mods may ship plugins with a Creation's name, so a catalog entry
    alone isn't enough. Reading every meta.ini takes tens of milliseconds, so
    the result is kept until the catalog or a mod folder changes (a new
    file, or a meta.ini rewritten in place by an atomic rename).
    """
    try:
        path = catalog_path(game)
        if path is None or not path.is_file():
            return {}
        catalog_mtime = path.stat().st_mtime_ns
        staging = Path(game.get_effective_mod_staging_path())
        # Follow links like _scan_mods: mod folders may be symlinks.
        with os.scandir(staging) as entries:
            folders = tuple(sorted(
                (e.name, e.stat().st_mtime_ns)
                for e in entries if e.is_dir()))
        key = (str(path), catalog_mtime, str(staging), folders)
        if _plugin_cache.get("key") == key:
            return _plugin_cache["value"]
        exts = tuple(ext.lower() for ext in game.plugin_extensions)
        index = files_index(read_catalog(path))
        held = {name for mod in _scan_mods(staging) if mod.is_creation_mod
                for name in mod.files}
        value = {name: creation for name, creation in index.items()
                 if name.endswith(exts) and name in held}
        _plugin_cache.update(key=key, value=value)
        return value
    except Exception:
        return {}


def _archive_exts(game) -> set[str]:
    try:
        return {ext.lower() for ext in game.archive_extensions} or {".ba2"}
    except Exception:
        return {".ba2", ".bsa"}


def creation_tooltip(creation: Creation) -> str:
    """The plugin-list tooltip for a Creation's plugin."""
    text = f"Creation: {creation.title} {display_version(creation.version)}"
    return text + "\nAchievement-friendly" if creation.achievement_safe else text


_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_CREATION_ID_LINE = re.compile(rb"creationid[ \t]*[=:][ \t]*(\S+)",
                               re.IGNORECASE)


def _creation_id(mod_dir: Path) -> str:
    """The mod's ``creationId``, found without parsing the whole meta.ini.

    The right-click menu asks for every selected mod; a full ConfigParser
    read of ~300 files takes ~70 ms on the GUI thread, a line scan ~8 ms.
    Like ConfigParser, it reads only [General] and the last entry wins.
    """
    try:
        data = (Path(mod_dir) / "meta.ini").read_bytes()
    except OSError:
        return ""
    found = b""
    in_general = False
    for line in data.splitlines():
        line = line.strip()
        if line.startswith(b"[") and line.endswith(b"]"):
            in_general = line[1:-1].strip() == b"General"
        elif in_general:
            match = _CREATION_ID_LINE.match(line)
            if match:
                found = match.group(1)
    return found.decode("ascii", "replace")


def creation_url(game, mod_dir: Path) -> str:
    """The mod's page on creations.bethesda.net; "" when it isn't a Creation
    mod or the game has no Creations site."""
    site_game = _SITE_GAMES.get(getattr(game, "nexus_game_domain", "") or "")
    if site_game is None:
        return ""
    uuid = _creation_id(mod_dir).removeprefix("TM_")
    if not _UUID.fullmatch(uuid):
        return ""
    return f"https://creations.bethesda.net/en/{site_game}/details/{uuid}"


def same_content(path: str, other: str) -> bool:
    """Whether two files hold the same bytes; False when either is unreadable.

    Restore uses it for a deployed file the game replaced: an in-game
    re-download of a Creation writes identical bytes, which isn't an edit.
    """
    try:
        return (os.path.getsize(path) == os.path.getsize(other)
                and filecmp.cmp(path, other, shallow=False))
    except OSError:
        return False


def catalog_fingerprint(catalog: dict[str, Creation]) -> str:
    """A hash of the catalog's Creations, versions and files.

    Titles and timestamps are left out: the game rewrites the catalog at the
    end of every session, so only a real install, update or removal counts.
    """
    rows = sorted((c.id, c.version, sorted(name.lower() for name in c.files))
                  for c in catalog.values())
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


def _fingerprint_path(game) -> Path:
    return Path(game.get_profile_root()) / _FINGERPRINT_FILE


def creations_changed(game) -> bool:
    """Whether the game's Creations changed since the last import."""
    try:
        catalog = read_catalog(catalog_path(game))
        if not catalog:
            return False
        stored = _fingerprint_path(game)
        if not stored.is_file():
            return True
        return (stored.read_text(encoding="utf-8").strip()
                != catalog_fingerprint(catalog))
    except Exception:
        return False


@dataclass
class _Mod:
    name: str
    path: Path
    meta: dict[str, str]        # meta.ini [General], lowercased keys
    files: dict[str, Path] = field(default_factory=dict)   # top level, by lowercased name

    @property
    def is_creation_mod(self) -> bool:
        return (self.meta.get("categoryname", "").strip().lower()
                == CATEGORY.lower()
                or self.name.startswith(_NAME_PREFIX)
                or bool(self.meta.get("creationid")))


def _top_files(folder: Path) -> dict[str, Path]:
    try:
        with os.scandir(folder) as entries:
            return {e.name.lower(): Path(e.path) for e in entries
                    if e.is_file(follow_symlinks=False)}
    except OSError:
        return {}


def _read_general(mod_dir: Path) -> dict[str, str]:
    """meta.ini [General] as upstream reads it (``%%`` is ``%``)."""
    from Utils.mods.metadata import read_meta_ini
    meta = mod_dir / "meta.ini"
    if not meta.is_file():
        return {}
    try:
        _, cp, _ = read_meta_ini(str(meta))
    except (OSError, UnicodeDecodeError):
        return {}
    if not cp.has_section("General"):
        return {}
    try:
        items = cp.items("General")
    except configparser.Error:   # a raw % another tool wrote
        items = cp.items("General", raw=True)
    return {key: value or "" for key, value in items}


def _set_meta(mod: _Mod, values: dict) -> None:
    from Nexus.nexus_meta import set_meta_keys
    meta = mod.path / "meta.ini"
    if not meta.is_file():
        meta.write_text("[General]\n", encoding="utf-8")
    set_meta_keys(meta, values)
    for key, value in values.items():
        if value is None:
            mod.meta.pop(key.lower(), None)
        else:
            mod.meta[key.lower()] = str(value)


def _scan_mods(staging: Path, *, clean: bool = False) -> list[_Mod]:
    """Every mod folder, with the top-level files of Creation mods.

    *clean* (the import only) deletes staged files a crash in _replace_file
    left behind. Never from the plugin list's tooltip lookup: that runs on
    the GUI thread while an import may be mid-swap.
    """
    mods = []
    try:
        with os.scandir(staging) as entries:
            folders = sorted((e for e in entries if e.is_dir()),
                             key=lambda e: e.name.lower())
    except OSError:
        return []
    for entry in folders:
        mod = _Mod(entry.name, Path(entry.path), _read_general(Path(entry.path)))
        if mod.is_creation_mod:
            mod.files = _top_files(mod.path)
            for name, path in list(mod.files.items()) if clean else ():
                if name.startswith(".") and name.endswith(_STAGED_SUFFIX):
                    # Left by a crash in _replace_file; it would be deployed.
                    try:
                        path.unlink()
                    except OSError:
                        continue
                    del mod.files[name]
        mods.append(mod)
    return mods


def _find_mod(creation: Creation, mods: list[_Mod]) -> _Mod | None:
    for mod in mods:
        if mod.meta.get("creationid") == creation.id:
            return mod
    wanted = {name.lower() for name in creation.files}
    hits = [(len(wanted & mod.files.keys()), mod) for mod in mods
            if mod.is_creation_mod and wanted & mod.files.keys()]
    if not hits:
        return None
    return min(hits, key=lambda hit: (-hit[0], hit[1].name.lower()))[1]


def _unique_name(base: str, taken: set[str]) -> str:
    name, n = base, 2
    while name.lower() in taken:
        name = f"{base} ({n})"
        n += 1
    return name


def _candidates(game, index: dict[str, Creation]) -> dict[str, list[tuple[Path, bool]]]:
    """Catalog-listed files the game wrote, by Creation id: (path, from Data)."""
    found: dict[str, list[tuple[Path, bool]]] = {}
    for name, path in _top_files(Path(game.get_effective_overwrite_path())).items():
        if name in index:
            found.setdefault(index[name].id, []).append((path, False))
    game_path = game.get_game_path()
    if not game_path:
        return found
    from Utils.games.registry import _vanilla_plugins_for_game
    vanilla = set(_vanilla_plugins_for_game(game))
    # Starfield and Fallout 4 archives are "<plugin> - <name>.ba2", Skyrim's
    # "<plugin>.bsa".
    prefixes = tuple(Path(name).stem + sep for name in vanilla
                     for sep in (" - ", "."))
    archive_exts = _archive_exts(game)
    for name, path in _top_files(Path(game_path) / "Data").items():
        if name not in index or name in vanilla:
            continue
        if Path(name).suffix in archive_exts and name.startswith(prefixes):
            continue
        try:
            if path.lstat().st_nlink > 1:
                continue
        except OSError:
            continue
        found.setdefault(index[name].id, []).append((path, True))
    return found


def _sync_plugins(game, profile_dir: Path, run: "_Run",
                  enabled_states: dict[str, bool]) -> None:
    """Bring plugins.txt in line with the plugins the import moved.

    Plugins moved out of Data into an enabled mod are added, at the slot
    loadorder.txt remembers and enabled unless the game's own list had them
    off. Plugins moved out of Overwrite (sync_overwrite_plugins registered
    them) into a mod that isn't enabled are taken off plugins.txt, unless an
    enabled mod ships the same name; loadorder.txt keeps them as position
    memory, as when a mod is disabled.
    """
    if not (run.data_plugins or run.unlisted_plugins) or not getattr(
            game, "uses_plugins_txt", False):
        return
    from Utils.plugins import (
        PluginEntry, insert_by_loadorder, read_loadorder, read_plugins,
        write_loadorder, write_plugins,
    )
    star = bool(getattr(game, "plugins_use_star_prefix", True))
    plugins_path = profile_dir / "plugins.txt"
    loadorder_path = profile_dir / "loadorder.txt"
    entries = read_plugins(plugins_path, star_prefix=star)
    loadorder = read_loadorder(loadorder_path)
    listed = {entry.name.lower() for entry in entries}
    lo_pos = {name.lower(): i for i, name in enumerate(loadorder)}
    added = [name for name in dict.fromkeys(run.data_plugins)
             if name.lower() not in listed]
    for name in added:
        insert_by_loadorder(
            entries, PluginEntry(name, enabled_states.get(name.lower(), True)),
            lo_pos)
        if name.lower() not in lo_pos:
            loadorder.append(name)
            lo_pos[name.lower()] = len(loadorder) - 1
    enabled_mods = [name for name, on in run.enabled.items() if on]
    removed = {name.lower() for name in run.unlisted_plugins
               if name.lower() in listed
               and not any((run.staging / mod / name).is_file()
                           for mod in enabled_mods)}
    if not added and not removed:
        return
    entries = [entry for entry in entries if entry.name.lower() not in removed]
    write_plugins(plugins_path, entries, star_prefix=star)
    if added:
        write_loadorder(loadorder_path,
                        [PluginEntry(name, True) for name in loadorder])
        run.log_fn("Creations: registered plugins: " + ", ".join(added))
    if removed:
        run.log_fn("Creations: took plugins of mods that aren't enabled off "
                   "the plugin list: " + ", ".join(sorted(removed)))


def adopt_creations(game, profile_dir: Path, *, log_fn,
                    enabled_states: dict[str, bool] | None = None) -> list[str]:
    """Move the files of in-game Creations into one mod per Creation.

    Called right after a full restore, so ``Data`` holds the vanilla files
    plus whatever the game added. *enabled_states* is the game's own plugin
    list (lowercased name → enabled), for plugins moved out of Data. Returns
    the mods whose files changed (including ones whose identical Overwrite
    copy was dropped, since Overwrite changed too); empty when nothing moved.
    """
    catalog = read_catalog(catalog_path(game), log_fn)
    if not catalog:
        return []
    changed: dict[str, None] = {}
    try:
        complete = _adopt(game, Path(profile_dir), catalog, changed,
                          enabled_states or {}, log_fn)
    except Exception as exc:
        log_fn(f"Creations: WARN: import stopped: {exc}")
        complete = False
    # Without the fingerprint, the next deploy takes the full path and tries
    # the failed Creations again.
    if complete:
        try:
            _fingerprint_path(game).write_text(
                catalog_fingerprint(catalog) + "\n", encoding="utf-8")
        except OSError as exc:
            log_fn(f"Creations: WARN: could not save {_FINGERPRINT_FILE}: {exc}")
    return list(changed)


def _adopt(game, profile_dir: Path, catalog: dict[str, Creation],
           changed: dict[str, None], enabled_states: dict[str, bool],
           log_fn) -> bool:
    """Import every Creation; False when any of them failed."""
    from Utils.mods.modlist import read_modlist

    index = files_index(catalog)
    owners: dict[str, set[str]] = {}
    for creation in catalog.values():
        for name in creation.files:
            owners.setdefault(name.lower(), set()).add(creation.id)
    staging = Path(game.get_effective_mod_staging_path())
    modlist_path = profile_dir / "modlist.txt"
    run = _Run(
        catalog=catalog,
        owners=owners,
        plugin_exts={ext.lower() for ext in game.plugin_extensions},
        archive_exts=_archive_exts(game),
        staging=staging,
        modlist_path=modlist_path,
        enabled={e.name: e.enabled for e in read_modlist(modlist_path)},
        mods=_scan_mods(staging, clean=True),
        now=datetime.now(),
        changed=changed,
        log_fn=log_fn,
    )
    run.taken = {name.lower() for name in run.enabled}
    try:
        run.taken.update(name.lower() for name in os.listdir(staging))
    except OSError:
        pass
    run.backup_root = (Path(game.get_profile_root()) / "creations_backup"
                       / run.now.strftime("%Y-%m-%dT%H-%M-%S"))
    candidates = _candidates(game, index)
    complete = True
    try:
        for creation in sorted(catalog.values(), key=lambda c: c.id):
            try:
                _adopt_one(run, creation, candidates.get(creation.id, []))
            except Exception as exc:
                complete = False
                log_fn(f"Creations: WARN: '{creation.title}' was not "
                       f"imported: {exc}")
    finally:
        _sync_plugins(game, profile_dir, run, enabled_states)
    return complete


@dataclass
class _Run:
    """The state one adopt_creations call shares between Creations."""
    catalog: dict[str, Creation]
    owners: dict[str, set[str]]
    plugin_exts: set[str]
    archive_exts: set[str]
    staging: Path
    modlist_path: Path
    enabled: dict[str, bool]
    mods: list[_Mod]
    now: datetime
    changed: dict[str, None]
    log_fn: object
    taken: set[str] = field(default_factory=set)
    backup_root: Path = Path()
    data_plugins: list[str] = field(default_factory=list)
    unlisted_plugins: list[str] = field(default_factory=list)


def _adopt_one(run: _Run, creation: Creation,
               files: list[tuple[Path, bool]]) -> None:
    mod = _find_mod(creation, run.mods)
    if mod is None and not files:
        return
    is_new = mod is None
    if is_new:
        mod = _new_mod(run, creation)
    _move_in(run, creation, mod, files)
    if not is_new:
        _refresh_version(run, creation, mod)


def _new_mod(run: _Run, creation: Creation) -> _Mod:
    from Utils.mods.modlist import prepend_mod
    name = _unique_name(creation_mod_name(creation.title), run.taken)
    mod = _Mod(name, run.staging / name, {})
    mod.path.mkdir(parents=True)
    run.taken.add(name.lower())
    _set_meta(mod, {
        "installed": run.now.strftime(_STAMP),
        "version": display_version(creation.version),
        "creationId": creation.id,
        "creationTitle": creation.title,
        "creationVersion": creation.version,
        "categoryName": CATEGORY,
    })
    prepend_mod(run.modlist_path, name, enabled=True)
    run.enabled[name] = True
    run.mods.append(mod)
    return mod


def _move_in(run: _Run, creation: Creation, mod: _Mod,
             files: list[tuple[Path, bool]]) -> None:
    if not files:
        return
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    for source, from_data in files:
        target = mod.files.get(source.name.lower())
        if target is not None and target.is_file():
            if filecmp.cmp(source, target, shallow=False):
                source.unlink()
                counts["unchanged"] += 1
                if not from_data:
                    run.changed[mod.name] = None
                _track_plugin(run, mod, target, from_data)
                continue
            # Recorded first: once swapped in, the file has changed even if
            # renaming it to the game's spelling fails.
            run.changed[mod.name] = None
            dest = _replace_file(source, target, mod.path / source.name)
            if dest.name != source.name:
                run.log_fn(f"Creations: kept the name {dest.name} in "
                           f"{mod.name}; the game calls it {source.name}.")
            counts["updated"] += 1
        else:
            dest = mod.path / source.name
            shutil.move(str(source), str(dest))
            counts["new"] += 1
        mod.files[source.name.lower()] = dest
        run.changed[mod.name] = None
        _track_plugin(run, mod, dest, from_data)
    run.log_fn(f"Creations: '{creation.title}' → {mod.name} "
               f"({counts['new']} new, {counts['updated']} updated, "
               f"{counts['unchanged']} unchanged)")
    state = run.enabled.get(mod.name)
    if state is False:
        run.log_fn(f"Creations: '{creation.title}' is in the disabled mod "
                   f"'{mod.name}'; enable it to keep using it.")
    elif state is None:
        run.log_fn(f"Creations: '{creation.title}' is in the mod '{mod.name}', "
                   "which isn't in this profile's mod list; add it to keep "
                   "using it.")


def _track_plugin(run: _Run, mod: _Mod, path: Path, from_data: bool) -> None:
    """Note a plugin the import placed in *mod* for _sync_plugins."""
    if path.suffix.lower() not in run.plugin_exts:
        return
    if from_data and run.enabled.get(mod.name):
        run.data_plugins.append(path.name)
    elif not from_data and not run.enabled.get(mod.name):
        run.unlisted_plugins.append(path.name)


def _replace_file(source: Path, target: Path, dest: Path) -> Path:
    """Replace the mod's *target* with *source*, renamed to *dest*.

    The new file is moved next to the target first and swapped in with one
    rename, so a failed move leaves the mod's own copy in place. If only the
    rename to the game's spelling fails, the target keeps its old spelling.
    """
    staged = target.with_name(f".{source.name}{_STAGED_SUFFIX}")
    shutil.move(str(source), str(staged))
    try:
        os.replace(staged, target)
    except OSError:
        shutil.move(str(staged), str(source))
        raise
    if target.name != dest.name:   # the game's spelling of the name
        try:
            os.rename(target, dest)
        except OSError:
            return target
    return dest


def _refresh_version(run: _Run, creation: Creation, mod: _Mod) -> None:
    # The mod's creation keys belong to the Creation it records, or to the
    # first one that claims it.
    if mod.meta.get("creationid", creation.id) != creation.id:
        return
    recorded = mod.meta.get("creationversion")
    # The Version column shows `version`; fill it when empty, never replace
    # one the user set.
    missing_version = not mod.meta.get("version", "").strip()
    if not recorded:
        values = {"creationId": creation.id,
                  "creationTitle": creation.title,
                  "creationVersion": creation.version}
        if not mod.meta.get("categoryname"):
            values["categoryName"] = CATEGORY
        if missing_version:
            values["version"] = display_version(creation.version)
        _set_meta(mod, values)
        return
    if recorded == creation.version:
        if missing_version:
            _set_meta(mod, {"version": display_version(recorded)})
        return
    version = display_version(creation.version)
    values = {"creationVersion": creation.version, "version": version,
              "updated": run.now.strftime(_STAMP)}
    flagged = mod.meta.get("xeditmodifiedplugins")
    if flagged:
        plugins = {name.lower() for name in creation.files
                   if Path(name).suffix.lower() in run.plugin_exts}
        kept = [n.strip() for n in flagged.split(";")
                if n.strip() and n.strip().lower() not in plugins]
        values["xeditModifiedPlugins"] = ";".join(kept) or None
    _set_meta(mod, values)
    run.log_fn(f"Creations: '{creation.title}' updated to {version} "
               f"in {mod.name}")
    _move_dropped_files(run, creation, mod)


def _move_dropped_files(run: _Run, creation: Creation, mod: _Mod) -> None:
    """Back up the plugins and archives an update no longer lists."""
    listed = {name.lower() for name in creation.files}
    top = _top_files(mod.path)
    if not listed & top.keys():
        return
    if any(run.owners.get(name, set()) - {creation.id} for name in top):
        return
    backup = run.backup_root / mod.name
    for name, path in sorted(top.items()):
        suffix = path.suffix.lower()
        if name in listed or (suffix not in run.plugin_exts
                              and suffix not in run.archive_exts):
            continue
        backup.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(backup / path.name))
        mod.files.pop(name, None)
        run.changed[mod.name] = None
        run.log_fn(f"Creations: '{creation.title}' no longer uses {path.name}; "
                   f"moved it to {backup}")
