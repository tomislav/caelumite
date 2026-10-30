"""Self-checks for importing Bethesda Creations (Utils/macos/creations.py).

Run from src/: python -m Utils.macos._creations_selftest

Everything runs in temporary folders on a Starfield handler pointed at them;
the real game, its bottle and the mod staging folder are never touched.
"""

from __future__ import annotations

import configparser
import json
import os
import tempfile
from pathlib import Path

from Utils.macos.creations import (
    Creation, adopt_creations, catalog_path, creation_mod_name,
    creation_tooltip, creation_url, creations_changed, display_version,
    files_index, is_creation,
    plugin_creations, read_catalog,
)
from Utils.mods.modlist import ModEntry, read_modlist

ACD_FILES = ["bnw_autoclosedoors.esm", "bnw_autoclosedoors - main.ba2"]


def _catalog_json(entries: dict, timestamp: int = 1793027204) -> str:
    data: dict = {"ContentCatalog": {"Description": "test", "Version": "1.1"}}
    for cid, (title, version, files) in entries.items():
        entry = {"AchievementSafe": False, "FilesSize": 0,
                 "Timestamp": timestamp, "Title": title, "Version": version}
        if files is not None:
            entry["Files"] = files
        data[cid] = entry
    return json.dumps(data, indent=2)


class Layout:
    """A Starfield handler whose game, prefix and staging live in *tmp*."""

    def __init__(self, tmp: Path, game_class=None) -> None:
        if game_class is None:
            from Games.Bethesda.starfield import Starfield as game_class
        self.tmp = tmp
        self.root = tmp / "root"
        self.staging = self.root / "mods"
        self.overwrite = self.root / "overwrite"
        self.profile = self.root / "profiles" / "default"
        self.data = tmp / "game" / "Data"
        for folder in (self.staging, self.overwrite, self.profile, self.data):
            folder.mkdir(parents=True)
        game = game_class()
        game._prefix_path = tmp / "prefix"
        game._game_path = tmp / "game"
        game.get_profile_root = lambda: self.root
        game.get_effective_mod_staging_path = lambda: self.staging
        self.game = game
        (self.data / "Starfield.esm").write_bytes(b"vanilla")
        (self.profile / "plugins.txt").write_text("*Starfield.esm\n",
                                                  encoding="utf-8")
        self.modlist("+Other")
        self.logs: list[str] = []

    def catalog(self, entries: dict, timestamp: int = 1793027204) -> None:
        path = catalog_path(self.game)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_catalog_json(entries, timestamp), encoding="utf-8")

    def modlist(self, *lines: str) -> None:
        (self.profile / "modlist.txt").write_text(
            "".join(line + "\n" for line in lines), encoding="utf-8")

    def mod(self, name: str, files: dict[str, bytes], **meta: str) -> Path:
        folder = self.staging / name
        folder.mkdir()
        for file, content in files.items():
            (folder / file).write_bytes(content)
        if meta:
            (folder / "meta.ini").write_text(
                "[General]\n" + "".join(f"{k}={v}\n" for k, v in meta.items()),
                encoding="utf-8")
        return folder

    def adopt(self, **kwargs) -> list[str]:
        return adopt_creations(self.game, self.profile, log_fn=self.logs.append,
                               **kwargs)


def read_meta_ini(mod: Path):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.read(mod / "meta.ini", encoding="utf-8")
    return cp["General"]


ACD = "[Creations] Auto Close Doors (ACD)"
ACD_ENTRY = ("Auto Close Doors (ACD)", "1792106932.3.2.2", ACD_FILES)


def test_read_catalog() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ContentCatalog.txt"
        path.write_text(_catalog_json({
            "TM_a": ("Auto Close Doors (ACD)", "1792106932.3.2.2", ACD_FILES),
            "TM_b": ("Deimog", "1700000000.1.0", ["deimog.esm"]),
            "TM_c": ("No Files", "1700000000.1.0", None),
        }), encoding="utf-8-sig")
        cat = read_catalog(path)
        assert set(cat) == {"TM_a", "TM_b"}, cat
        assert cat["TM_a"] == Creation(
            "TM_a", "Auto Close Doors (ACD)", "1792106932.3.2.2",
            ("bnw_autoclosedoors.esm", "bnw_autoclosedoors - main.ba2"),
            False), cat["TM_a"]
        assert files_index(cat)["bnw_autoclosedoors - main.ba2"].id == "TM_a"


def test_read_catalog_bad_input() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        logs: list[str] = []
        assert read_catalog(tmp / "missing.txt", logs.append) == {}
        assert read_catalog(None, logs.append) == {}
        assert logs == []
        (tmp / "bad.txt").write_text("{not json", encoding="utf-8")
        assert read_catalog(tmp / "bad.txt", logs.append) == {}
        assert len(logs) == 1 and logs[0].startswith("Creations: WARN"), logs


def test_names() -> None:
    assert (creation_mod_name("Lambent: Street Rat Ship Services")
            == "Lambent- Street Rat Ship Services")
    assert (creation_mod_name("A New Coat of Paint | The Dream Home")
            == "A New Coat of Paint - The Dream Home")
    assert creation_mod_name("Deimog") == "Deimog"
    assert display_version("1776917616.2.2") == "2.2"
    assert display_version("3") == "3"
    assert display_version("1.1") == "1.1"   # no timestamp part
    assert display_version("1700000000.") == "1700000000."


def test_new_creation_from_overwrite() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_d": ("Deimog", "1700000000.1.0",
                            ["deimog.esm", "deimog - main.ba2"])})
        for name in ("deimog.esm", "deimog - main.ba2", "unrelated.esm"):
            (t.overwrite / name).write_bytes(name.encode())
        assert t.adopt() == ["Deimog"], t.logs
        mod = t.staging / "Deimog"
        assert sorted(p.name for p in mod.iterdir()) == [
            "deimog - main.ba2", "deimog.esm", "meta.ini"]
        meta = read_meta_ini(mod)
        assert meta["creationid"] == "TM_d" and meta["categoryname"] == "Creations"
        assert meta["version"] == "1.0" and meta["installed"]
        assert read_modlist(t.profile / "modlist.txt")[0] == ModEntry(
            "Deimog", True, False)
        assert (t.overwrite / "unrelated.esm").is_file()
        assert any("'Deimog' → Deimog (2 new, 0 updated, 0 unchanged)" in line
                   for line in t.logs), t.logs


def test_existing_disabled_mod_identical_copy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm", ACD_FILES[1]: b"old"})
        t.modlist("+Other", "-" + ACD)
        (t.overwrite / ACD_FILES[0]).write_bytes(b"esm")
        (t.overwrite / ACD_FILES[1]).write_bytes(b"new")
        assert t.adopt() == [ACD], t.logs
        assert not (t.overwrite / ACD_FILES[0]).exists()
        assert not (t.overwrite / ACD_FILES[1]).exists()
        assert (mod / ACD_FILES[1]).read_bytes() == b"new"
        [entry] = [e for e in read_modlist(t.profile / "modlist.txt")
                   if e.name == ACD]
        assert entry.enabled is False
        assert any("enable it to keep using it" in line for line in t.logs), t.logs
        assert any("(0 new, 1 updated, 1 unchanged)" in line
                   for line in t.logs), t.logs


def test_data_scan_skips_vanilla_and_deployed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({
            "TM_v": ("Shattered Space", "1.1.0",
                     ["SFBGS003.esm", "SFBGS003 - main.ba2"]),
            "TM_l": ("Linked", "1.1.0", ["linked.esm"]),
            "TM_p": ("The Perfect Recipe", "1.1.0", ["sfbgs00c.esm"]),
        })
        for name in ("SFBGS003.esm", "SFBGS003 - main.ba2", "linked.esm",
                     "sfbgs00c.esm"):
            (t.data / name).write_bytes(name.encode())
        os.link(t.data / "linked.esm", t.tmp / "linked-elsewhere.esm")
        t.adopt()
        assert (t.data / "SFBGS003.esm").is_file()
        assert (t.data / "SFBGS003 - main.ba2").is_file()
        assert (t.data / "linked.esm").is_file()
        assert not (t.data / "sfbgs00c.esm").exists()
        assert (t.staging / "The Perfect Recipe" / "sfbgs00c.esm").is_file()
        assert "*sfbgs00c.esm" in (t.profile / "plugins.txt").read_text()
        assert t.adopt() == [], t.logs


def test_name_collision() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_d": ("Deimog", "1700000000.1.0", ["deimog.esm"])})
        t.mod("Deimog", {"readme.txt": b"a Nexus mod"})
        t.modlist("+Deimog")
        (t.overwrite / "deimog.esm").write_bytes(b"esm")
        assert t.adopt() == ["Deimog (2)"], t.logs
        assert (t.staging / "Deimog (2)" / "deimog.esm").is_file()


def test_update_refreshes_version_and_xedit_flag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ("Auto Close Doors (ACD)", "1795000000.3.3",
                            ACD_FILES)})
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm", ACD_FILES[1]: b"ba2"},
                    creationId="TM_a", creationVersion="1792106932.3.2.2",
                    xeditModifiedPlugins="bnw_autoclosedoors.esm;Other.esp")
        assert t.adopt() == [], t.logs
        meta = read_meta_ini(mod)
        assert meta["creationversion"] == "1795000000.3.3"
        assert meta["version"] == "3.3"
        assert meta["updated"]
        assert meta["xeditmodifiedplugins"] == "Other.esp"
        assert any("updated to 3.3" in line for line in t.logs), t.logs


def test_same_version_keeps_xedit_flag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm", ACD_FILES[1]: b"ba2",
                          "bnw_autoclosedoors - old.ba2": b"old"},
                    creationId="TM_a", creationVersion="1792106932.3.2.2",
                    version="3.2.2",
                    xeditModifiedPlugins="bnw_autoclosedoors.esm;Other.esp")
        before = (mod / "meta.ini").stat().st_mtime_ns
        assert t.adopt() == [], t.logs
        assert (read_meta_ini(mod)["xeditmodifiedplugins"]
                == "bnw_autoclosedoors.esm;Other.esp")
        assert (mod / "meta.ini").stat().st_mtime_ns == before
        assert (mod / "bnw_autoclosedoors - old.ba2").is_file()


def test_update_moves_removed_files_to_backup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ("Auto Close Doors (ACD)", "1795000000.3.3",
                            ACD_FILES)})
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm", ACD_FILES[1]: b"ba2",
                          "bnw_autoclosedoors - old.ba2": b"old",
                          "readme.txt": b"readme"},
                    creationId="TM_a", creationVersion="1792106932.3.2.2")
        assert t.adopt() == [mod.name], t.logs
        assert not (mod / "bnw_autoclosedoors - old.ba2").exists()
        assert (mod / "readme.txt").is_file()
        assert (mod / ACD_FILES[0]).is_file()
        [backup] = (t.root / "creations_backup").glob("*/*/*")
        assert backup.name == "bnw_autoclosedoors - old.ba2"
        assert backup.parent.name == mod.name
        assert any("no longer uses bnw_autoclosedoors - old.ba2" in line
                   for line in t.logs), t.logs


def test_update_cleanup_skips_mod_with_two_creations() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({
            "TM_a": ("Auto Close Doors (ACD)", "1795000000.3.3", ACD_FILES),
            "TM_b": ("Other Creation", "1700000000.1.0", ["other.esm"]),
        })
        mod = t.mod("[Creations] Two", {
            ACD_FILES[0]: b"esm", "other.esm": b"other",
            "unlisted - main.ba2": b"ba2"},
            creationId="TM_a", creationVersion="1792106932.3.2.2")
        t.adopt()
        assert (mod / "unlisted - main.ba2").is_file()
        assert not (t.root / "creations_backup").exists()
        meta = read_meta_ini(mod)
        assert meta["creationid"] == "TM_a", dict(meta)


def test_first_sighting_records_version() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({
            "TM_a": ACD_ENTRY,
            "TM_s": ("Ship Builder", "1700000000.1.0", ["ship.esm"]),
        })
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm"},
                    xeditModifiedPlugins="bnw_autoclosedoors.esm")
        ships_mod = t.mod("[Creations] Ship Builder", {"ship.esm": b"ship"},
                          categoryName="Ships")
        assert t.adopt() == [], t.logs
        meta = read_meta_ini(mod)
        assert meta["creationid"] == "TM_a"
        assert meta["creationversion"] == "1792106932.3.2.2"
        assert meta["categoryname"] == "Creations" and "updated" not in meta
        assert read_meta_ini(ships_mod)["categoryname"] == "Ships"
        assert meta["xeditmodifiedplugins"] == "bnw_autoclosedoors.esm"
        assert not any("updated to" in line for line in t.logs), t.logs


def test_creations_changed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        assert creations_changed(t.game) is False   # no catalog
        t.catalog({"TM_a": ACD_ENTRY})
        t.mod(ACD, {ACD_FILES[0]: b"esm", ACD_FILES[1]: b"ba2"})
        assert creations_changed(t.game) is True    # no stored fingerprint
        t.adopt()
        assert creations_changed(t.game) is False
        t.catalog({"TM_a": ACD_ENTRY}, timestamp=1799999999)
        assert creations_changed(t.game) is False   # only timestamps changed
        t.catalog({"TM_a": ("Auto Close Doors (ACD)", "1795000000.3.3",
                            ACD_FILES)})
        assert creations_changed(t.game) is True


def test_plugin_creations() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        assert plugin_creations(t.game) == {}
        t.catalog({"TM_a": ("Auto Close Doors (ACD)", "1792106932.3.2.2",
                            ["BNW_AutoCloseDoors.esm",
                             "BNW_AutoCloseDoors - Main.ba2"])})
        t.mod(ACD, {"bnw_autoclosedoors.esm": b"esm",
                    "bnw_autoclosedoors - main.ba2": b"ba2"})
        found = plugin_creations(t.game)
        assert set(found) == {"bnw_autoclosedoors.esm"}, found
        creation = found["bnw_autoclosedoors.esm"]
        assert creation.title == "Auto Close Doors (ACD)"
        assert creation_tooltip(creation) == "Creation: Auto Close Doors (ACD) 3.2.2"
        safe = Creation("TM_s", "Safe", "1700000000.0.1", ("safe.esm",), True)
        assert creation_tooltip(safe) == "Creation: Safe 0.1\nAchievement-friendly"
    assert plugin_creations(object()) == {}


def test_skyrim_vanilla_archives_stay() -> None:
    from Games.Bethesda.skyrim_se import SkyrimSE
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp), SkyrimSE)
        (t.data.parent / "Skyrim.ccc").write_text("ccBGSSSE001-Fish.esm\n")
        t.catalog({"TM_f": ("Fishing", "1700000000.1.0",
                            ["ccBGSSSE001-Fish.esm", "ccBGSSSE001-Fish.bsa"])})
        for name in ("ccBGSSSE001-Fish.esm", "ccBGSSSE001-Fish.bsa"):
            (t.data / name).write_bytes(name.encode())
        assert t.adopt() == [], t.logs
        assert (t.data / "ccBGSSSE001-Fish.bsa").is_file()


def test_tooltips_only_for_creation_mods() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY,
                   "TM_d": ("Deimog", "1700000000.1.0", ["deimog.esm"])})
        t.mod(ACD, {ACD_FILES[0]: b"esm"})
        t.mod("Deimog", {"deimog.esm": b"a Nexus mod with that plugin name"})
        assert set(plugin_creations(t.game)) == {ACD_FILES[0]}


def test_stray_file_takes_the_name() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_1": ("Alpha", "1700000000.1.0", ["alpha.esm"])})
        (t.staging / "Alpha").write_bytes(b"a stray file")
        (t.data / "alpha.esm").write_bytes(b"alpha")
        assert t.adopt() == ["Alpha (2)"], t.logs


def test_one_failing_creation_keeps_the_rest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_1": ("Alpha", "1700000000.1.0", ["alpha.esm"]),
                   "TM_2": ("Beta", "1700000000.1.0", ["beta.esm"])})
        locked = t.mod("[Creations] Alpha", {"readme.txt": b"x"},
                       creationId="TM_1", creationVersion="1700000000.1.0")
        (t.data / "alpha.esm").write_bytes(b"alpha")
        (t.data / "beta.esm").write_bytes(b"beta")
        locked.chmod(0o500)
        try:
            assert t.adopt() == ["Beta"], t.logs
        finally:
            locked.chmod(0o700)
        assert any(line.startswith("Creations: WARN: 'Alpha'") for line in t.logs), t.logs
        assert (t.data / "alpha.esm").is_file()
        assert "*beta.esm" in (t.profile / "plugins.txt").read_text()
        assert creations_changed(t.game) is True   # retried on the next deploy


def test_in_game_plugin_state_is_kept() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_p": ("The Perfect Recipe", "1.1.0", ["sfbgs00c.esm"])})
        (t.data / "sfbgs00c.esm").write_bytes(b"esm")
        t.adopt(enabled_states={"sfbgs00c.esm": False})
        lines = (t.profile / "plugins.txt").read_text().split()
        assert "sfbgs00c.esm" in lines and "*sfbgs00c.esm" not in lines, lines


def test_mod_missing_from_profile_is_logged() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        t.mod(ACD, {ACD_FILES[0]: b"esm"})
        (t.overwrite / ACD_FILES[1]).write_bytes(b"ba2")
        t.adopt()
        assert any("isn't in this profile's mod list" in line
                   for line in t.logs), t.logs


def _restore_rewritten_plugin(content: bytes, name: str = ACD_FILES[0]
                              ) -> tuple[bytes, list[str], int]:
    """Restore after the game rewrote a deployed file *name* with *content*.

    Returns the mod's file bytes, its meta.ini lines afterwards, and how
    often Restore compared file contents.
    """
    with tempfile.TemporaryDirectory() as tmp:
        return _restore_in(Path(tmp), content, name)


def _restore_in(tmp: Path, content: bytes,
                name: str) -> tuple[bytes, list[str], int]:
    import types
    from unittest.mock import patch
    import Utils.macos.creations as creations
    from Utils.deployment import move_to_core, restore_data_core

    deploy_dir = tmp / "Data"
    deploy_dir.mkdir()
    (deploy_dir / "vanilla.esm").write_bytes(b"vanilla")
    move_to_core(deploy_dir)
    staging = tmp / "mods"
    mod = staging / ACD
    mod.mkdir(parents=True)
    (mod / name).write_bytes(b"esm")
    os.utime(mod / name, (1_600_000_000, 1_600_000_000))
    (deploy_dir / name).write_bytes(content)   # the game's new copy
    game = types.SimpleNamespace(
        get_effective_mod_staging_path=lambda: staging)
    entry = types.SimpleNamespace(provider_kind="mod", mod_name=ACD,
                                  source_rel=name.encode())
    compared = []
    real_same = creations.same_content

    def spy(*args):
        compared.append(args)
        return real_same(*args)

    with (patch("Utils.filegraph.deploy.deployed_entries_for",
                return_value=[entry]),
          patch("Utils.filegraph.deploy.entry_relative_to",
                return_value=name),
          patch("Utils.filegraph.service.source_path",
                side_effect=lambda _g, m, rel: str(staging / m / rel.decode())),
          patch.object(creations, "same_content", side_effect=spy)):
        restore_data_core(deploy_dir, overwrite_dir=tmp / "overwrite",
                          game=game, profile_dir=tmp / "profile",
                          log_fn=lambda _line: None)
    meta = mod / "meta.ini"
    return ((mod / name).read_bytes(),
            meta.read_text().splitlines() if meta.is_file() else [],
            len(compared))


def test_restore_drops_identical_rewrite() -> None:
    plugin, meta, _ = _restore_rewritten_plugin(b"esm")
    assert not any("xeditmodifiedplugins" in line.lower() for line in meta), meta
    assert plugin == b"esm"


def test_restore_still_tags_real_edit() -> None:
    plugin, meta, _ = _restore_rewritten_plugin(b"edited in xEdit")
    assert any("xeditmodifiedplugins" in line.lower() for line in meta), meta
    assert plugin == b"edited in xEdit"


def test_restore_compares_only_plugins() -> None:
    archive, _, compared = _restore_rewritten_plugin(b"esm", ACD_FILES[1])
    assert compared == 0
    assert archive == b"esm"


def test_failed_move_keeps_the_mod_file() -> None:
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        mod = t.mod(ACD, {ACD_FILES[0]: b"old"})
        t.modlist("+" + ACD)
        (t.overwrite / ACD_FILES[0]).write_bytes(b"new")
        with patch("Utils.macos.creations.shutil.move",
                   side_effect=OSError("disk full")):
            t.adopt()
        assert (mod / ACD_FILES[0]).read_bytes() == b"old"
        assert (t.overwrite / ACD_FILES[0]).read_bytes() == b"new"


def test_percent_in_kept_xedit_names_survives() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ("Auto Close Doors (ACD)", "1795000000.3.3",
                            ACD_FILES)})
        # As upstream writes it: ConfigParser escapes % as %%.
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm", ACD_FILES[1]: b"ba2"},
                    creationId="TM_a", creationVersion="1792106932.3.2.2",
                    xeditModifiedPlugins="bnw_autoclosedoors.esm;100%%.esp")
        t.adopt()
        cp = configparser.ConfigParser(strict=False)
        cp.read(mod / "meta.ini", encoding="utf-8")
        assert cp["General"]["xeditmodifiedplugins"] == "100%.esp"


def test_tooltip_cache_sees_changes_inside_mods() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY,
                   "TM_b": ("Second", "1700000000.1.0", ["second.esm"])})
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm"})
        assert set(plugin_creations(t.game)) == {ACD_FILES[0]}
        (mod / "second.esm").write_bytes(b"esm")   # staging's own mtime stays
        assert set(plugin_creations(t.game)) == {ACD_FILES[0], "second.esm"}


def test_overwrite_plugin_into_disabled_mod_is_unlisted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        t.mod(ACD, {ACD_FILES[0]: b"old"})
        t.modlist("+Other", "-" + ACD)
        (t.overwrite / ACD_FILES[0]).write_bytes(b"new")
        # sync_overwrite_plugins registered it before the import.
        (t.profile / "plugins.txt").write_text(
            "*Starfield.esm\n*bnw_autoclosedoors.esm\n", encoding="utf-8")
        t.adopt()
        lines = (t.profile / "plugins.txt").read_text().split()
        assert "*bnw_autoclosedoors.esm" not in lines, lines


def test_creation_url() -> None:
    from Games.Bethesda.skyrim_se import SkyrimSE
    from Games.Bethesda.starfield import Starfield
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm"},
                    creationId="TM_afe907c3-d65d-4578-a512-4cd684fd7b38")
        nexus_mod = t.mod("Nexus Mod", {"x.esm": b"x"}, modid="123")
        assert creation_url(Starfield(), mod) == (
            "https://creations.bethesda.net/en/starfield/details/"
            "afe907c3-d65d-4578-a512-4cd684fd7b38")
        assert creation_url(SkyrimSE(), mod) == (
            "https://creations.bethesda.net/en/skyrim/details/"
            "afe907c3-d65d-4578-a512-4cd684fd7b38")
        assert creation_url(Starfield(), nexus_mod) == ""
        assert creation_url(Starfield(), t.staging / "missing") == ""
        assert creation_url(object(), mod) == ""   # no Creations site
        assert creation_url(None, mod) == ""


def test_identical_overwrite_plugin_into_disabled_mod_is_unlisted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        t.mod(ACD, {ACD_FILES[0]: b"esm"})
        t.modlist("+Other", "-" + ACD)
        (t.overwrite / ACD_FILES[0]).write_bytes(b"esm")   # same bytes
        (t.profile / "plugins.txt").write_text(
            "*Starfield.esm\n*bnw_autoclosedoors.esm\n", encoding="utf-8")
        t.adopt()
        lines = (t.profile / "plugins.txt").read_text().split()
        assert "*bnw_autoclosedoors.esm" not in lines, lines


def test_plugin_of_another_enabled_mod_stays_listed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        t.mod(ACD, {ACD_FILES[0]: b"old"})
        t.mod("Nexus ACD", {ACD_FILES[0]: b"nexus"})
        t.modlist("+Nexus ACD", "-" + ACD)
        (t.overwrite / ACD_FILES[0]).write_bytes(b"new")
        (t.profile / "plugins.txt").write_text(
            "*Starfield.esm\n*bnw_autoclosedoors.esm\n", encoding="utf-8")
        t.adopt()
        assert "*bnw_autoclosedoors.esm" in (t.profile / "plugins.txt").read_text()


def test_tooltip_cache_follows_symlinked_mods() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY,
                   "TM_b": ("Second", "1700000000.1.0", ["second.esm"])})
        real = t.tmp / "elsewhere" / ACD
        real.mkdir(parents=True)
        (real / ACD_FILES[0]).write_bytes(b"esm")
        (t.staging / ACD).symlink_to(real, target_is_directory=True)
        assert set(plugin_creations(t.game)) == {ACD_FILES[0]}
        (real / "second.esm").write_bytes(b"esm")
        assert set(plugin_creations(t.game)) == {ACD_FILES[0], "second.esm"}


def test_tooltips_skip_the_scan_without_a_catalog() -> None:
    from unittest.mock import patch
    import Utils.macos.creations as creations
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.mod(ACD, {ACD_FILES[0]: b"esm"})
        with patch.object(creations.os, "scandir",
                          wraps=creations.os.scandir) as scan:
            assert plugin_creations(t.game) == {}
        assert scan.call_count == 0


def test_failed_case_rename_is_still_recorded() -> None:
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        mod = t.mod(ACD, {"BNW_AutoCloseDoors.esm": b"old"})
        t.modlist("+" + ACD)
        (t.overwrite / ACD_FILES[0]).write_bytes(b"new")
        with patch("Utils.macos.creations.os.rename",
                   side_effect=OSError("busy")):
            assert t.adopt() == [ACD], t.logs
        [plugin] = [p for p in mod.iterdir() if p.suffix == ".esm"]
        assert plugin.read_bytes() == b"new"


def test_stale_staged_file_is_removed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm",
                          f".{ACD_FILES[0]}.caelumite-new": b"half"})
        t.adopt()
        assert not (mod / f".{ACD_FILES[0]}.caelumite-new").exists()


def test_tooltip_refresh_during_import_keeps_the_new_file() -> None:
    from unittest.mock import patch
    import Utils.macos.creations as creations
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        mod = t.mod(ACD, {ACD_FILES[0]: b"old"})
        t.modlist("+" + ACD)
        (t.overwrite / ACD_FILES[0]).write_bytes(b"new")
        real_replace = os.replace

        def replace_after_tooltips(src, dst):
            plugin_creations(t.game)   # the GUI refreshing the plugin list
            return real_replace(src, dst)

        with patch.object(creations.os, "replace",
                          side_effect=replace_after_tooltips):
            t.adopt()
        assert (mod / ACD_FILES[0]).read_bytes() == b"new", t.logs


def test_creation_url_reads_only_general() -> None:
    from Games.Bethesda.starfield import Starfield
    first = "11111111-1111-1111-1111-111111111111"
    last = "22222222-2222-2222-2222-222222222222"
    other = "33333333-3333-3333-3333-333333333333"
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm"})
        (mod / "meta.ini").write_text(
            f"[other]\ncreationid = TM_{other}\n"
            f"[General]\ncreationid = TM_{first}\ncreationid = TM_{last}\n",
            encoding="utf-8")
        assert creation_url(Starfield(), mod).endswith("/" + last)
        (mod / "meta.ini").write_text(
            f"[General]\nmodid = 0\n[other]\ncreationid = TM_{other}\n",
            encoding="utf-8")
        assert creation_url(Starfield(), mod) == ""


def test_failed_case_rename_is_logged() -> None:
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({"TM_a": ACD_ENTRY})
        t.mod(ACD, {"BNW_AutoCloseDoors.esm": b"old"})
        t.modlist("+" + ACD)
        (t.overwrite / ACD_FILES[0]).write_bytes(b"new")
        with patch("Utils.macos.creations.os.rename",
                   side_effect=OSError("busy")):
            t.adopt()
        assert any(line.startswith("Creations: kept the name "
                                   "BNW_AutoCloseDoors.esm")
                   for line in t.logs), t.logs


def test_empty_versions_are_filled() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.catalog({
            "TM_a": ACD_ENTRY,
            "TM_d": ("Deimog", "1700000000.1.0", ["deimog.esm"]),
            "TM_s": ("Ship Builder", "1700000000.1.0", ["ship.esm"]),
        })
        first = t.mod(ACD, {ACD_FILES[0]: b"esm"})       # never imported
        recorded = t.mod("[Creations] Deimog", {"deimog.esm": b"esm"},
                         creationId="TM_d", creationVersion="1700000000.1.0",
                         version="")
        custom = t.mod("[Creations] Ship Builder", {"ship.esm": b"esm"},
                       creationId="TM_s", creationVersion="1700000000.1.0",
                       version="1.0-mine")
        assert t.adopt() == [], t.logs
        assert read_meta_ini(first)["version"] == "3.2.2"
        assert read_meta_ini(recorded)["version"] == "1.0"
        assert read_meta_ini(custom)["version"] == "1.0-mine"
        assert not any("updated to" in line for line in t.logs), t.logs


def test_creation_url_rejects_odd_ids() -> None:
    from Games.Bethesda.starfield import Starfield
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm"}, creationId="TM_../../evil")
        assert creation_url(Starfield(), mod) == ""


def test_creation_url_reads_upstream_format() -> None:
    from Games.Bethesda.starfield import Starfield
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        mod = t.mod(ACD, {ACD_FILES[0]: b"esm"})
        uuid = "afe907c3-d65d-4578-a512-4cd684fd7b38"
        # As set_meta_keys writes it: lowercased key, spaces around "=".
        (mod / "meta.ini").write_text(
            f"[General]\nmodid = 0\ncreationid = TM_{uuid}\n", encoding="utf-8")
        assert creation_url(Starfield(), mod) == (
            "https://creations.bethesda.net/en/starfield/details/" + uuid)


def test_pipeline_skips_the_import_while_deployed() -> None:
    from unittest.mock import patch
    from Utils.deployment import _selftest as deploy_tests
    case = deploy_tests.DeploymentTransferFailureTests(
        "test_successful_transfer_commits_filegraph")
    try:
        # Upstream's fake game predates the deploy events, which need a
        # game_id (its own pipeline tests fail the same way).
        with (patch.object(deploy_tests._PipelineGame, "game_id",
                           "transfer_failure_test", create=True),
              patch.object(deploy_tests._PipelineGame, "get_deploy_active",
                           return_value=True),
              patch("Utils.macos.creations.creations_changed",
                    return_value=True),
              patch("Utils.macos.creations.adopt_creations",
                    return_value=[]) as adopt):
            result, _game, _session, _finish, logs = case._run_pipeline(None)
    finally:
        case.doCleanups()
    assert result and adopt.call_count == 0
    assert any(line.startswith("Creations: not imported") for line in logs), logs


def test_is_creation() -> None:
    from types import SimpleNamespace
    def meta(name, mod_id=0, category=""):
        return SimpleNamespace(mod_name=name, mod_id=mod_id,
                               category_name=category)
    assert is_creation(meta("Neon Houseboat", category="Creations"))
    assert is_creation(meta(ACD))
    assert not is_creation(meta("Manual Mod"))
    assert not is_creation(meta("Nexus Mod", mod_id=5, category="Creations"))


def _qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeNexus:
    def __init__(self) -> None:
        self.asked: list[int] = []

    def get_mod_files(self, domain, mod_id):
        from types import SimpleNamespace
        self.asked.append(mod_id)
        return SimpleNamespace(files=[])


def _wait_for(condition, app, what: str) -> None:
    import time
    deadline = time.monotonic() + 5
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        app.processEvents()
        time.sleep(0.01)


def _meta(name: str, mod_id: int = 0, category: str = ""):
    from types import SimpleNamespace
    return SimpleNamespace(mod_name=name, mod_id=mod_id, category_name=category,
                           ignore_update=False, game_domain="")


def test_change_version_shows_a_creation() -> None:
    from Games.Bethesda.starfield import Starfield
    from gui_qt.nexus.change_version import ChangeVersionView, _LegendBar
    app = _qt_app()
    api = _FakeNexus()
    nexus = _meta("Nexus Mod", 123)
    view = ChangeVersionView(api, Starfield(), "Nexus Mod", nexus,
                             install_fn=None, on_close=None)
    legend = view.findChild(_LegendBar)
    _wait_for(lambda: api.asked == [123], app, "the Nexus fetch")
    view.retarget("Neon Houseboat", _meta("Neon Houseboat", category="Creations"))
    assert view.current_mod_name() == "Neon Houseboat"
    assert view._status.text() == ("Neon Houseboat is a Creation. Right-click "
                                   "it and choose Open on Creations.")
    assert not view._status.isHidden()
    assert not view._ignore_cb.isEnabled()
    assert legend.isHidden()
    view.retarget("Nexus Mod", nexus)
    _wait_for(lambda: len(api.asked) == 2, app, "the second Nexus fetch")
    assert api.asked == [123, 123], api.asked
    assert view._ignore_cb.isEnabled()
    assert not legend.isHidden()
    view.deleteLater()


def test_change_version_leaves_other_mods_to_upstream() -> None:
    from Games.Bethesda.starfield import Starfield
    from gui_qt.nexus.change_version import ChangeVersionView
    app = _qt_app()
    api = _FakeNexus()
    view = ChangeVersionView(api, Starfield(), "Nexus Mod", _meta("Nexus Mod", 123),
                             install_fn=None, on_close=None)
    _wait_for(lambda: api.asked == [123], app, "the Nexus fetch")
    view.retarget("Manual Mod", _meta("Manual Mod"))
    _wait_for(lambda: len(api.asked) == 2, app, "the upstream fetch")
    assert "is a Creation" not in view._status.text()
    view.deleteLater()


def test_change_version_follows_selection_to_a_creation() -> None:
    from types import SimpleNamespace
    from gui_qt.app import MainWindow
    with tempfile.TemporaryDirectory() as tmp:
        t = Layout(Path(tmp))
        t.mod(ACD, {ACD_FILES[0]: b"esm"},
              creationId="TM_afe907c3-d65d-4578-a512-4cd684fd7b38")
        t.mod("Neon Houseboat", {"neon.esm": b"x"}, categoryName="Creations")
        t.mod("Manual Mod", {"x.esm": b"x"}, modid="0")
        retargeted: list[str] = []
        view = SimpleNamespace(
            isVisible=lambda: True, busy=lambda: False,
            current_mod_name=lambda: "Nexus Mod",
            retarget=lambda name, meta: retargeted.append(name))
        for name in (ACD, "Neon Houseboat", "Manual Mod"):
            entry = SimpleNamespace(name=name, is_separator=False,
                                    is_group_header=False)
            rows = [SimpleNamespace(row=lambda: 0)]
            mod_view = SimpleNamespace(
                selectionModel=lambda: SimpleNamespace(
                    selectedRows=lambda: rows),
                model=lambda: SimpleNamespace(entry=lambda row: entry))
            window = SimpleNamespace(
                _change_version_view=view,
                _selected_modlist_view=lambda: mod_view,
                _gs=SimpleNamespace(game=t.game,
                                    staging_dir=lambda: t.staging))
            MainWindow._retarget_change_version_to_selection(window)
        assert retargeted == [ACD, "Neon Houseboat"], retargeted


if __name__ == "__main__":
    test_read_catalog()
    print("✓ reads ContentCatalog.txt with a BOM")
    test_read_catalog_bad_input()
    print("✓ a missing or invalid catalog is empty")
    test_names()
    print("✓ mod names and display versions")
    test_new_creation_from_overwrite()
    print("✓ a new Creation in Overwrite becomes a mod")
    test_existing_disabled_mod_identical_copy()
    print("✓ an existing disabled mod keeps its state; identical copies are dropped")
    test_data_scan_skips_vanilla_and_deployed()
    print("✓ Data scan skips vanilla files and deployed links")
    test_name_collision()
    print("✓ a taken name gets a number")
    test_update_refreshes_version_and_xedit_flag()
    print("✓ an update refreshes the version and the xEdit flag")
    test_same_version_keeps_xedit_flag()
    print("✓ the same version leaves meta.ini alone")
    test_update_moves_removed_files_to_backup()
    print("✓ an update moves dropped files to the backup folder")
    test_update_cleanup_skips_mod_with_two_creations()
    print("✓ the cleanup skips a mod holding two Creations")
    test_first_sighting_records_version()
    print("✓ the first sighting records the version and category")
    test_creations_changed()
    print("✓ catalog changes are noticed, timestamp rewrites are not")
    test_plugin_creations()
    print("✓ Creation plugins and their tooltips")
    test_skyrim_vanilla_archives_stay()
    print("✓ vanilla .bsa archives stay in Data")
    test_tooltips_only_for_creation_mods()
    print("✓ tooltips only for plugins a Creation mod holds")
    test_stray_file_takes_the_name()
    print("✓ a stray staging file takes the name")
    test_one_failing_creation_keeps_the_rest()
    print("✓ one failing Creation doesn't stop the rest")
    test_in_game_plugin_state_is_kept()
    print("✓ a plugin turned off in-game stays off")
    test_mod_missing_from_profile_is_logged()
    print("✓ a Creation mod missing from the profile is logged")
    test_restore_drops_identical_rewrite()
    print("✓ Restore drops an identical rewrite without an xEdit mark")
    test_restore_still_tags_real_edit()
    print("✓ Restore still marks a real edit")
    test_restore_compares_only_plugins()
    print("✓ Restore compares only plugin contents")
    test_failed_move_keeps_the_mod_file()
    print("✓ a failed move keeps the mod's file")
    test_percent_in_kept_xedit_names_survives()
    print("✓ % in kept xEdit names survives an update")
    test_tooltip_cache_sees_changes_inside_mods()
    print("✓ the tooltip cache sees changes inside mods")
    test_overwrite_plugin_into_disabled_mod_is_unlisted()
    print("✓ an Overwrite plugin moved into a disabled mod is unlisted")
    test_creation_url()
    print("✓ Creation mods link to their Creations page")
    test_identical_overwrite_plugin_into_disabled_mod_is_unlisted()
    print("✓ an identical Overwrite plugin moved into a disabled mod is unlisted")
    test_plugin_of_another_enabled_mod_stays_listed()
    print("✓ a plugin another enabled mod ships stays listed")
    test_tooltip_cache_follows_symlinked_mods()
    print("✓ the tooltip cache follows symlinked mod folders")
    test_tooltips_skip_the_scan_without_a_catalog()
    print("✓ tooltips skip the staging scan without a catalog")
    test_failed_case_rename_is_still_recorded()
    print("✓ a failed case rename is still recorded")
    test_stale_staged_file_is_removed()
    print("✓ a stale staged file is removed")
    test_tooltip_refresh_during_import_keeps_the_new_file()
    print("✓ a tooltip refresh during an import keeps the new file")
    test_creation_url_reads_only_general()
    print("✓ Creation links read only [General], last entry wins")
    test_failed_case_rename_is_logged()
    print("✓ a failed case rename is logged")
    test_empty_versions_are_filled()
    print("✓ empty versions are filled in, set ones are kept")
    test_creation_url_rejects_odd_ids()
    print("✓ Creation links reject ids that aren't UUIDs")
    test_creation_url_reads_upstream_format()
    print("✓ Creation links read meta.ini as upstream writes it")
    test_pipeline_skips_the_import_while_deployed()
    print("✓ the pipeline skips the import while the game is deployed")
    test_is_creation()
    print("✓ Creation mods are told apart from Nexus and manual mods")
    test_change_version_shows_a_creation()
    print("✓ Change Version shows that a mod is a Creation")
    test_change_version_leaves_other_mods_to_upstream()
    print("✓ Change Version leaves other mods without a Nexus ID to upstream")
    test_change_version_follows_selection_to_a_creation()
    print("✓ Change Version follows the selection to a Creation only")
