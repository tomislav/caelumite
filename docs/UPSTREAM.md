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
| `Utils/deployment/wine_dll.py` | DLL overrides go through `reg import` in the bottle (`Utils/macos/registry.py`), not a direct `user.reg` edit a running Wine would overwrite |
| `Utils/deployment/pipeline.py` | `steamuser` link before deploying; no script-extender launcher swap (CrossOver can't run a renamed game exe) |
| `Utils/config_paths.py` | config dir and default staging root |
| `Games/base_game.py` | Hardlink is the default deploy method (games that ask for Symlink keep it) |
| `Utils/environment/xdg.py` | `open` instead of `xdg-open`; `~/Downloads` |
| `Utils/processes/sleep.py` | `caffeinate` |
| `Utils/processes/instances.py` | `ps`/`kill` instead of `/proc` |
| `Utils/processes/game.py` | running-game tracking via `sysctl(KERN_PROCARGS2)` instead of `/proc/*/environ` |
| `gui_qt/i18n.py` | installs the rename translator |
| `gui_qt/shortcuts.py` | Install Mod defaults to Cmd+I so Cmd+M can minimize |
| `Nexus/nxm_handler.py` | `NxmHandler` registration via LaunchServices (`Utils/macos/urls.py`); the single-instance socket is in the per-user temp folder, not XDG/Flatpak/`~/.local/share` paths |
| `Thunderstore/ror2mm_handler.py` | `ror2mm://` and `modl://` registration via LaunchServices, only when no other app handles them |
| `Nexus/nexus_api.py` | requests identify as Caelumite; Caelumite's own keyring entry ([NEXUS.md](NEXUS.md)) |
| `Nexus/nexus_oauth.py` | Caelumite's own OAuth client, empty (OAuth off) until Nexus registers it; the keyring probe checks for the macOS Keychain instead of DBus |
| `Utils/mods/install.py` | the install worker's Nexus lookup ignores saved upstream OAuth logins |
| `gui_qt/nexus_mod_detail_view.py` | image requests identify as Caelumite |
| `wizards_qt/__init__.py` | wizards in `Utils/macos/wizard.py` `MACOS_UNSUPPORTED` join `EXCLUDED` (Linux-native tools, Proton-only texture conversion, Synthesis, ReShade) |
| `Utils/wine/protontricks.py` | `build_proton_env_for_game` → bottle (dtkit-patch and other prefix installers) |
| `Utils/ui/config.py` | the Wabbajack top-bar button is always hidden; the Endorse button and update check are off |
| `gui_qt/settings_view.py` | no "Hide Ko-Fi button" setting |
| `wizards_qt/proton_step.py` | the wizard "Choose Proton Version" step shows the game's bottle instead (`Utils/macos/wizard.py`) |
| `gui_qt/app.py` | app name and UI filter; menu bar; the Github button opens Caelumite's repository; Nexus login goes through `Utils/macos/nexus.py` until Caelumite is registered; no Ko-Fi button |
| `native/amethyst_filegraph/build_extension.py` | `.dylib` output on macOS |

**Replaced files:** `src/icons/Logo.png` (from `scripts/make_icon.py`) and
`README.md`.

## Editing upstream files

Some upstream files mix CRLF and LF line endings (`Utils/launchers/steam.py`).
Editors that normalize line endings turn a three-line hook into a
whole-file diff, and every later merge then conflicts. After editing a
shared file, check that `git diff --stat` only counts the lines you meant to
change.
