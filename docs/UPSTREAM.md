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

The script fetches the `upstream` remote, without its tags (upstream's
version tags would clash with Caelumite's), and merges `upstream/main` with a
merge commit. Never rebase or squash: git needs upstream's history to keep
later merges small. After the merge it:

- deletes the paths in `scripts/removed-upstream-paths.txt` again (Linux
  packaging, CI, Nix, meson), which also resolves conflicts where upstream
  edited one of them;
- keeps Caelumite's copy of files marked `merge=ours` in `.gitattributes`
  (the logo, the README, the changelog);
- says when upstream's version changed: set `AMETHYST_VERSION` in
  `src/Utils/macos/app.py` to it, since manager plugins are checked against
  that version, and add it to `AMETHYST_RELEASES` with the Caelumite release
  that will ship it, so plugin requirements show as Caelumite versions.

Any other conflict is left for you to resolve; the merge isn't committed
until none remain. After merging, start the app and check that a game
deploys and launches.

### The Resources branch

Caelumite downloads game handlers, wizard plugins, translations, curated
profiles and the Synthesis NuGet config at runtime from its own `Resources`
branch, a copy of upstream's. Merge upstream's into it from a worktree:

```bash
git worktree add ../caelumite-resources Resources
```

```bash
cd ../caelumite-resources && ../Caelumite/scripts/sync-upstream.sh
```

On `Resources` the script merges `upstream/Resources`, removes the paths in
`scripts/removed-resources-paths.txt` (upstream's GitHub Actions workflows,
its Crowdin config, and the manager plugins that don't run on macOS), and
stops before committing if any `.py` file changed. Caelumite runs plugin code, so review it first, then
`git commit --no-edit` and push.

## Where Caelumite differs from upstream

**New code** (never conflicts):

- `src/Utils/macos/` — CrossOver bottle discovery and path translation
  (`crossover.py`), the bottle runner for Play, Run EXE and tools
  (`launch.py`), the rename translator and identity (`branding.py`, `app.py`),
  hiding Linux-only UI (`ui_prune.py`), the `caffeinate` and `ps`
  backends (`sleep.py`, `instances.py`), the import of in-game Bethesda
  Creations into mods (`creations.py`), their Change Version notice
  (`change_version.py`), the missing-master check before a LOOT sort
  (`loot.py`), the built-in plugin and game-handler repositories
  (`resources.py`), and plugin versions shown as Caelumite versions
  (`plugins.py`).
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
| `Utils/deployment/pipeline.py` | `steamuser` and `pfx` links before deploying (`prepare_bottle`); no script-extender launcher swap (CrossOver can't run a renamed game exe); instead a detected loader is the first, default play-bar entry and starts the bottle's Steam first, and the game entry starts the game without it (`Utils/macos/launch.py`, `gui_qt/app.py` play bar); a changed `ContentCatalog.txt` forces the full deploy path, and after the restore in-game Creations become mods (`Utils/macos/creations.py`) |
| `Utils/deployment/standard.py` | Restore discards a deployed file the game rewrote with identical bytes (an in-game Creation re-download) instead of moving it back into its mod and flagging it as edited in xEdit (`Utils/macos/creations.py`) |
| `Utils/config_paths.py` | config dir and default staging root |
| `Games/base_game.py` | Hardlink is the default deploy method (games that ask for Symlink keep it) |
| `Utils/environment/xdg.py` | `open` instead of `xdg-open`; `~/Downloads` |
| `Utils/processes/sleep.py` | `caffeinate` |
| `Utils/processes/instances.py` | `ps`/`kill` instead of `/proc` |
| `Utils/processes/game.py` | running-game tracking via `sysctl(KERN_PROCARGS2)` instead of `/proc/*/environ` |
| `Utils/processes/leases.py` | launch leases identify the boot and processes via sysctl instead of `/proc` (`Utils/macos/processes.py`) |
| `gui_qt/i18n.py` | installs the rename translator |
| `Utils/ui/portal.py`, `gui_qt/dialogs/file_pickers.py` | file pickers skip the XDG portal, zenity and kdialog and use the native macOS open and save panels |
| `gui_qt/games/configure.py` | no dependency installers run in a game's CrossOver bottle |
| `Utils/ui/shortcut_bindings.py` | Install Mod defaults to Cmd+I so Cmd+M can minimize |
| `Nexus/nxm_handler.py` | `NxmHandler` registration via LaunchServices (`Utils/macos/urls.py`); the single-instance socket is in the per-user temp folder, not XDG/Flatpak/`~/.local/share` paths |
| `Thunderstore/ror2mm_handler.py` | `ror2mm://` and `modl://` registration via LaunchServices, only when no other app handles them |
| `Nexus/nexus_api.py` | requests identify as Caelumite; Caelumite's own keyring entry; no weak key-file fallback - a key the Keychain can't store is kept for the session ([NEXUS.md](NEXUS.md)) |
| `Nexus/nexus_oauth.py` | Caelumite's own OAuth client, empty (OAuth off) until Nexus registers it; the keyring probe checks for the macOS Keychain instead of DBus |
| `Nexus/session.py` | until Caelumite is registered: the saved Nexus login loads only Caelumite's testing personal key, never Amethyst's OAuth login (the app and headless mode both load it here); headless mode's login status counts that key and its OAuth login can't start (`Utils/macos/nexus.py`) |
| `Utils/mods/install.py` | the install worker's Nexus lookup ignores saved upstream OAuth logins |
| `gui_qt/nexus/mod_detail.py` | image requests identify as Caelumite |
| `wizards_qt/__init__.py` | wizards in `Utils/macos/wizard.py` `MACOS_UNSUPPORTED` join `EXCLUDED` (Linux-native tools, Proton-only texture conversion, Synthesis, ReShade) |
| `Utils/wine/protontricks.py` | `build_proton_env_for_game` → bottle (dtkit-patch and other prefix installers) |
| `Utils/ui/config.py` | the Wabbajack top-bar button is always hidden; the Endorse button is off; the mod list defaults to MO2's order |
| `gui_qt/settings/view.py` | no "Hide Ko-Fi button" setting (a hook appended at the end skips that checkbox) |
| `Utils/bethesda/xedit.py` | the xEdit Windows XP flag goes through `reg import` (`Utils/macos/registry.py`) |
| `Utils/github/cache.py`, `Utils/sharing/paste.py`, `Thunderstore/thunderstore_download.py`, `Utils/downloads/modl.py`, `LOOT/loot_sorter.py`, `Games/Baldur's Gate 3/modio_api.py`, `Games/Baldur's Gate 3/bg3le_runtime.py`, `amethyst_backend/tool_acquisition.py`, `amethyst_backend/modio_versions.py` | User-Agent `Caelumite/<version>` |
| `Utils/loverslab/credentials.py`, `Games/Baldur's Gate 3/modio_key.py` | Keychain service `Caelumite` |
| `wizards_qt/proton_step.py` | the wizard "Choose Proton Version" step shows the game's bottle instead (`Utils/macos/wizard.py`) |
| `gui_qt/modlist/menu.py` | "Open on Creations" in a Creation mod's right-click menu (one or several mods) opens its creations.bethesda.net page (`Utils/macos/creations.py`) |
| `gui_qt/plugins/model.py` | a Creation plugin's name has a tooltip with the Creation's title and version (`Utils/macos/creations.py`) |
| `gui_qt/nexus/change_version.py` | a Creation shows a notice instead of asking Nexus for its files; Ignore Update and the legend are off meanwhile (`Utils/macos/change_version.py`) |
| `gui_qt/app.py` | app name and UI filter; menu bar; the Github button opens Caelumite's repository; the Nexus login button goes through `Utils/macos/nexus.py` until Caelumite is registered; no Ko-Fi button; after a Play session, a Deploy imports Creations changed in-game, and a startup notice appears when they changed while Caelumite wasn't running; the Change Version tab follows the selection to a Creation and says it's a Creation (`Utils/macos/creations.py`, `Utils/macos/change_version.py`) |
| `Utils/github/sync.py`, `Utils/profiles/curated.py`, `Utils/bethesda/synthesis.py` | resources come from Caelumite's `Resources` branch |
| `amethyst_plugins/sources.py`, `Utils/github/handler_sources.py` | the built-in manager-plugin catalogue and game-handler repository are Caelumite's `Resources` branch; upstream's is an ordinary repository (`Utils/macos/resources.py`) |
| `amethyst_plugins/catalog.py`, `gui_qt/settings/plugin_store.py` | a plugin's minimum version (an Amethyst version) is compared with the Amethyst version Caelumite is based on (`AMETHYST_VERSION` in `Utils/macos/app.py`), and the plugin browser and the too-new message show it as a Caelumite version (`AMETHYST_RELEASES`, `Utils/macos/plugins.py`) |
| `amethyst_plugins/protocols.py` | URL schemes that plugins declare aren't registered (LaunchServices only sends the app bundle's own schemes); each is logged instead |
| `amethyst_backend/service.py` | headless mode's handshake names Caelumite |
| `Utils/bethesda/xedit_run.py` | xEdit, QuickAutoClean, the LOD tools and Wrye Bash may run while the bottle's Steam client, Wine's services and CrossOver's own programs do; a game or any other program in the bottle (also one CrossOver marks only with `CX_BOTTLE=<name>`) still blocks them, and the message names it (`Utils/macos/processes.py`) |
| `Utils/wine/repair.py` | registry repairs and installers keep upstream's check (any process in the bottle, also those CrossOver marks only with `CX_BOTTLE=<name>`); when the bottle is busy, the message names the programs and says its Steam counts too and how to quit it |
| `Utils/operations.py`, `Utils/bethesda/lod_run.py` | operation locks, launch leases and LOD work folders are in `~/Library/Application Support/Caelumite`, not `~/.local/share` |
| `Utils/github/wiki.py`, `gui_qt/games/onboarding.py` | the in-app wiki and onboarding link use Caelumite's wiki |
| `Nexus/nexus_requirements.py` | the requirement filter list comes from Caelumite's `main` |
| `Utils/github/app_updates.py` | release URLs point at Caelumite |
| `gui_qt/app.py` (LOOT sort, overlap check) | for games whose LOOT loads masters first (Starfield, Morrowind, OpenMW), a plugin with a missing master stops Sort, Refresh and the record-overlap check with a notice naming the plugin and the master, instead of LOOT's "has not been loaded" (`Utils/macos/loot.py`) |
| `gui_qt/app.py` (app update check), `gui_qt/support/update.py` | updates come from Caelumite's GitHub releases: the newest one with a DMG, which the banner's "Download update" opens; the check repeats daily while the app is open, and the menu bar's "Check for Updates…" runs it right away (`Utils/macos/updates.py`, `Utils/macos/menubar.py`) |
| `gui_qt/app.py` (`_install_paths`, `_on_nxm_download_done`) | installing the file the update check found for a mod (`latestfileid`, when it isn't the installed file), from Change Version or a Mod Manager Download on Nexus, replaces that mod under its own name like Quick Update, instead of installing beside it under the file's name; Change Version also does this without a check when the picked file has the installed file's Nexus category, or either is an old version; other files install as before (`Utils/macos/mod_updates.py`) |
| `gui_qt/app.py` (`_open_change_version_tab`) | when Change Version is reopened for another mod, deleting the replaced tab no longer clears the window's reference to the new one, so a Mod Manager Download for it is recognised instead of installing as a new mod while the tab keeps waiting (`Utils/macos/change_version.py`) |
| `gui_qt/app.py` (`_on_wizard_finish_done`, `_finish_one_install`) | a Rollback, Reinstall or Quick Update of the mod the Change Version tab shows refreshes its "installed" highlight, not only installs the tab started; a tab waiting for its own download is left alone (`Utils/macos/change_version.py`) |
| `Nexus/nexus_update_checker.py` (Path A) | for a mod without a Nexus file ID, Nexus's per-account "update available" flag is ignored when the page's version is older than the installed one, so comparing them decides and an optional file at 2.0.3 isn't flagged for the page's 1.3; an unchanged page version still trusts the flag (`Utils/macos/mod_updates.py`) |
| `gui_qt/app.py` (`_on_updates_ready`), `gui_qt/modlist/menu.py` (`_update_menu_items`) | after Check Updates, the prompt for Nexus updates adds Show updates, which adds `!update` to the mod list's search; without Nexus Premium the prompt offers only that, and the right-click menu leaves out Quick Update, since it downloads directly (`Utils/macos/mod_updates.py`) |
| `native/amethyst_filegraph/build_extension.py` | `.dylib` output on macOS |
| `Utils/diagnostics/system.py` | System Information shows the macOS version, run mode and installed CrossOver builds instead of the Linux distribution, libc, Flatpak/AppImage and desktop-session rows (`Utils/macos/diagnostics.py`) |

**Replaced files:** `src/icons/Logo.png` (from `scripts/make_icon.py`),
`README.md`, `Changelog.txt`, `src/version.py` and `AGENTS.md`.

## Editing upstream files

Some upstream files mix CRLF and LF line endings (`Utils/launchers/steam.py`).
Editors that normalize line endings turn a three-line hook into a
whole-file diff, and every later merge then conflicts. After editing a
shared file, check that `git diff --stat` only counts the lines you meant to
change.
