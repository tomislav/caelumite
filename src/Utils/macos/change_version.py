"""
Utils.macos.change_version
The Change Version tab (gui_qt/nexus/change_version.py) for Creation mods,
and the window's reference to the open tab.

A Creation has no Nexus files, so instead of asking Nexus for mod 0 the tab
says the mod is a Creation and points at its right-click menu. Ignore Update
and the highlight legend only apply to Nexus files and are turned off
meanwhile.

Opening Change Version for another mod replaces the tab, and Qt deletes the
old one only after the new one is open; upstream's slot then clears the
window's reference to the new tab. Without it a Mod Manager Download for the
new tab isn't recognised: it installs as a new mod and the tab keeps waiting.
keep_replacement puts the reference back.

The tab refreshes its "installed" highlight after installs it started. A
Rollback, Reinstall or Quick Update of the mod it shows refreshes it too,
also when a rollback restores the folder's earlier name (showing_mod), unless
the tab is waiting for its own download.
"""

from __future__ import annotations

from Utils.macos.creations import is_creation


def show_creation_notice(view) -> bool:
    """Set up *view* for the mod it now shows. True when that mod is a
    Creation and the notice replaced the Nexus fetch."""
    from gui_qt.nexus.change_version import _LegendBar
    creation = is_creation(view._meta)
    view._ignore_cb.setEnabled(not creation)
    legend = view.findChild(_LegendBar)
    if legend is not None:
        legend.setVisible(not creation)
    if not creation:
        return False
    view._fetch_gen += 1    # drop the previous mod's fetch
    view._loading_overlay.hide_overlay()
    view._status.setText(view.tr(
        "{0} is a Creation. Right-click it and choose Open on Creations."
    ).format(view._mod_name))
    view._status.setVisible(True)
    return True


def keep_replacement(window, view) -> None:
    """Connected after upstream's slot that clears the window's Change Version
    reference when *view* is deleted: when another tab has replaced *view* by
    then, put that tab back."""
    window._caelumite_change_version = view

    def restore(*_):
        current = getattr(window, "_caelumite_change_version", None)
        if current is view:
            window._caelumite_change_version = None
        elif current is not None:
            window._change_version_view = current
    view.destroyed.connect(restore)


def showing_mod(window, name: str, previous_name: str | None = None) -> bool:
    """The open Change Version tab shows mod *name*, or the *previous_name* it
    had before a rollback restored another, and isn't busy with its own
    download or install, so it can re-read the mod after an install."""
    view = getattr(window, "_change_version_view", None)
    return (view is not None and not view.busy()
            and view.current_mod_name() in {name, previous_name} - {None})
