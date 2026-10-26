# Caelumite

A macOS mod manager for Windows games running in CrossOver, with an MO2-style
interface: profiles, FOMOD installers, LOOT sorting, Nexus downloads and
hardlink deployment, plus wizards for tools like xEdit, BodySlide and
DynDOLOD.

Caelumite is a macOS-only fork of
[Amethyst Mod Manager](https://github.com/ChrisDKN/Amethyst-Mod-Manager) by
ChrisDKN. Nearly all of the mod-management code is Amethyst's. Caelumite adds
the macOS platform layer and keeps merging upstream releases. Please send
game-support and mod-management bug reports and feature ideas upstream, and
support the original project.

## How it works on macOS

- **Games live in CrossOver bottles.** Caelumite finds every CrossOver bottle
  and the Windows Steam installed inside it, so Steam games are detected
  automatically. The game's bottle is its prefix.
- **Mods are hardlinked into the game folder.** The game reads plain files at
  full speed; nothing is injected at runtime. Keep mod staging
  (`~/Games/Caelumite` by default) on the same disk as the bottle, or
  deployment falls back to slower symlinks or copies.
- **Play and tools run in the bottle.** Play hands off to the bottle's
  Steam (`steam.exe -applaunch`), or runs the exe directly with launch mode
  *None*. Wizard tools and Run EXE use the same bottle.
- **One link is added to each game bottle:** `drive_c/users/steamuser` →
  the bottle's real user (`crossover`). Amethyst's game handlers use Proton's
  user name for plugins.txt, INIs and saves; the link makes those paths land
  in the right place. Wine ignores the extra folder.

Config lives in `~/Library/Application Support/Caelumite`.

## Requirements

- macOS on Apple silicon or Intel
- [CrossOver](https://www.codeweavers.com/crossover) with your game installed
  in a bottle
- Homebrew Python 3.12–3.14, Rust (`brew install python@3.14 rust`) and the
  Xcode command line tools (`xcode-select --install`)

## Running from source

```bash
git clone https://github.com/tomislav/caelumite
```

```bash
scripts/setup-macos.sh
```

```bash
./caelumite
```

The setup script creates `.venv`, installs the Python dependencies and builds
the two native extensions (the deployment catalog and libloot) into `src/`.

To get the Caelumite name and icon in the menu bar, Dock and app switcher,
and to open Nexus "Mod Manager Download" links, build the app bundle:

```bash
scripts/build-app.sh
```

`build/Caelumite.app` runs this checkout, so code changes need no rebuild;
rebuild after `scripts/setup-macos.sh` or a Homebrew Python upgrade. You can
drag it into `/Applications`. `./caelumite` uses it when it exists. On start,
Caelumite makes itself the default `nxm://` handler.

## Importing from Mod Organizer 2

Caelumite uses MO2's mod-folder and load-order formats, so an MO2 instance
(for example one in a CrossOver bottle) imports as-is:

```bash
.venv/bin/python scripts/import_mo2.py "<MO2 instance folder>" ~/Games/Caelumite/<Game>
```

Mods and the overwrite folder are copied as APFS clones (instant, almost no
extra disk space, independent of MO2), and the MO2 profile's load order
replaces the Caelumite profile's after a backup. MO2 itself isn't changed.
Close Caelumite first.

## Not supported on macOS (yet)

- Tool prefixes separate from the game's bottle: every tool runs in the game's
  bottle.
- Windows component installers (VC++, .NET, XAudio): install them with
  CrossOver's own "Install Software" instead.
- Steam-style launch options (`%command%`), the Linux VFS deploy method,
  Wayland, LSFG and MangoHud.
- Wabbajack (texture conversion and MPI installers need Proton), and the
  wizards that run Linux-native tools or Proton-only texture conversion:
  ReShade, BodySlide/Outfit Studio (Linux builds - the Windows BodySlide
  wizard still works once BodySlide is installed as a mod), TTW, BSA
  Decompressor, ESM Fixes, me3, Regulation Merge, YeetPatch, VRAMr,
  BENDr, ParallaxR and Synthesis. See `src/Utils/macos/wizard.py`.

## Keeping up with upstream

See [docs/UPSTREAM.md](docs/UPSTREAM.md).

## License

GPL-3.0, like upstream. See [LICENSE](LICENSE).
