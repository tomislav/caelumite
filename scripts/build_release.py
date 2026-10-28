#!/usr/bin/env python3
"""Build a self-contained, signed and notarized Caelumite.app (Apple silicon).

Unlike scripts/build-app.sh (a development bundle that runs this checkout),
the release bundle carries everything it needs:

  Contents/MacOS/Caelumite          launcher (scripts/bundle/launcher.c)
  Contents/MacOS/caelumite-python   relocatable CPython (python-build-standalone)
  Contents/lib/python3.14/          its standard library + site-packages
  Contents/Resources/app/           the app code (src/), precompiled
  Contents/Resources/bin/7zz        7-Zip, for archive installs

Python finds its standard library from the interpreter's location
(Contents/MacOS/../lib), so nothing outside the bundle is used. The build
trims PySide6 to the Qt modules the app imports (and everything those link),
thins every binary to arm64, repairs the framework layout pip flattens, and
precompiles all Python code - the bundle is never written to at runtime.

Signing (Developer ID, hardened runtime) and notarization need a "Developer
ID Application" certificate in the keychain and a notarytool profile:

  xcrun notarytool store-credentials caelumite --apple-id <id> --team-id <team>

Usage:
  .venv/bin/python scripts/build_release.py               # sign + notarize + DMG
  .venv/bin/python scripts/build_release.py --no-notarize # sign only (or ad hoc)
  .venv/bin/python scripts/build_release.py --identity -  # ad-hoc, for testing

Downloads (cached in build/cache/, checksummed): the CPython build, 7-Zip and
dmgbuild (which lays out the DMG window) pinned below. Output:
build/release/Caelumite.app and Caelumite-<ver>.dmg.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
CACHE = BUILD / "cache"
OUT = BUILD / "release"
APP = OUT / "Caelumite.app"
VENV_SITE = ROOT / ".venv" / "lib" / "python3.14" / "site-packages"

PY_RELEASE = "20261026"
PY_ARCHIVE = f"cpython-3.14.10+{PY_RELEASE}-aarch64-apple-darwin-install_only_stripped.tar.gz"
PY_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/"
          f"{PY_RELEASE}/{PY_ARCHIVE.replace('+', '%2B')}")
PY_SUMS_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/"
               f"{PY_RELEASE}/SHA256SUMS")
SEVENZIP_ARCHIVE = "7z2605-mac.tar.xz"
SEVENZIP_URL = f"https://github.com/ip7z/7zip/releases/download/26.05/{SEVENZIP_ARCHIVE}"
SEVENZIP_SHA256 = "12ef6830317743cfd3f0ab1724bde43fcc270d8b6d8564f8c12c2a2b7f993570"
# dmgbuild lays out the DMG window. Build-time only: installed into
# build/cache, never into .venv (whose site-packages the app ships).
DMGBUILD_WHEELS = {
    "dmgbuild==1.6.7": "37ee5771c377beb3203d9164aae8046ffed8531c06edf9227f5788b3c599b1bf",
    "ds_store==1.3.3": "b92a371efbf1b4ccce2a04d1ed13fceacc4736c81ba09cf5aefb74c088160a35",
    "mac_alias==2.2.3": "7362b521d2132ef92f606a37abfed5fcd849ceb2f28b6f9743e014b02af92f0d",
}

PY_VER = "3.14"
MIN_MACOS = "14.0"   # PySide6 6.12 wheels are built for macOS 14
BUNDLE_ID = "io.github.caelumite"
NOTARY_PROFILE = "caelumite"

# Qt modules the app imports (plus what they link, found from the binaries).
QT_MODULES = ["QtCore", "QtGui", "QtWidgets", "QtOpenGL", "QtOpenGLWidgets",
              "QtMultimedia", "QtMultimediaWidgets", "QtSvg", "QtNetwork"]
# Qt plugin folders worth shipping on macOS; others (QML, 3D, sensors,
# designer, SQL, web view, speech, ...) serve modules the app doesn't use.
QT_PLUGINS = ["platforms", "imageformats", "iconengines", "styles", "multimedia",
              "tls", "networkinformation"]
# Standard-library parts nothing in the app uses.
STDLIB_DROP = ["test", "idlelib", "tkinter", "turtledemo", "ensurepip",
               "turtle.py", "__phello__"]
SITE_DROP = ["pip", "setuptools", "_distutils_hack", "wheel", "maturin",
             "secretstorage", "jeepney"]   # build tools; Linux keyring backends
SRC_SKIP = {"__pycache__", ".DS_Store", ".pytest_cache"}


def run(*cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def out(*cmd) -> str:
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True,
                          text=True).stdout


def step(msg: str) -> None:
    print(f"=== {msg}", flush=True)


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def fetch(url: str, dest: Path) -> Path:
    if not dest.is_file():
        print(f"  downloading {dest.name}")
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as fh:
            shutil.copyfileobj(resp, fh)
        tmp.rename(dest)
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_inputs() -> tuple[Path, Path]:
    step("Fetching CPython and 7-Zip (cached in build/cache)")
    py = fetch(PY_URL, CACHE / PY_ARCHIVE)
    sums = fetch(PY_SUMS_URL, CACHE / f"SHA256SUMS-{PY_RELEASE}")
    want = next((l.split()[0] for l in sums.read_text().splitlines()
                 if l.endswith(" " + PY_ARCHIVE)), None)
    if want is None or sha256(py) != want:
        raise SystemExit(f"error: {PY_ARCHIVE} does not match its SHA256SUMS")
    sz = fetch(SEVENZIP_URL, CACHE / SEVENZIP_ARCHIVE)
    got = sha256(sz)
    if SEVENZIP_SHA256 and got != SEVENZIP_SHA256:
        raise SystemExit(f"error: {SEVENZIP_ARCHIVE} checksum changed: {got}")
    print(f"  7-Zip sha256 {got}")
    return py, sz


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def copytree(src: Path, dst: Path, skip=lambda p: False) -> None:
    def ignore(d, names):
        return [n for n in names if n in SRC_SKIP or skip(Path(d) / n)]
    shutil.copytree(src, dst, symlinks=True, ignore=ignore)


def assemble(py_archive: Path, sz_archive: Path) -> None:
    step(f"Assembling {APP.relative_to(ROOT)}")
    shutil.rmtree(APP, ignore_errors=True)
    contents = APP / "Contents"
    for d in ("MacOS", "Resources/bin", "Resources/licenses", "lib"):
        (contents / d).mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with tarfile.open(py_archive) as tf:
            tf.extractall(tmp / "py", filter="data")
        with tarfile.open(sz_archive) as tf:
            tf.extractall(tmp / "7z", filter="data")
        py = tmp / "py" / "python"
        shutil.copy2(py / "bin" / f"python{PY_VER}", contents / "MacOS" / "caelumite-python")
        stdlib = contents / "lib" / f"python{PY_VER}"
        copytree(py / "lib" / f"python{PY_VER}", stdlib,
                 skip=lambda p: p.parent.name == f"python{PY_VER}"
                 and p.name in STDLIB_DROP + ["site-packages"])
        for so in (stdlib / "lib-dynload").glob("_tkinter*"):
            so.unlink()
        shutil.copy2(py / "lib" / f"python{PY_VER}" / "LICENSE.txt",
                     contents / "Resources" / "licenses" / "Python.txt")
        shutil.copy2(tmp / "7z" / "7zz", contents / "Resources" / "bin" / "7zz")
        shutil.copy2(tmp / "7z" / "License.txt",
                     contents / "Resources" / "licenses" / "7-Zip.txt")

    site = stdlib / "site-packages"
    copytree(VENV_SITE, site, skip=lambda p: p.parent == VENV_SITE and (
        p.name in SITE_DROP or p.name.endswith(".pth")
        or any(p.name.lower().startswith(n.replace("_", "-") + "-")
               or p.name.lower().startswith(n + "-") for n in SITE_DROP)))

    app = contents / "Resources" / "app"
    copytree(ROOT / "src", app, skip=lambda p: p.suffix == ".pyc")
    shutil.copy2(ROOT / "Changelog.txt", app / "Changelog.txt")
    shutil.copy2(ROOT / "LICENSE", contents / "Resources" / "licenses" / "Caelumite.txt")

    build_launcher(contents / "MacOS" / "Caelumite")
    build_icon(contents / "Resources" / "Caelumite.icns")
    write_info_plist(contents / "Info.plist")


def build_launcher(dest: Path) -> None:
    run("clang", "-O2", "-Wall", "-arch", "arm64", f"-mmacosx-version-min={MIN_MACOS}",
        "-o", dest, ROOT / "scripts" / "bundle" / "launcher.c")


def build_icon(dest: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        run(sys.executable, ROOT / "scripts" / "make_icon.py", tmp / "master.png",
            env=env, stdout=subprocess.DEVNULL)
        iconset = tmp / "Caelumite.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ""), (2, "@2x")):
                run("sips", "-z", size * scale, size * scale, tmp / "master.png",
                    "--out", iconset / f"icon_{size}x{size}{suffix}.png",
                    stdout=subprocess.DEVNULL)
        run("iconutil", "-c", "icns", iconset, "-o", dest)


def version() -> str:
    return out(sys.executable, ROOT / "src" / "version.py").strip()


def write_info_plist(dest: Path) -> None:
    ver = version()
    schemes = [("Nexus Mods download link", "nxm"),
               ("Thunderstore install link", "ror2mm"),
               ("MODL download link", "modl")]
    plist = {
        "CFBundleName": "Caelumite", "CFBundleDisplayName": "Caelumite",
        "CFBundleIdentifier": BUNDLE_ID, "CFBundleExecutable": "Caelumite",
        "CFBundleIconFile": "Caelumite", "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": ver, "CFBundleVersion": ver,
        "LSMinimumSystemVersion": MIN_MACOS,
        "LSApplicationCategoryType": "public.app-category.games",
        "LSArchitecturePriority": ["arm64"],
        "NSHighResolutionCapable": True, "NSPrincipalClass": "NSApplication",
        "NSHumanReadableCopyright": "GPL-3.0. Based on Amethyst Mod Manager by ChrisDKN.",
        "CFBundleURLTypes": [{"CFBundleURLName": n, "CFBundleURLSchemes": [s]}
                             for n, s in schemes],
    }
    with open(dest, "wb") as fh:
        plistlib.dump(plist, fh)


# ---------------------------------------------------------------------------
# PySide6 trimming and binary fixes
# ---------------------------------------------------------------------------

def is_macho(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with open(path, "rb") as fh:
        magic = fh.read(4)
    return magic in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                     b"\xfe\xed\xfa\xcf")


def linked(path: Path) -> list[str]:
    lines = out("otool", "-L", path).splitlines()[1:]
    return [l.strip().split(" (")[0] for l in lines]


def trim_pyside() -> None:
    step("Trimming PySide6 to the Qt modules the app uses")
    pyside = APP / "Contents" / "lib" / f"python{PY_VER}" / "site-packages" / "PySide6"
    qtlib, plugins = pyside / "Qt" / "lib", pyside / "Qt" / "plugins"

    # Plugins: keep the useful folders, and only the Cocoa platform plugin.
    for d in plugins.iterdir():
        if d.name not in QT_PLUGINS:
            shutil.rmtree(d)
    for p in (plugins / "platforms").iterdir():
        if p.name not in ("libqcocoa.dylib", "libqoffscreen.dylib", "libqminimal.dylib"):
            p.unlink()

    keep_bindings = {f"{m}.abi3.so" for m in QT_MODULES}
    for so in pyside.glob("Qt*.abi3.so"):
        if so.name not in keep_bindings:
            so.unlink()

    # Tools, QML, headers and other development files - before the
    # dependency walk, since they link most of Qt.
    for name in ("Assistant.app", "Designer.app", "Linguist.app", "include", "glue",
                 "typesystems", "scripts", "support", "doc", "examples"):
        target = pyside / name
        if target.is_dir():
            shutil.rmtree(target)
    for exe in pyside.iterdir():
        if is_macho(exe) and exe.suffix not in (".so", ".dylib"):
            exe.unlink()   # qmlls, qmlformat, uic, rcc, lupdate, ...
    for lib in pyside.glob("libpyside6qml*.dylib"):
        lib.unlink()       # only the QtQml bindings use it
    for name in ("qml", "metatypes", "libexec", "mkspecs"):
        shutil.rmtree(pyside / "Qt" / name, ignore_errors=True)
    trans = pyside / "Qt" / "translations"
    if trans.is_dir():
        for qm in trans.rglob("*"):
            if qm.is_file() and not qm.name.startswith(("qtbase_", "qt_")):
                qm.unlink()
    for pyi in pyside.glob("*.pyi"):
        pyi.unlink()

    # Everything the kept bindings and plugins link, transitively.
    roots = [p for p in pyside.rglob("*") if is_macho(p) and "Qt/lib" not in str(p)]
    needed: set[str] = set()
    todo = list(roots)
    seen: set[Path] = set()
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        for dep in linked(f):
            if not dep.startswith("@rpath/"):
                continue
            rel = dep.removeprefix("@rpath/")
            needed.add(rel.split("/")[0])
            target = qtlib / rel
            if target.exists():
                todo.append(target.resolve())
    for item in qtlib.iterdir():
        if item.name not in needed:
            shutil.rmtree(item) if item.is_dir() and not item.is_symlink() else item.unlink()
    print("  kept Qt libraries: " + ", ".join(sorted(needed)))


def fix_frameworks() -> None:
    """Restore the framework layout pip's wheels flatten (no symlinks), which
    codesign requires: Versions/Current, and top-level links to it."""
    for fw in APP.rglob("*.framework"):
        name = fw.stem
        versions = fw / "Versions"
        version_dirs = [d for d in versions.iterdir() if d.is_dir() and not d.is_symlink()]
        if len(version_dirs) != 1:
            continue
        ver = version_dirs[0]
        current = versions / "Current"
        if not current.is_symlink():
            current.symlink_to(ver.name)
        top_res = fw / "Resources"
        if top_res.is_dir() and not top_res.is_symlink():
            dest = ver / "Resources"
            dest.mkdir(exist_ok=True)
            for f in top_res.iterdir():
                if not (dest / f.name).exists():
                    shutil.move(str(f), str(dest / f.name))
            shutil.rmtree(top_res)
        for link, target in ((fw / name, f"Versions/Current/{name}"),
                             (fw / "Resources", "Versions/Current/Resources")):
            if not link.exists() and not link.is_symlink() and (fw / target).exists():
                link.symlink_to(target)


def dedupe_dylib_aliases() -> None:
    """libavcodec.63.dylib and libavcodec.63.1.101.dylib arrive as two
    identical files; keep one and link the other."""
    for lib in APP.rglob("*.dylib"):
        if lib.is_symlink():
            continue
        m = re.match(r"^(.+?\.\d+)\.\d+\.\d+\.dylib$", lib.name)
        if not m:
            continue
        alias = lib.with_name(m.group(1) + ".dylib")
        if alias.is_file() and not alias.is_symlink() and sha256(alias) == sha256(lib):
            alias.unlink()
            alias.symlink_to(lib.name)


def thin_to_arm64() -> int:
    step("Thinning universal binaries to arm64")
    n = 0
    for f in APP.rglob("*"):
        if is_macho(f) and "x86_64" in out("lipo", "-archs", f):
            run("lipo", "-thin", "arm64", f, "-output", f)
            n += 1
    return n


def precompile() -> None:
    step("Precompiling Python code")
    python = APP / "Contents" / "MacOS" / "caelumite-python"
    run(python, "-m", "compileall", "-q", "-j0", "--invalidation-mode", "unchecked-hash",
        APP / "Contents" / "lib" / f"python{PY_VER}", APP / "Contents" / "Resources" / "app",
        stdout=subprocess.DEVNULL)


def smoke_test() -> None:
    step("Smoke test: bundled Python imports the app's dependencies")
    python = APP / "Contents" / "MacOS" / "caelumite-python"
    code = ("import sys, ssl, sqlite3, PySide6.QtWidgets, PySide6.QtMultimedia, "
            "PySide6.QtOpenGLWidgets, PySide6.QtSvg, requests, cryptography, keyring, py7zr, "
            "loot, amethyst_filegraph; "
            "assert sys.prefix.endswith('Contents'), sys.prefix; print('  ok', sys.version.split()[0])")
    run(python, "-B", "-s", "-c", code, cwd=APP / "Contents" / "Resources" / "app",
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())})


# ---------------------------------------------------------------------------
# Signing, notarization, DMG
# ---------------------------------------------------------------------------

def find_identity() -> str:
    ids = out("security", "find-identity", "-v", "-p", "codesigning")
    m = re.search(r'"(Developer ID Application: [^"]+)"', ids)
    return m.group(1) if m else "-"


def sign(identity: str) -> None:
    step(f"Signing ({'ad hoc' if identity == '-' else identity})")
    entitlements = ROOT / "scripts" / "bundle" / "entitlements.plist"
    base = ["codesign", "--force", "--sign", identity]
    if identity != "-":
        base += ["--options", "runtime", "--timestamp"]
    contents = APP / "Contents"
    machos = [f for f in contents.rglob("*") if is_macho(f)
              and f.parent != contents / "MacOS"]
    # Deepest first, so containers are signed after what they contain.
    for f in sorted(machos, key=lambda p: len(p.parts), reverse=True):
        run(*base, f, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for fw in sorted(contents.rglob("*.framework"), key=lambda p: len(p.parts), reverse=True):
        run(*base, fw, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for exe in ("caelumite-python", "Caelumite"):
        run(*base, "--entitlements", entitlements, contents / "MacOS" / exe,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run(*base, "--entitlements", entitlements, APP,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run("codesign", "--verify", "--deep", "--strict", APP)
    print("  signature verified")


def notarize(path: Path, profile: str) -> None:
    step(f"Notarizing {path.name} (this takes a few minutes)")
    submit = path
    if path.suffix == ".app":
        submit = OUT / "Caelumite-notarize.zip"
        submit.unlink(missing_ok=True)
        run("ditto", "-c", "-k", "--keepParent", path, submit)
    result = subprocess.run(["xcrun", "notarytool", "submit", str(submit),
                             "--keychain-profile", profile, "--wait"],
                            capture_output=True, text=True)
    print(result.stdout.strip())
    if submit != path:
        submit.unlink(missing_ok=True)
    if result.returncode != 0 or "status: Accepted" not in result.stdout:
        m = re.search(r"id: ([0-9a-f-]{36})", result.stdout)
        if m:
            print(out("xcrun", "notarytool", "log", m.group(1),
                      "--keychain-profile", profile))
        raise SystemExit("error: notarization failed")
    run("xcrun", "stapler", "staple", path, stdout=subprocess.DEVNULL)
    print("  ticket stapled")


def load_dmgbuild():
    """dmgbuild from build/cache, installed there from the pinned wheels."""
    target = CACHE / "dmgbuild"
    stamp = target / "pins.txt"
    pins = "".join(f"{spec} --hash=sha256:{sha}\n"
                   for spec, sha in DMGBUILD_WHEELS.items())
    if not stamp.is_file() or stamp.read_text() != pins:
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        req = target / "requirements.txt"
        req.write_text(pins)
        run(sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
            "--no-deps", "--require-hashes", "--only-binary=:all:",
            "--target", target, "-r", req)
        stamp.write_text(pins)
    sys.path.insert(0, str(target))
    import dmgbuild
    return dmgbuild


def make_dmg(identity: str) -> Path:
    """The DMG: a window with the app, an Applications link and an arrow
    between them on the background from scripts/make_dmg_background.py."""
    step("Building the disk image")
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_dmg_background as bg
    dmgbuild = load_dmgbuild()
    dmg = OUT / f"Caelumite-{version()}.dmg"
    dmg.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        run(sys.executable, ROOT / "scripts" / "make_dmg_background.py", tmp,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dmgbuild.build_dmg(str(dmg), "Caelumite", settings={
            "format": "ULFO",
            "filesystem": "APFS",
            "files": [str(APP)],
            "symlinks": {"Applications": "/Applications"},
            "icon": str(APP / "Contents" / "Resources" / "Caelumite.icns"),
            "background": str(Path(tmp) / "background.png"),
            "window_rect": ((200, 120), (bg.WIDTH, bg.HEIGHT)),
            "default_view": "icon-view",
            "icon_size": 128,
            "text_size": 13,
            "icon_locations": {APP.name: bg.ICON_APP, "Applications": bg.ICON_APPS},
            "hide_extensions": [APP.name],
            "show_status_bar": False,
            "show_tab_view": False,
            "show_toolbar": False,
            "show_pathbar": False,
            "show_sidebar": False,
        })
    if identity != "-":
        run("codesign", "--sign", identity, "--timestamp", dmg, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    return dmg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--identity", help='signing identity; "-" for ad hoc '
                    "(default: the keychain's Developer ID Application)")
    ap.add_argument("--no-notarize", action="store_true")
    ap.add_argument("--no-dmg", action="store_true")
    ap.add_argument("--profile", default=NOTARY_PROFILE, help="notarytool keychain profile")
    a = ap.parse_args()

    if not (VENV_SITE / "PySide6").is_dir():
        raise SystemExit("error: run scripts/setup-macos.sh first (needs .venv)")
    identity = a.identity or find_identity()
    notarize_it = not a.no_notarize and identity != "-"

    py, sz = fetch_inputs()
    assemble(py, sz)
    trim_pyside()
    fix_frameworks()
    dedupe_dylib_aliases()
    print(f"  thinned {thin_to_arm64()} binaries")
    precompile()
    smoke_test()
    sign(identity)
    if notarize_it:
        notarize(APP, a.profile)
    if not a.no_dmg:
        dmg = make_dmg(identity)
        if notarize_it:
            notarize(dmg, a.profile)
        print(f"Built {dmg.relative_to(ROOT)}")
    size = out("du", "-sh", APP).split()[0]
    print(f"Built {APP.relative_to(ROOT)} ({size})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
