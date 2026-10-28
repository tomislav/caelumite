"""
Utils.macos.loot
A check before LOOT loads the plugins: Sort, Refresh and the record-overlap
check (gui_qt/app.py _on_sort_plugins, _on_show_overlapping_plugins).

For these games LOOT loads each plugin's masters before the plugin
(LOOT.loot_sorter._load_plugins), so one plugin whose master isn't in the
load order stops it with "the plugin X has not been loaded", which doesn't
say who needs X. The plugin rows already list their missing masters (the
red Missing masters flag), so LOOT isn't started and the notice says which
plugin needs which master.
"""

from __future__ import annotations

from Utils.app_log import app_log

# The game types LOOT.loot_sorter._load_plugins loads masters-first.
_MASTERS_FIRST = ("Morrowind", "OpenMW", "Starfield")


def missing_master_notice(window, rows, game) -> str:
    """The notice to show instead of running LOOT, or "" when it can run.
    Disabled plugins count too: LOOT loads every plugin in the list."""
    if getattr(game, "loot_game_type", "") not in _MASTERS_FIRST:
        return ""
    broken = [(r.name, r.missing_masters) for r in rows if r.missing_masters]
    if not broken:
        return ""
    for name, masters in broken:
        app_log(f"[loot] {name} needs {', '.join(masters)}, which isn't in the load order.")
    name, masters = broken[0]
    notice = window.tr(
        "LOOT can't run: {0} needs {1}, which isn't in the load order. "
        "Enable the mod that has it, or disable the mod with {0}."
    ).format(name, ", ".join(masters))
    if len(broken) > 1:
        notice += " " + window.tr(
            "{0} more plugin(s) have missing masters: filter the Plugins list "
            "by Missing masters to see them."
        ).format(len(broken) - 1)
    return notice
