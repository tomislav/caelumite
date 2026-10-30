# Headless mode and plugins on macOS

[headless.md](headless.md) and [manager-plugins.md](manager-plugins.md) are
upstream's references, kept unchanged so they merge cleanly. They apply to
Caelumite except for the commands and paths below.

## Starting headless mode

There's no `amethyst-mod-manager-cli`, AppImage or Flatpak. Run `cli.py`
with Caelumite's own Python.

From an installed app:

```bash
/Applications/Caelumite.app/Contents/MacOS/caelumite-python -s /Applications/Caelumite.app/Contents/Resources/app/cli.py headless --stdio
```

From a checkout (after `scripts/setup-macos.sh`):

```bash
cd src && ../.venv/bin/python cli.py headless --stdio
```

The other `cli.py` commands work the same way, for example
`cli.py plugin-validate <plugin folder>`. Started from Terminal, the app's
bundled tools (`7zz`) aren't on `PATH`; installing archives needs
`/Applications/Caelumite.app/Contents/Resources/bin` added to it.

## Paths

| Upstream | Caelumite |
|---|---|
| `~/.config/AmethystModManager/` | `~/Library/Application Support/Caelumite/` |
| `~/.config/AmethystModManager/Plugins/` | `~/Library/Application Support/Caelumite/Plugins/` |
| `~/Games/Amethyst/<game>` | `~/Games/Caelumite/<game>` |
| a game's Proton prefix | the game's CrossOver bottle |

## What differs

- **Built-in repositories.** The plugin catalogue (`Plugins/v2`) and game
  handlers (`Custom Handlers`) come from Caelumite's `Resources` branch, not
  upstream's (`Utils/macos/resources.py`). It carries only the plugins that
  run on macOS; `scripts/removed-resources-paths.txt` lists the others.
  Upstream's repository can be added as an ordinary one.
- **Nexus Mods.** Login is off until Nexus registers Caelumite, in the app
  and in headless mode ([NEXUS.md](NEXUS.md)). Plugins that use the Nexus API
  only get it with the testing personal key.
- **Launching and tools.** Play, Run EXE and tools always run in the game's
  CrossOver bottle. Launcher plugins and Proton runner settings don't apply.
