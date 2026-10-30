"""
Utils.macos.resources
The built-in repositories for manager plugins (amethyst_plugins/sources.py)
and game handlers (Utils/github/handler_sources.py).

Upstream's built-in source for both is a folder of its own Resources
branch. Caelumite runs that code, so its built-in source is the same folder
of Caelumite's Resources branch instead, which is reviewed before it's
pushed (docs/UPSTREAM.md). Upstream's repository can still be added as an
ordinary repository; it's never the built-in one.
"""

from __future__ import annotations

from Utils.macos.app import REPO_SLUG, REPO_URL, RESOURCES_BRANCH


def builtin_source(normalize_repository, folder: str):
    """(normalize_source, DEFAULT_SOURCE) for *folder* of Caelumite's
    Resources branch, replacing the module's upstream pair."""
    builtin = (REPO_SLUG.lower(), RESOURCES_BRANCH, folder)

    def normalize_source(url, branch="", folder="", enabled=True):
        source = normalize_repository(url, branch, folder, enabled)
        if (source["repository"].lower(), source["branch"], source["folder"]) == builtin:
            source["id"] = "builtin"
        return source

    return normalize_source, normalize_source(REPO_URL, RESOURCES_BRANCH, folder)
