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
such as an optional patch, still installs beside it. For a mod installed
without a file ID or category, a Main file replaces it when its archive was
that file (the name before the mod ID in the archive's name, versions aside)
and no other mod in the profile comes from the same Nexus page. Hooked in gui_qt/app.py
(_install_paths and _on_nxm_download_done).

For a mod without a Nexus file ID, upstream's update check trusts Nexus's
per-account "update available" flag first. That flag only says the mod page
changed since the account last downloaded from it, so an optional file at
2.0.3 showed "update" to the page's 1.3. When the page's version is behind
the installed one, the version comparison decides instead
(without_stale_flag, hooked in Nexus/nexus_update_checker.py).

After Check Updates, upstream offers Quick Update for the Nexus updates it
found, which downloads directly and so needs Nexus Premium. offer_updates
(hooked in gui_qt/app.py _on_updates_ready) adds Show updates, which filters
the mod list to !update, and without Premium offers only that. The mod list's
right-click menu leaves out Quick Update then too (quick_update_available,
hooked in gui_qt/modlist/menu.py). An unchanged page version still
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
    """*preferred_names* plus the mod's own name for each archive that replaces
    the mod its Nexus version change updates: the update the check found, a
    file in the installed file's place on the page (_same_place), or the
    Main file of a mod installed without a file ID (_main_for_unknown).
    Returns *preferred_names* unchanged when no archive qualifies."""
    names = dict(preferred_names or {})
    for path in paths:
        change = (version_changes or {}).get(path)
        meta = (metas or {}).get(path)
        if (change is None or meta is None or path in names
                or change.operation != "update" or change.source != "nexus"):
            continue
        if (_is_update(change.previous_meta, getattr(meta, "file_id", 0))
                or _same_place(change.previous_meta, meta)
                or _main_for_unknown(change, meta)):
            names[path] = change.mod_name
    return names or preferred_names


def _category(meta) -> str:
    return (getattr(meta, "file_category", "") or "").strip().upper()


def _main_for_unknown(change, picked) -> bool:
    """The installed file of *change*'s mod is unknown (no file ID or
    category), *picked* is a Main file of its Nexus page whose name matches
    the archive the mod was installed from, and no other mod in the profile
    comes from that page, so the Main file can only replace it."""
    installed = change.previous_meta
    mod_id = getattr(installed, "mod_id", 0)
    profile_dir = getattr(change, "profile_dir", None)
    previous_path = getattr(change, "previous_path", None)
    if (getattr(installed, "file_id", 0) or _category(installed)
            or _category(picked) != "MAIN" or not getattr(picked, "file_id", 0)
            or not mod_id or getattr(picked, "mod_id", 0) != mod_id
            or profile_dir is None or previous_path is None):
        return False
    archive_name = _archive_file_name(getattr(installed, "installation_file", ""), mod_id)
    picked_name = _without_versions(getattr(picked, "nexus_file_name", ""))
    if not archive_name or archive_name != picked_name:
        return False
    names = [name for name, _meta in _mods_with_id(profile_dir, Path(previous_path).parent, mod_id)]
    return names == [change.mod_name]


def _archive_file_name(archive: str, mod_id: int) -> str:
    """The Nexus file name a downloaded archive was named after: what comes
    before its mod ID ("NativeLight FOMOD 17733 1 2026-07-26T21-27Z ….zip",
    "Akila Outskirts Expanded-16238-1-0-1774513871.7z"), versions aside."""
    match = re.match(rf"(.+?)[ -]{mod_id}[ -]", archive or "")
    return _without_versions(match.group(1)) if match else ""


def _without_versions(name: str) -> str:
    """*name* compared loosely and without version numbers ("V2.0.1", "1.3")."""
    from Utils.mods.versions import _normalize_match
    return " ".join(token for token in _normalize_match(name or "").split()
                    if not re.fullmatch(r"v?\d+", token))


def _same_place(installed, picked) -> bool:
    """*picked* is another file of the installed mod's Nexus page in the
    installed file's place: the same category, or either an old version."""
    old, new = _category(installed), _category(picked)
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
    from Nexus.nexus_meta import normalise_game_domain
    from Utils.profiles.groups import is_group
    domain = normalise_game_domain(game_domain)
    if not (profile_dir and staging and mod_id and file_id) or is_group(profile_dir):
        return None
    found = [name for name, meta in _mods_with_id(profile_dir, staging, mod_id)
             if _is_update(meta, file_id)
             and (normalise_game_domain(meta.game_domain) or domain) == domain]
    return found[0] if len(found) == 1 else None


def _mods_with_id(profile_dir, staging, mod_id: int):
    """(name, meta) of each mod in the profile's mod list from Nexus mod
    *mod_id*. Each meta.ini is checked for the ID before it's parsed."""
    from Nexus.nexus_meta import read_meta
    from Utils.mods.modlist import read_modlist
    found = []
    for entry in read_modlist(Path(profile_dir) / "modlist.txt"):
        if entry.is_separator:
            continue
        meta_path = Path(staging) / entry.name / "meta.ini"
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
        if meta.mod_id == mod_id:
            found.append((entry.name, meta))
    return found


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


def quick_update_available() -> bool:
    """Quick Update downloads directly, which needs Nexus Premium: False only
    when the account's last validation said it has none."""
    from Utils.ui.config import load_nexus_last_premium
    return load_nexus_last_premium() is not False


def show_updates(window) -> None:
    """Filter the mod list to mods with updates: add !update to its search,
    keeping what's already typed there."""
    text = window._modlist_search.text().strip()
    if any(term.lower() in ("!update", "!updates") for term in text.split()):
        return
    window._modlist_search.setText(f"{text} !update".strip())


def offer_updates(window, names: list[str]) -> None:
    """After Check Updates, offer the Nexus updates in *names*: Show updates
    (the mod list filtered to !update), plus upstream's Quick Update unless
    the account is known not to have Premium."""
    if not names:
        return
    from gui_qt.dialogs.confirm import ConfirmOverlay

    if not quick_update_available():
        ConfirmOverlay.show_over(
            window, window.tr("Updates available"),
            window.tr("{0} mod(s) have an update.").format(len(names)),
            lambda ok: ok and show_updates(window),
            confirm_label=window.tr("Show updates"), danger=False)
        return
    ConfirmOverlay.show_over(
        window, window.tr("Updates available"),
        window.tr("{0} mod(s) have an update available.\n\n"
                  "Run Quick Update on all of them now?").format(len(names)),
        lambda ok: ok and window._quick_update_mods(names),
        confirm_label=window.tr("Quick Update"),
        secondary_action=(window.tr("Show updates"), lambda: show_updates(window)))
