# Syncing with upstream

Caelumite follows
[ChrisDKN/Amethyst-Mod-Manager](https://github.com/ChrisDKN/Amethyst-Mod-Manager)
closely. Game handlers, deployment, LOOT, Nexus and the UI come from upstream
unchanged. Caelumite only adds a platform layer, so most upstream merges apply
cleanly.

## Merging

```bash
scripts/sync-upstream.sh
```

The script fetches the `upstream` remote and merges `upstream/main` with a
merge commit. Never rebase or squash: git needs upstream's history to keep
later merges small. After the merge it:

- deletes the paths in `scripts/removed-upstream-paths.txt` again (Linux
  packaging, CI, Nix, meson), which also resolves conflicts where upstream
  edited one of them;
- keeps Caelumite's copy of files marked `merge=ours` in `.gitattributes`
  (the logo, the README).

Any other conflict is left for you to resolve; the merge isn't committed
until none remain. After merging, start the app and check that a game
deploys and launches.

## Where Caelumite differs from upstream

**New code** (never conflicts):

- `src/Utils/macos/` — CrossOver bottle discovery and path translation
  (`crossover.py`), the bottle runner for Play, Run EXE and tools
  (`launch.py`), the rename translator and identity (`branding.py`, `app.py`),
  hiding Linux-only UI (`ui_prune.py`), and the `caffeinate` and `ps`
  backends (`sleep.py`, `instances.py`).
- `src/LOOT/build_libloot_macos.sh`, `native/amethyst_filegraph/.cargo/`,
  `scripts/`, `caelumite`, `docs/`.

**Hooks in upstream files.** Each is a small `if sys.platform == "darwin":`
branch that calls into `Utils.macos` and is tagged with a `# Caelumite:`
comment. To list them:

```bash
grep -rn "Caelumite:" src --include="*.py" --exclude-dir=macos
```

| File | Hook |
|---|---|
| `Utils/launchers/steam.py` | Windows Steam in bottles as Steam roots; Windows library paths; bottle as prefix; `proton_run_command` → bottle |
| `Utils/executables/launch.py` | Play, Run EXE, tool prefixes and the game prefix use the bottle; no `wineserver -k` |
| `Utils/wine/proton.py` | `resolve_proton_env` → bottle (winecfg, regedit, registry repair) |
| `Utils/deployment/pipeline.py` | `steamuser` link before deploying |
| `Utils/config_paths.py` | config dir and default staging root |
| `Games/base_game.py` | Hardlink is the default deploy method (games that ask for Symlink keep it) |
| `Utils/environment/xdg.py` | `open` instead of `xdg-open`; `~/Downloads` |
| `Utils/processes/sleep.py` | `caffeinate` |
| `Utils/processes/instances.py` | `ps`/`kill` instead of `/proc` |
| `gui_qt/i18n.py` | installs the rename translator |
| `gui_qt/app.py` | app name and UI filter |
| `native/amethyst_filegraph/build_extension.py` | `.dylib` output on macOS |

**Replaced files:** `src/icons/Logo.png` (from `scripts/make_icon.py`) and
`README.md`.

## Editing upstream files

Some upstream files mix CRLF and LF line endings (`Utils/launchers/steam.py`).
Editors that normalize line endings turn a three-line hook into a
whole-file diff, and every later merge then conflicts. After editing a
shared file, check that `git diff --stat` only counts the lines you meant to
change.
