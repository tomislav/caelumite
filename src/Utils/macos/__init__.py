"""
Utils.macos
macOS platform support for Caelumite: CrossOver bottle discovery and the
launch/tool runner that drives games and Windows tools inside a bottle.

Shared upstream modules call into this package from small
``sys.platform == "darwin"`` branches, so the rest of the code base stays
identical to upstream and keeps merging cleanly.
"""
