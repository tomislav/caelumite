"""
Utils.macos.change_version
The Change Version tab (gui_qt/nexus/change_version.py) for Creation mods.

A Creation has no Nexus files, so instead of asking Nexus for mod 0 the tab
says the mod is a Creation and points at its right-click menu. Ignore Update
and the highlight legend only apply to Nexus files and are turned off
meanwhile.
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
