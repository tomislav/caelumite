"""Self-checks for linking a profile's plugins.txt into a tool prefix.

Run from src/: python -m Utils.executables._plugins_txt_selftest

``link_plugins_txt`` (Utils/executables/launch.py) calls every game's
``_symlink_plugins_txt(profile, log_fn, prefix_root=...)``. A handler that
overrides it without ``prefix_root`` makes every tool-prefix link fail
("got an unexpected keyword argument 'prefix_root'"), so the first check
scans all handler sources for such overrides; the second runs Starfield's
end to end in temporary folders.
"""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]


def test_every_override_accepts_prefix_root() -> None:
    missing = []
    for path in sorted((SRC / "Games").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name == "_symlink_plugins_txt"):
                names = [a.arg for a in node.args.args + node.args.kwonlyargs]
                if "prefix_root" not in names and node.args.kwarg is None:
                    missing.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not missing, "overrides without prefix_root: " + ", ".join(missing)


def test_starfield_links_into_tool_prefix() -> None:
    from Games.Bethesda.starfield import Starfield
    from Utils.executables.launch import link_plugins_txt

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        game = Starfield()
        game._prefix_path = tmp / "game-prefix"
        game._game_path = tmp / "game"
        (game._game_path / "Data").mkdir(parents=True)
        game.get_profile_root = lambda: tmp / "staging"
        game.get_last_deployed_profile = lambda: "default"
        profile = tmp / "staging" / "profiles" / "default"
        profile.mkdir(parents=True)
        (profile / "plugins.txt").write_text(
            "*Starfield.esm\n*MyMod.esm\nBlueprintShips-Starfield.esm\n",
            encoding="utf-8")

        logs: list[str] = []
        link_plugins_txt(game, tmp / "tool-prefix", logs.append)
        assert not any("failed" in line for line in logs), logs
        linked = (tmp / "tool-prefix" / game._APPDATA_SUBPATH
                  / game.plugins_txt_filename)
        assert linked.read_text(encoding="utf-8").split() == [
            "*Starfield.esm", "*MyMod.esm"], linked.read_text(encoding="utf-8")
        assert not game._prefix_path.exists(), "the game prefix was written"

        # Deploy and restore still use the game's own prefix.
        game._symlink_plugins_txt("default", logs.append)
        assert (game._prefix_path / game._APPDATA_SUBPATH
                / game.plugins_txt_filename).is_file()


if __name__ == "__main__":
    test_every_override_accepts_prefix_root()
    print("✓ every _symlink_plugins_txt override accepts prefix_root")
    test_starfield_links_into_tool_prefix()
    print("✓ Starfield links plugins.txt into a tool prefix")
