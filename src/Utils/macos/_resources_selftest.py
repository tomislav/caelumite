"""Self-checks for the built-in plugin and game-handler sources
(Utils/macos/resources.py): both come from Caelumite's own Resources branch.

Run from src/: python -m Utils.macos._resources_selftest

Nothing is downloaded.
"""

from __future__ import annotations

from Utils.macos.app import REPO_URL, RESOURCES_BRANCH

UPSTREAM_URL = "https://github.com/ChrisDKN/Amethyst-Mod-Manager"


def _check(module, folder: str) -> None:
    default = module.DEFAULT_SOURCE
    assert default["id"] == "builtin", default
    assert default["url"].lower() == REPO_URL.lower(), default
    assert (default["branch"], default["folder"]) == (RESOURCES_BRANCH, folder), default
    # Upstream's catalogue is an ordinary repository on macOS, never the
    # built-in one.
    upstream = module.normalize_source(UPSTREAM_URL, "Resources", folder)
    assert upstream["id"] != "builtin", upstream


def test_plugins_come_from_caelumite() -> None:
    from amethyst_plugins import sources
    _check(sources, "Plugins/v2")
    stored = dict(sources.DEFAULT_SOURCE)
    assert sources.read_source(stored)["id"] == "builtin"
    assert sources.api_url(stored).endswith("/repos/tomislav/caelumite")


def test_game_handlers_come_from_caelumite() -> None:
    from Utils.github import handler_sources
    _check(handler_sources, "Custom Handlers")
    assert "repos/tomislav/caelumite/contents/Custom%20Handlers" in \
        handler_sources.listing_url(handler_sources.DEFAULT_SOURCE)


def test_store_uses_the_redirected_source() -> None:
    from amethyst_plugins import store
    assert store.DEFAULT_SOURCE["url"].lower() == REPO_URL.lower(), store.DEFAULT_SOURCE
    assert store.normalize_source(UPSTREAM_URL, "Resources", "Plugins/v2")["id"] != "builtin"


def test_config_dir_can_be_left_uncreated() -> None:
    # The plugin store and catalogue ask for the config folder without
    # creating it (get_config_dir(create=False)).
    import os
    import tempfile
    from unittest.mock import patch
    from Utils.config_paths import get_config_dir
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HOME": tmp}):
        assert not get_config_dir(create=False).exists()
        assert get_config_dir().is_dir()


def test_work_folders_stay_in_application_support() -> None:
    # Operation locks, launch leases and LOD work folders go to Caelumite's
    # own folder, not ~/.local/share/AmethystModManager.
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    from Utils.bethesda.lod_run import new_output_path
    from Utils.config_paths import get_config_dir
    from Utils.operations import _lock_dir
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HOME": tmp}):
        os.environ.pop("AMETHYST_OPERATION_LOCK_DIR", None)
        os.environ.pop("XDG_DATA_HOME", None)
        config = get_config_dir().resolve()
        assert _lock_dir().resolve().is_relative_to(config), _lock_dir()
        assert new_output_path().is_relative_to(config), new_output_path()
        assert not (Path(tmp) / ".local").exists()


if __name__ == "__main__":
    test_plugins_come_from_caelumite()
    print("✓ the built-in plugin catalogue is Caelumite's Resources branch")
    test_game_handlers_come_from_caelumite()
    print("✓ built-in game handlers come from Caelumite's Resources branch")
    test_store_uses_the_redirected_source()
    print("✓ the plugin store sees the redirected source")
    test_config_dir_can_be_left_uncreated()
    print("✓ the config folder isn't created when asked not to")
    test_work_folders_stay_in_application_support()
    print("✓ operation locks and LOD work folders stay in Application Support")
