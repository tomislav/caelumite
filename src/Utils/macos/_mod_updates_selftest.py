"""Self-checks for installing a found Nexus update in place of its mod
(Utils/macos/mod_updates.py) and the hooks in gui_qt/app.py.

Run from src/: python -m Utils.macos._mod_updates_selftest

Uses a temporary staging folder; nothing is downloaded or installed.
"""

from __future__ import annotations

import ast
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2]


@dataclass
class _Change:
    mod_name: str
    previous_meta: object
    operation: str = "update"
    source: str = "nexus"


@dataclass
class _Meta:
    file_id: int = 0
    mod_id: int = 0
    file_category: str = ""


def _nexus_meta(mod_id: int, file_id: int, latest_file_id: int, domain="starfield",
                category=""):
    from Nexus.nexus_meta import NexusModMeta
    return NexusModMeta(game_domain=domain, mod_id=mod_id, file_id=file_id,
                        latest_file_id=latest_file_id, file_category=category)


def _profile(root: Path, mods: dict[str, tuple | None]):
    """A profile and staging folder; *mods* maps a name to
    (mod_id, file_id, latest_file_id[, domain]), or None for a mod without
    meta.ini."""
    from Nexus.nexus_meta import write_meta
    profile, staging = root / "profiles" / "Default", root / "mods"
    profile.mkdir(parents=True)
    lines = []
    for name, ids in mods.items():
        (staging / name).mkdir(parents=True)
        if ids is not None:
            write_meta(staging / name / "meta.ini", _nexus_meta(*ids))
        lines.append(f"+{name}")
    (profile / "modlist.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return profile, staging


def _names(paths, metas, changes, preferred=None):
    from Utils.macos.mod_updates import in_place_names
    return in_place_names(paths, metas, changes, preferred)


def test_found_update_keeps_the_mod_name() -> None:
    change = _Change("FTL - Grav Jump Overhaul", _nexus_meta(17971, 73000, 73555))
    names = _names(["a.zip"], {"a.zip": _Meta(73555, 17971)}, {"a.zip": change})
    assert names == {"a.zip": "FTL - Grav Jump Overhaul"}, names


def test_other_files_keep_their_own_name() -> None:
    change = _Change("FTL - Grav Jump Overhaul", _nexus_meta(17971, 73000, 73555))
    for meta in (_Meta(70000, 17971), None):
        metas = {"a.zip": meta} if meta is not None else None
        assert _names(["a.zip"], metas, {"a.zip": change}) is None, meta
    no_update = _Change("FTL", _nexus_meta(17971, 73000, 0))
    assert _names(["a.zip"], {"a.zip": _Meta(0, 17971)}, {"a.zip": no_update}) is None


def test_reinstalling_the_installed_file_keeps_its_own_name() -> None:
    # An up-to-date mod's latestfileid is its own file: that's no update.
    current = _Change("FTL", _nexus_meta(17971, 73555, 73555))
    assert _names(["a.zip"], {"a.zip": _Meta(73555, 17971)}, {"a.zip": current}) is None


def test_rollbacks_forced_names_and_other_sources_are_untouched() -> None:
    meta = {"a.zip": _Meta(73555, 17971)}
    previous = _nexus_meta(17971, 73000, 73555)
    rollback = _Change("FTL", previous, operation="rollback")
    assert _names(["a.zip"], meta, {"a.zip": rollback}) is None
    thunderstore = _Change("FTL", previous, source="thunderstore")
    assert _names(["a.zip"], meta, {"a.zip": thunderstore}) is None
    forced = {"a.zip": "Chosen"}
    assert _names(["a.zip"], meta, {"a.zip": _Change("FTL", previous)}, forced) == forced
    assert _names(["a.zip"], meta, None) is None
    assert _names(["a.zip"], meta, {"a.zip": None}) is None


def test_other_forced_names_are_kept() -> None:
    change = _Change("FTL", _nexus_meta(17971, 73000, 73555))
    names = _names(["a.zip", "b.zip"], {"a.zip": _Meta(73555, 17971)},
                   {"a.zip": change}, {"b.zip": "Other"})
    assert names == {"b.zip": "Other", "a.zip": "FTL"}, names


def _picked(installed_category, picked_category, picked_id=73589, mod_id=18465):
    """Change Version on ScreenSFSE (file 72913, no update recorded): the
    folder name the picked file installs under, or None for its own name."""
    change = _Change("ScreenSFSE", _nexus_meta(18465, 72913, 0, category=installed_category))
    names = _names(["a.zip"], {"a.zip": _Meta(picked_id, mod_id, picked_category)},
                   {"a.zip": change})
    return (names or {}).get("a.zip")


def test_same_place_on_the_page_replaces_in_place() -> None:
    assert _picked("OLD_VERSION", "MAIN") == "ScreenSFSE", "old version to current main"
    assert _picked("MAIN", "MAIN") == "ScreenSFSE", "main to main"
    assert _picked("MAIN", "OLD_VERSION") == "ScreenSFSE", "back to an old version"
    assert _picked("MISCELLANEOUS", "MISCELLANEOUS") == "ScreenSFSE", "FTL's betas"
    assert _picked("Main", "main ") == "ScreenSFSE", "categories compare loosely"
    assert _picked("ARCHIVED", "OPTIONAL") == "ScreenSFSE"


def test_other_places_on_the_page_keep_their_own_name() -> None:
    assert _picked("MAIN", "OPTIONAL") is None, "an add-on on the same page"
    assert _picked("MAIN", "UPDATE") is None
    assert _picked("", "MAIN") is None, "installed category unknown"
    assert _picked("MAIN", "") is None, "picked category unknown"
    assert _picked("MAIN", "MAIN", picked_id=72913) is None, "reinstalling the same file"
    assert _picked("MAIN", "MAIN", mod_id=99999) is None, "another Nexus mod"


def test_link_finds_the_mod_it_updates() -> None:
    from Utils.macos.mod_updates import update_target
    with tempfile.TemporaryDirectory() as tmp:
        profile, staging = _profile(Path(tmp), {
            "States of Matter": (13686, 69711, 73557),
            "The Space Economy - States of the Matter Patch": (14000, 1, 2),
            "Loose files": None,
        })
        assert update_target(profile, staging, "starfield", 13686, 73557) == "States of Matter"
        assert update_target(profile, staging, "starfield", 13686, 70000) is None
        assert update_target(profile, staging, "starfield", 99999, 73557) is None


def test_link_to_the_installed_file_is_no_update() -> None:
    from Utils.macos.mod_updates import update_target
    with tempfile.TemporaryDirectory() as tmp:
        profile, staging = _profile(Path(tmp), {"States of Matter": (13686, 73557, 73557)})
        assert update_target(profile, staging, "starfield", 13686, 73557) is None


def test_link_matches_the_game_domain() -> None:
    from Utils.macos.mod_updates import update_target
    with tempfile.TemporaryDirectory() as tmp:
        profile, staging = _profile(Path(tmp), {
            "Site tool": (13686, 69711, 73557, "site"),
            "Legacy": (14000, 1, 2, ""),
        })
        assert update_target(profile, staging, "starfield", 13686, 73557) is None
        assert update_target(profile, staging, "site", 13686, 73557) == "Site tool"
        # A blank domain belongs to the profile's game, like the update check.
        assert update_target(profile, staging, "starfield", 14000, 2) == "Legacy"


def test_link_with_two_candidates_installs_as_before() -> None:
    from Utils.macos.mod_updates import update_target
    with tempfile.TemporaryDirectory() as tmp:
        profile, staging = _profile(Path(tmp), {
            "States of Matter": (13686, 69711, 73557),
            "States of Matter copy": (13686, 69711, 73557),
        })
        assert update_target(profile, staging, "starfield", 13686, 73557) is None


def test_link_ignores_separators_and_missing_folders() -> None:
    from Utils.macos.mod_updates import update_target
    with tempfile.TemporaryDirectory() as tmp:
        profile, staging = _profile(Path(tmp), {"States of Matter": (13686, 69711, 73557)})
        with (profile / "modlist.txt").open("a", encoding="utf-8") as f:
            f.write("+Gone\n-Gameplay_separator\n")
        assert update_target(profile, staging, "starfield", 13686, 73557) == "States of Matter"


def test_link_skips_profile_groups() -> None:
    from Utils.macos import mod_updates
    with tempfile.TemporaryDirectory() as tmp:
        profile, staging = _profile(Path(tmp), {"States of Matter": (13686, 69711, 73557)})
        with patch("Utils.profiles.groups.is_group", lambda _p: True):
            assert mod_updates.update_target(profile, staging, "starfield", 13686, 73557) is None


def test_link_captures_the_update_and_logs_it() -> None:
    from Utils.macos import mod_updates
    from Utils.mods.version_history import VersionChangeContext
    captured, logged = [], []

    def capture(game, profile_dir, mod_name, source, operation="update"):
        captured.append((game, profile_dir, mod_name, source, operation))
        return "change"

    with tempfile.TemporaryDirectory() as tmp:
        profile, staging = _profile(Path(tmp), {"States of Matter": (13686, 69711, 73557)})
        with patch.object(VersionChangeContext, "capture", capture):
            change = mod_updates.nxm_update("game", profile, staging, "starfield",
                                            13686, 73557, log_fn=logged.append)
            assert mod_updates.nxm_update("game", profile, staging, "starfield",
                                          13686, 1, log_fn=logged.append) is None
            assert mod_updates.nxm_update("game", None, staging, "starfield",
                                          13686, 73557) is None
    assert change == "change", change
    assert captured == [("game", profile, "States of Matter", "nexus", "update")], captured
    assert len(logged) == 1 and "States of Matter" in logged[0], logged


def test_link_falls_back_when_capture_fails() -> None:
    from Utils.macos import mod_updates
    from Utils.mods.version_history import VersionChangeContext
    logged = []

    def capture(*_args, **_kw):
        raise ValueError("broken")

    with tempfile.TemporaryDirectory() as tmp:
        profile, staging = _profile(Path(tmp), {"States of Matter": (13686, 69711, 73557)})
        with patch.object(VersionChangeContext, "capture", capture):
            assert mod_updates.nxm_update("game", profile, staging, "starfield",
                                          13686, 73557, log_fn=logged.append) is None
    assert logged and "broken" in logged[0], logged


def test_page_behind_the_installed_version() -> None:
    from Utils.macos.mod_updates import page_is_behind
    assert page_is_behind("1.3", "2.0.3")
    for page, installed in (("2.1", "2.0.3"), ("2.0.3", "2.0.3"), ("v2.0.3", "2.0.3"),
                            ("", "2.0.3"), ("1.3", ""), ("Beta", "2.0.3"),
                            ("1.3", "latest")):
        assert not page_is_behind(page, installed), (page, installed)


class _Api:
    """The GraphQL batch the update check asks for mods without a file ID."""

    def __init__(self, infos) -> None:
        self.infos = infos

    def graphql_mod_update_info_batch(self, _ids):
        return self.infos

    def get_endorsements(self):
        return []


def test_update_check_flags_only_real_updates() -> None:
    from Nexus.nexus_api import NexusModUpdateInfo
    from Nexus.nexus_meta import NexusModMeta
    from Nexus.nexus_update_checker import _check_for_updates_one_domain
    pages = {1: "1.3", 2: "1.3", 3: "2.1", 4: "Beta"}
    installed = {1: "2.0.3", 2: "1.3", 3: "2.0", 4: "2.0"}
    infos = {mid: NexusModUpdateInfo(mod_id=mid, name=f"Mod {mid}", version=page,
                                     viewer_update_available=True)
             for mid, page in pages.items()}
    metas = [NexusModMeta(game_domain="starfield", mod_id=mid, version=version,
                          mod_name=f"Mod {mid}")
             for mid, version in installed.items()]
    with tempfile.TemporaryDirectory() as tmp:
        updates, _missing = _check_for_updates_one_domain(
            _Api(infos), Path(tmp), "starfield", save_results=False,
            installed_mods=metas)
    flagged = {u.mod_id for u in updates}
    # 1: page 1.3 behind installed 2.0.3 (the Real Fuel patch) - no update.
    # 2: page not bumped (1.3) but Nexus says a new file exists - update.
    # 3: newer page - update. 4: unreadable page - Nexus's flag decides.
    assert flagged == {2, 3, 4}, flagged


def test_update_check_judges_each_copy_of_a_mod() -> None:
    from Nexus.nexus_api import NexusModUpdateInfo
    from Nexus.nexus_meta import NexusModMeta
    from Nexus.nexus_update_checker import _check_for_updates_one_domain
    infos = {5: NexusModUpdateInfo(mod_id=5, name="Mod 5", version="1.3",
                                   viewer_update_available=True)}
    # Two local mods from one Nexus page: the first is ahead of the page, the
    # second level with it (a new file without a page bump). Ignoring the flag
    # for the first must not hide the second's.
    metas = [NexusModMeta(game_domain="starfield", mod_id=5, version=version,
                          mod_name=name)
             for name, version in (("Patch", "2.0.3"), ("Main", "1.3"))]
    with tempfile.TemporaryDirectory() as tmp:
        updates, _missing = _check_for_updates_one_domain(
            _Api(infos), Path(tmp), "starfield", save_results=False,
            installed_mods=metas)
    assert [u.mod_name for u in updates] == ["Main"], [u.mod_name for u in updates]


def test_update_check_hook_is_in_place() -> None:
    text = (SRC / "Nexus" / "nexus_update_checker.py").read_text(encoding="utf-8")
    path_a = text.index("# --- Path A")
    hook = text.index("without_stale_flag(gql_info.get(mod_id), meta.version)")
    path_b = text.index("# --- Path B")
    assert path_a < hook < path_b, "hook must sit on Path A"
    upstream = "            if info is not None and info.viewer_update_available is True:\n"
    assert hook < text.index(upstream) < path_b, "upstream's Path A line must stay unchanged"
    assert "\nimport sys\n" in text


def _method_source(name: str) -> str:
    text = (SRC / "gui_qt" / "app.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node)
    raise AssertionError(f"MainWindow.{name} not found")


def test_hooks_are_in_place() -> None:
    install = _method_source("_install_paths")
    assert "in_place_names(paths, metas, version_changes, preferred_names)" in install
    assert install.index("in_place_names(") < install.index("self._fomod_controller()")
    nxm = _method_source("_on_nxm_download_done")
    assert "nxm_update(" in nxm
    assert nxm.index("nxm_update(") < nxm.index("for change in changes")


if __name__ == "__main__":
    test_found_update_keeps_the_mod_name()
    print("✓ the update the check found installs under the mod's own name")
    test_other_files_keep_their_own_name()
    print("✓ other files of the mod still install under their own name")
    test_rollbacks_forced_names_and_other_sources_are_untouched()
    print("✓ rollbacks, forced names and other sources are left alone")
    test_other_forced_names_are_kept()
    print("✓ names other archives already have are kept")
    test_same_place_on_the_page_replaces_in_place()
    print("✓ a file in the installed file's place on the page replaces it in place")
    test_other_places_on_the_page_keep_their_own_name()
    print("✓ add-ons, unknown categories and the same file keep their own name")
    test_link_finds_the_mod_it_updates()
    print("✓ a Mod Manager Download finds the mod it updates")
    test_link_with_two_candidates_installs_as_before()
    print("✓ two candidate mods install as before")
    test_link_ignores_separators_and_missing_folders()
    print("✓ separators and missing mod folders are skipped")
    test_link_skips_profile_groups()
    print("✓ Profile Groups install as before")
    test_link_captures_the_update_and_logs_it()
    print("✓ the update is captured for rollback and logged")
    test_link_falls_back_when_capture_fails()
    print("✓ a failed capture installs as before and logs why")
    test_hooks_are_in_place()
    print("✓ the install and nxm hooks are in place")
    test_reinstalling_the_installed_file_keeps_its_own_name()
    print("✓ reinstalling the installed file isn't treated as its update")
    test_link_to_the_installed_file_is_no_update()
    print("✓ a Mod Manager Download of the installed file isn't an update")
    test_link_matches_the_game_domain()
    print("✓ the link only matches mods of its Nexus game")
    test_page_behind_the_installed_version()
    print("✓ a page version behind the installed one is recognised")
    test_update_check_flags_only_real_updates()
    print("✓ the update check ignores Nexus's flag only when the page is behind")
    test_update_check_judges_each_copy_of_a_mod()
    print("✓ each local copy of a Nexus mod is judged on its own")
    test_update_check_hook_is_in_place()
    print("✓ the update check hook sits on the Nexus-flag path")
