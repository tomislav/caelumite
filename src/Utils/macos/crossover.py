"""
Utils.macos.crossover
Read-only discovery of CrossOver apps and bottles, plus path translation
between a bottle's Windows drives and macOS paths.

A CrossOver bottle is a plain Wine prefix: ``drive_c/`` sits at the bottle
root and ``dosdevices/<letter>:`` symlinks map drive letters to host paths.
Caelumite treats the bottle itself as the game's prefix, the way upstream
treats a Proton ``pfx/`` directory, so the shared game handlers work on it
unchanged.

Nothing here imports Qt or the Steam launcher module, so it is safe to use
from ``Utils.launchers.steam`` at import time.
"""

from __future__ import annotations

import os
import plistlib
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

_HOME = Path.home()

# CrossOver's default bottle location. CX_BOTTLE_PATH overrides it the same
# way it does for CrossOver's own command-line tools.
_DEFAULT_BOTTLES_DIR = _HOME / "Library" / "Application Support" / "CrossOver" / "Bottles"

_APP_DIRS = (Path("/Applications"), _HOME / "Applications")
_CROSSOVER_BUNDLE_ID = "com.codeweavers.CrossOver"

# Windows user folder Proton uses. Upstream's game handlers hardcode it in
# their Documents/AppData paths; see ensure_steamuser_alias().
PROTON_USER = "steamuser"

_CONF_LINE = re.compile(r'^\s*"([^"]+)"\s*=\s*"([^"]*)"')


@dataclass(frozen=True)
class CrossOverApp:
    """One installed CrossOver app bundle (stable or Preview)."""

    path: Path        # /Applications/CrossOver.app
    version: str      # CFBundleVersion, e.g. "26.3.0.39832"

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def wine(self) -> Path:
        """CrossOver's bottle-aware ``wine`` wrapper (supports --bottle)."""
        return self.path / "Contents" / "SharedSupport" / "CrossOver" / "bin" / "wine"


@dataclass(frozen=True)
class Bottle:
    """One CrossOver bottle."""

    path: Path        # .../CrossOver/Bottles/<name>
    version: str      # "Version" from cxbottle.conf (the CrossOver build)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def drive_c(self) -> Path:
        return self.path / "drive_c"


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

def _read_bundle_version(app: Path) -> str | None:
    """CFBundleVersion of a CrossOver bundle, or None if it isn't CrossOver."""
    try:
        with open(app / "Contents" / "Info.plist", "rb") as fh:
            info = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    if info.get("CFBundleIdentifier") != _CROSSOVER_BUNDLE_ID:
        return None
    return str(info.get("CFBundleVersion") or info.get("CFBundleShortVersionString") or "")


def _version_key(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def list_crossover_apps() -> list[CrossOverApp]:
    """Installed CrossOver apps, newest build first."""
    apps: list[CrossOverApp] = []
    seen: set[Path] = set()
    for root in _APP_DIRS:
        try:
            entries = sorted(root.glob("CrossOver*.app"))
        except OSError:
            continue
        for app in entries:
            version = _read_bundle_version(app)
            if version is None:
                continue
            real = app.resolve()
            if real in seen:
                continue
            seen.add(real)
            app_obj = CrossOverApp(path=app, version=version)
            if app_obj.wine.is_file():
                apps.append(app_obj)
    apps.sort(key=lambda a: _version_key(a.version), reverse=True)
    return apps


# ---------------------------------------------------------------------------
# Bottles
# ---------------------------------------------------------------------------

def bottles_dir() -> Path:
    custom = os.environ.get("CX_BOTTLE_PATH")
    return Path(custom) if custom else _DEFAULT_BOTTLES_DIR


def _read_bottle_conf(bottle_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = (bottle_path / "cxbottle.conf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.strip("[]")
            continue
        if section != "Bottle":
            continue
        m = _CONF_LINE.match(line)
        if m:
            values[m.group(1)] = m.group(2)
    return values


def is_bottle(path: Path) -> bool:
    return (path / "cxbottle.conf").is_file() and (path / "drive_c").is_dir()


def list_bottles() -> list[Bottle]:
    """All CrossOver bottles, sorted by name."""
    root = bottles_dir()
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return []
    bottles = []
    for entry in entries:
        if entry.is_dir() and is_bottle(entry):
            conf = _read_bottle_conf(entry)
            bottles.append(Bottle(path=entry, version=conf.get("Version", "")))
    return bottles


def find_bottle(name: str) -> Bottle | None:
    target = (name or "").strip().casefold()
    for bottle in list_bottles():
        if bottle.name.casefold() == target:
            return bottle
    return None


def bottle_for_path(path: "Path | str | None") -> Bottle | None:
    """The bottle that contains *path* (or is *path*), if any."""
    if not path:
        return None
    try:
        p = Path(path).absolute()
    except (OSError, ValueError):
        return None
    root = bottles_dir()
    for candidate in (p, *p.parents):
        if candidate.parent == root and is_bottle(candidate):
            conf = _read_bottle_conf(candidate)
            return Bottle(path=candidate, version=conf.get("Version", ""))
    return None


def app_for_bottle(bottle: Bottle) -> CrossOverApp | None:
    """The CrossOver app that should run *bottle*.

    Prefers the app whose build matches the bottle's recorded version (the
    one that last updated it), then the newest app of the same major
    version, then the newest app installed. Running a bottle with a
    different major version makes CrossOver upgrade it, so matching matters.
    """
    apps = list_crossover_apps()
    if not apps:
        return None
    for app in apps:
        if bottle.version and app.version == bottle.version:
            return app
    major = bottle.version.split(".", 1)[0]
    for app in apps:
        if major and app.version.split(".", 1)[0] == major:
            return app
    return apps[0]


# ---------------------------------------------------------------------------
# Windows <-> host paths
# ---------------------------------------------------------------------------

def windows_to_host(bottle_path: Path, win_path: str) -> Path | None:
    """Translate a Windows path inside *bottle_path* to a host path.

    Handles ``C:\\Steam``, ``c:/steam`` and VDF-escaped ``C:\\\\Steam``.
    Drive letters resolve through the bottle's ``dosdevices`` symlinks, so
    ``Z:`` and extra drives map wherever CrossOver points them.
    """
    raw = win_path.replace("\\\\", "\\").replace("/", "\\")
    pure = PureWindowsPath(raw)
    drive = pure.drive.lower()
    if len(drive) != 2 or drive[1] != ":":
        return None
    link = bottle_path / "dosdevices" / drive
    try:
        target = Path(os.readlink(link))
    except OSError:
        if drive == "c:":
            target = Path("../drive_c")
        else:
            return None
    if not target.is_absolute():
        target = (bottle_path / "dosdevices" / target)
    rest = [part for part in pure.parts[1:] if part not in ("\\", "")]
    return _true_case(Path(os.path.normpath(target.joinpath(*rest))))


def _true_case(path: Path) -> Path:
    """*path* with each existing component spelled as it is on disk.

    Windows paths are case-insensitive (``c:/steam`` for ``C:\\Steam``), and
    so is a default APFS volume, but upstream dedups and compares paths as
    strings - so return the on-disk spelling.
    """
    parts = path.parts
    fixed = Path(parts[0])
    for i, part in enumerate(parts[1:], start=1):
        try:
            names = os.listdir(fixed)
        except OSError:
            return fixed.joinpath(*parts[i:])
        if part not in names:
            match = next((n for n in names if n.casefold() == part.casefold()), None)
            if match is None:
                return fixed.joinpath(*parts[i:])
            part = match
        fixed = fixed / part
    return fixed


def host_library_path(vdf_path: Path, raw: str) -> str:
    """A ``libraryfolders.vdf`` "path" value as a host path string.

    Libraries recorded by Windows Steam inside a bottle are Windows paths;
    anything else (or a path outside a bottle) is returned unchanged.
    """
    if not re.match(r"^[A-Za-z]:[\\/]", raw):
        return raw
    bottle = bottle_for_path(vdf_path)
    if bottle is None:
        return raw
    host = windows_to_host(bottle.path, raw)
    return str(host) if host is not None else raw


def _registry_steam_path(bottle: Bottle) -> str | None:
    """SteamPath that Windows Steam recorded in the bottle's user.reg."""
    try:
        text = (bottle.path / "user.reg").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    in_key = False
    for line in text.splitlines():
        if line.startswith("["):
            in_key = line.lower().startswith("[software\\\\valve\\\\steam]")
            continue
        if in_key and line.startswith('"SteamPath"='):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def bottle_steam_roots() -> list[Path]:
    """Windows Steam install roots inside every bottle.

    Uses the SteamPath Steam writes into the bottle's registry, then the
    usual install locations. These are appended to the Steam client roots
    upstream scans, so its library and app-manifest lookups find games
    installed through Steam in a bottle.
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path | None) -> None:
        if path is None or not (path / "steamapps").is_dir():
            return
        real = path.resolve()
        if real not in seen:
            seen.add(real)
            roots.append(path)

    for bottle in list_bottles():
        reg = _registry_steam_path(bottle)
        if reg:
            _add(windows_to_host(bottle.path, reg))
        for rel in ("Program Files (x86)/Steam", "Program Files/Steam", "Steam"):
            _add(bottle.drive_c / rel)
    return roots


def bottle_for_steam_app(steam_id: str) -> Bottle | None:
    """The bottle whose Windows Steam has *steam_id* installed."""
    if not steam_id:
        return None
    for root in bottle_steam_roots():
        steamapps = root / "steamapps"
        if (steamapps / f"appmanifest_{steam_id}.acf").is_file():
            return bottle_for_path(root)
        try:
            vdf = (steamapps / "libraryfolders.vdf").read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in re.findall(r'"path"\s+"([^"]+)"', vdf):
            library = Path(host_library_path(steamapps / "libraryfolders.vdf", raw))
            if (library / "steamapps" / f"appmanifest_{steam_id}.acf").is_file():
                return bottle_for_path(root)
    return None


def prefix_for_game(steam_id: str, game_path: "Path | str | None") -> Path | None:
    """The bottle to use as a game's prefix: the one holding the game's
    files, else the one whose Steam has the app installed."""
    bottle = bottle_for_path(game_path) or bottle_for_steam_app(steam_id)
    if bottle is None:
        return None
    ensure_steamuser_alias(bottle.path)
    return bottle.path


# ---------------------------------------------------------------------------
# Windows user folder
# ---------------------------------------------------------------------------

def bottle_user(bottle_path: Path) -> str | None:
    """The bottle's real Windows user folder name (``crossover`` normally)."""
    users = bottle_path / "drive_c" / "users"
    try:
        names = [p.name for p in users.iterdir()
                 if p.is_dir() and not p.is_symlink()
                 and p.name.lower() not in ("public", PROTON_USER)]
    except OSError:
        return None
    return names[0] if len(names) == 1 else None


def ensure_steamuser_alias(bottle_path: Path, log_fn=None) -> bool:
    """Make ``drive_c/users/steamuser`` point at the bottle's real user.

    Upstream's game handlers (plugins.txt, My Games INIs, saves) spell the
    prefix user as Proton's ``steamuser``; CrossOver names it ``crossover``.
    A relative symlink lets every handler work against a bottle unchanged.
    Wine ignores the extra folder. Returns True when the alias is in place.
    """
    users = bottle_path / "drive_c" / "users"
    alias = users / PROTON_USER
    if alias.is_symlink() or alias.is_dir():
        return True
    real = bottle_user(bottle_path)
    if real is None:
        return False
    try:
        alias.symlink_to(real)
    except OSError as exc:
        if log_fn:
            log_fn(f"could not link {alias} -> {real}: {exc}")
        return False
    if log_fn:
        log_fn(f"linked {alias} -> {real} so prefix paths resolve in the bottle")
    return True
