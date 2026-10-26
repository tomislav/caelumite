# Caelumite

A macOS-only fork of [Amethyst Mod Manager](https://github.com/ChrisDKN/Amethyst-Mod-Manager)
(the `upstream` remote) that manages Windows games running in CrossOver
bottles. It keeps merging upstream releases, so every change has to stay
mergeable. Python 3.14 and PySide6, Apple silicon, macOS 14 or later.

- Repository: `tomislav/caelumite` (`origin`). Issues are reported here, not
  upstream. Never push to or open PRs against upstream.
- `gh` resolves to upstream when no repo is given: always pass
  `--repo tomislav/caelumite`.
- The user's shell is fish: commands for them must be fish-compatible
  (`set -x FOO bar`).

## Fork rules

- New macOS code goes in `src/Utils/macos/`. Upstream files only get small
  `if sys.platform == "darwin":` hooks tagged `# Caelumite:` that call into
  `Utils.macos`. Add each new hook to the table in
  [docs/UPSTREAM.md](docs/UPSTREAM.md).
- Don't edit upstream UI strings to rename or reword them:
  `Utils/macos/branding.py` translates them at runtime, and
  `Utils/macos/ui_prune.py` hides Linux-only UI.
- Keep each file's line endings. Some upstream files are CRLF or mixed; after
  editing one, `git diff --stat` must count only the lines you changed.
- `README.md`, `Changelog.txt`, `src/version.py`, `src/icons/Logo.png` and
  this file are `merge=ours` in `.gitattributes`.
- Merge upstream with `scripts/sync-upstream.sh` (merge commits, never rebase
  or squash). It also maintains the `Resources` branch, which the app
  downloads game handlers, wizard plugins and translations from. Review
  changed `.py` files there before committing: the app runs that code. See
  [docs/UPSTREAM.md](docs/UPSTREAM.md).

## Running and testing

```bash
scripts/setup-macos.sh   # .venv, dependencies, native extensions
scripts/build-app.sh     # build/Caelumite.app, runs this checkout
./caelumite
```

- Config: `~/Library/Application Support/Caelumite` (`amethyst.ini`). One log
  per session in its `logs/`, plus `logs/nxm.log` for link handling.
- Mod staging: `~/Games/Caelumite/<Game>`.
- Self-checks are plain modules run from `src/`, e.g.
  `../.venv/bin/python -m Utils.executables._plugins_txt_selftest`. Find
  them with `find src -name "*selftest*.py"`.
- The user's real games live in `~/Games/Caelumite` and their CrossOver
  bottles. While Caelumite may be running, only read there, and copy sqlite
  files elsewhere before querying them. Ask before changing anything there.

## macOS behavior worth knowing

- A game's CrossOver bottle is its prefix. Commands run as
  `wine --bottle <name> --no-convert`. `crossover.prepare_bottle` adds
  `drive_c/users/steamuser` → the bottle's user and `pfx` → the bottle, so
  upstream's Proton paths land in the bottle.
- Wine doesn't pass Windows-side environment variables to the macOS-side
  process, so games started through Steam are tracked by an exe marker
  (`CAELUMITE_EXE=`, `Utils/macos/processes.py`) matched against the Windows
  command line.
- Play hands off to the bottle's Steam (`steam.exe -applaunch`). Steam and
  the hand-off run outside the play session, or the session ends when the
  hand-off exits. A detected script extender is the default Play entry and
  starts Steam first (`Utils/macos/launch.py`).
- Credentials go in the Keychain (service `Caelumite`). There is no key-file
  fallback on macOS.

## Nexus Mods

Nexus's API policy requires honest identification and allows personal API
keys only for testing. Requests send `Application-Name: Caelumite`.
`NEXUS_CLIENT_ID` and `NEXUS_CLIENT_SECRET` in `src/Utils/macos/app.py` stay
empty until Nexus registers Caelumite, which keeps login off; never use
Amethyst's client. The personal-key switch is for developers only: document
it in [docs/NEXUS.md](docs/NEXUS.md), not in the README or the wiki.

## Releasing

1. Set the version in `src/version.py` and add a `- v<version>` section at
   the top of `Changelog.txt` (headings `### macOS`, `### Additions`,
   `### Changes`, `### Bug Fixes`). Commit and push `main`.
2. Build, sign and notarize (takes several minutes, run it in the
   background):
   ```bash
   .venv/bin/python scripts/build_release.py
   ```
   It needs the "Developer ID Application" certificate and the notarytool
   profile `caelumite`. Output: `build/release/Caelumite.app` and
   `Caelumite-<version>.dmg`. `--identity -` makes an ad-hoc build for
   local testing.
3. Check the DMG: `xcrun stapler validate` and `spctl -a -vv -t open
   --context context:primary-signature` on it.
4. Create the release `v<version>`, titled `Caelumite <version>`, with the
   DMG attached:
   ```bash
   gh release create v<version> build/release/Caelumite-<version>.dmg --repo tomislav/caelumite --title "Caelumite <version>" --notes-file <notes>
   ```
   The notes are the **Requires** and **Install** lines from the previous
   release, followed by the version's changelog section. The tag must point
   at the commit the DMG was built from.
5. The app's update check (`Utils/macos/updates.py`) offers the newest
   non-draft release that has a `.dmg` asset. Check that the previous version
   sees the new one.

Publishing, tagging and pushing are visible to everyone: ask the user first.

## Wiki

The wiki is a separate repository, `https://github.com/tomislav/caelumite.wiki.git`.
Help → Caelumite Wiki shows it in the app, using `_Sidebar.md` for
navigation. Page names keep upstream's numbering (`1.-FAQ`, `3.1-...`).
Keep pages short and user-facing.
