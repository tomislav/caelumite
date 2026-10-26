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
scripts/setup-macos.sh
```

```bash
./caelumite
```

The setup script creates `.venv`, installs the Python dependencies and builds
the two native extensions (the deployment catalog and libloot) into `src/`.

## Not supported on macOS (yet)

- Tool prefixes separate from the game's bottle: every tool runs in the game's
  bottle.
- Windows component installers (VC++, .NET, XAudio): install them with
  CrossOver's own "Install Software" instead.
- Steam-style launch options (`%command%`), the Linux VFS deploy method,
  Wayland, LSFG and MangoHud.
- Opening `nxm://` links from the Nexus website needs an app bundle, which
  is not built yet.

## Keeping up with upstream

See [docs/UPSTREAM.md](docs/UPSTREAM.md).

## License

GPL-3.0, like upstream. See [LICENSE](LICENSE).
