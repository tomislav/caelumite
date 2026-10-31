"""
Utils.macos.mod_updates
Installs a Nexus update in place of the mod it updates.

Upstream names a new install after the Nexus file ("FTL - Grav Jump Overhaul
2.0.6 (Beta)"). When that differs from the installed mod's folder, Change
Version installs the update beside it and asks to remove the previous
version, and a Mod Manager Download from the website adds a second mod.

The update check records which file updates each mod (latestfileid in
meta.ini; for an up-to-date mod that's its own file). Installing exactly that
file, when it isn't the installed one, replaces the mod under its own name,
the way Quick Update does, so it keeps its place and can be rolled back.
Change Version also replaces in place without that record (no check yet, or
after a rollback cleared it) when the picked file fills the installed file's
place on the mod's page: the same Nexus category, or either one an old
version - the rule the update check uses. A file in another current category,
such as an optional patch, still installs beside it. Hooked in gui_qt/app.py
(_install_paths and _on_nxm_download_done).

For a mod without a Nexus file ID, upstream's update check trusts Nexus's
per-account "update available" flag first. That flag only says the mod page
changed since the account last downloaded from it, so an optional file at
2.0.3 showed "update" to the page's 1.3. When the page's version is behind
the installed one, the version comparison decides instead
(without_stale_flag, hooked in Nexus/nexus_update_checker.py). An unchanged page version still
trusts the flag: authors often upload a file without bumping it.
"""

from __future__ import annotations

import re
from pathlib import Path

# Nexus file categories of files their author has replaced (as in the update
# check, Nexus/nexus_update_checker.py).
_SUPERSEDED = {"OLD_VERSION", "ARCHIVED", "REMOVED"}

# meta.ini's [General] mod ID, matched before parsing the whole file.
_MOD_ID = re.compile(r"^[ \t]*modid[ \t]*=[ \t]*(\d+)[ \t]*$", re.IGNORECASE | re.MULTILINE)


def in_place_names(paths, metas, version_changes, preferred_names):
    """*preferred_names* plus the mod's own name for each archive that is the
    update the check found for the mod its Nexus version change updates.
    Returns *preferred_names* unchanged when no archive qualifies."""
    names = dict(preferred_names or {})
    for path in paths:
        change = (version_changes or {}).get(path)
        meta = (metas or {}).get(path)
        if (change is None or meta is None or path in names
                or change.operation != "update" or change.source != "nexus"):
            continue
        if (_is_update(change.previous_meta, getattr(meta, "file_id", 0))
                or _same_place(change.previous_meta, meta)):
            names[path] = change.mod_name
    return names or preferred_names


def _same_place(installed, picked) -> bool:
    """*picked* is another file of the installed mod's Nexus page in the
    installed file's place: the same category, or either an old version."""
    def category(meta):
        return (getattr(meta, "file_category", "") or "").strip().upper()
    old, new = category(installed), category(picked)
    file_id = getattr(picked, "file_id", 0)
    return (bool(old and new and file_id)
            and file_id != getattr(installed, "file_id", 0)
            and getattr(picked, "mod_id", 0) == getattr(installed, "mod_id", 0)
            and (old == new or old in _SUPERSEDED or new in _SUPERSEDED))


def _is_update(meta, file_id: int) -> bool:
    """*file_id* is the update the check found for the mod *meta* describes,
    not the file already installed."""
    latest = getattr(meta, "latest_file_id", 0)
    return bool(latest) and file_id == latest and file_id != getattr(meta, "file_id", 0)


def update_target(profile_dir, staging, game_domain: str, mod_id: int,
                  file_id: int) -> str | None:
    """The profile's one mod whose update the check found is *file_id* of Nexus
    mod *mod_id* on *game_domain*, or None (none, several, or a Profile Group).
    A meta.ini without a domain belongs to the profile's game, as in the
    update check."""
    from Nexus.nexus_meta import normalise_game_domain, read_meta
    from Utils.mods.modlist import read_modlist
    from Utils.profiles.groups import is_group
    domain = normalise_game_domain(game_domain)
    if not (profile_dir and staging and mod_id and file_id) or is_group(profile_dir):
        return None
    found = []
    for entry in read_modlist(Path(profile_dir) / "modlist.txt"):
        meta_path = Path(staging) / entry.name / "meta.ini"
        if entry.is_separator:
            continue
        try:
            text = meta_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(int(found_id) == mod_id for found_id in _MOD_ID.findall(text)):
            continue
        try:
            meta = read_meta(meta_path)
        except Exception:
            continue
        if (meta.mod_id == mod_id and _is_update(meta, file_id)
                and (normalise_game_domain(meta.game_domain) or domain) == domain):
            found.append(entry.name)
    return found[0] if len(found) == 1 else None


def nxm_update(game, profile_dir, staging, game_domain: str, mod_id: int,
               file_id: int, log_fn=None):
    """The version change for a Mod Manager Download of the update the check
    found for an installed mod, or None to install it as a new mod."""
    name = update_target(profile_dir, staging, game_domain, mod_id, file_id)
    if name is None:
        return None
    from Utils.mods.version_history import VersionChangeContext
    try:
        change = VersionChangeContext.capture(game, profile_dir, name, "nexus")
    except Exception as exc:
        if log_fn is not None:
            log_fn(f"[nexus] couldn't update '{name}' in place ({exc}) - installing as a new mod.")
        return None
    if log_fn is not None:
        log_fn(f"[nexus] file {file_id} is the update for '{name}' - updating it in place.")
    return change


def page_is_behind(page_version: str, installed_version: str) -> bool:
    """The mod page's version is readable and older than the installed one, so
    Nexus's "update available" flag is about another file."""
    from Nexus.nexus_update_checker import _parse_version
    page, installed = _parse_version(page_version), _parse_version(installed_version)
    return page is not None and installed is not None and page < installed


def without_stale_flag(info, installed_version: str):
    """Nexus's update info for one local copy of a mod: *info* itself, or a
    copy without the "update available" flag when the page's version is
    behind *installed_version*. Never changes *info*, which the mod's other
    local copies still read."""
    if (info is None or info.viewer_update_available is not True
            or not page_is_behind(info.version, installed_version)):
        return info
    import copy
    stale = copy.copy(info)
    stale.viewer_update_available = None
    return stale
