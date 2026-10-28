#!/usr/bin/env python3
"""Self-checks for the release DMG (scripts/build_release.py).

Run: .venv/bin/python scripts/_build_release_selftest.py

Builds a DMG of a tiny ad-hoc-signed app in a temporary folder (hdiutil
attaches it briefly); the real build/release output is never touched.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import build_release as br  # noqa: E402


def _tiny_app(folder: Path) -> Path:
    app = folder / "Caelumite.app"
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    exe = macos / "Caelumite"
    shutil.copyfile("/usr/bin/true", exe)    # not copy2: /usr/bin flags stay behind
    exe.chmod(0o755)
    (app / "Contents" / "Resources" / "Caelumite.icns").write_bytes(b"icns")
    with (app / "Contents" / "Info.plist").open("wb") as fh:
        plistlib.dump({"CFBundleExecutable": "Caelumite",
                       "CFBundleIdentifier": "io.github.caelumite.selftest",
                       "CFBundlePackageType": "APPL"}, fh)
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True,
                   capture_output=True)
    return app


def test_dmg_keeps_the_apps_strict_signature() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "release"
        out.mkdir()
        app = _tiny_app(out)
        with (patch.object(br, "OUT", out), patch.object(br, "APP", app),
              patch.object(br, "version", return_value="0.0.0")):
            dmg = br.make_dmg("-")
        mount = Path(tmp) / "mnt"
        mount.mkdir()
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-quiet",
                        "-mountpoint", str(mount), str(dmg)], check=True)
        try:
            inside = mount / app.name
            verify = subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", str(inside)],
                capture_output=True, text=True)
            assert verify.returncode == 0, verify.stderr
            attrs = subprocess.run(["xattr", str(inside)], capture_output=True,
                                   text=True).stdout
            assert "com.apple.FinderInfo" not in attrs, attrs
        finally:
            subprocess.run(["hdiutil", "detach", "-quiet", str(mount)], check=False)


def test_failed_command_shows_its_output() -> None:
    try:
        br.run_quiet(sys.executable, "-c",
                     "import sys; sys.stderr.write('background failed'); sys.exit(3)")
    except SystemExit as exc:
        assert "background failed" in str(exc), exc
    else:
        raise AssertionError("a failing command didn't stop the build")


def test_broken_dmgbuild_cache_is_reinstalled() -> None:
    saved_path = list(sys.path)
    saved = {n: m for n, m in sys.modules.items() if n.split(".")[0] == "dmgbuild"}
    for name in saved:
        del sys.modules[name]
    installs: list[list[str]] = []

    def fake_run(*cmd, **_kw):
        installs.append([str(c) for c in cmd])
        target = Path(cmd[cmd.index("--target") + 1])
        (target / "dmgbuild").mkdir(parents=True, exist_ok=True)
        (target / "dmgbuild" / "__init__.py").write_text("FAKE = True\n")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            target = cache / "dmgbuild"
            target.mkdir()
            (target / "pins.txt").write_text(br._dmgbuild_pins())
            with (patch.object(br, "CACHE", cache), patch.object(br, "run", fake_run)):
                module = br.load_dmgbuild()
            assert getattr(module, "FAKE", False) and len(installs) == 1, installs
    finally:
        sys.path[:] = saved_path
        for name in [n for n in sys.modules if n.split(".")[0] == "dmgbuild"]:
            del sys.modules[name]
        sys.modules.update(saved)


def test_background_usage_message() -> None:
    result = subprocess.run([sys.executable, str(SCRIPTS / "make_dmg_background.py")],
                            capture_output=True, text=True,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    import make_dmg_background as bg
    assert result.returncode == 2 and bg.USAGE in result.stderr, result.stderr


if __name__ == "__main__":
    test_broken_dmgbuild_cache_is_reinstalled()
    print("✓ a broken dmgbuild cache is reinstalled")
    test_failed_command_shows_its_output()
    print("✓ a failing build command shows its output")
    test_background_usage_message()
    print("✓ the background script prints its usage")
    test_dmg_keeps_the_apps_strict_signature()
    print("✓ the app in the DMG keeps its strict signature")
