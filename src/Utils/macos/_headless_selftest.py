"""Self-checks for headless mode on macOS (cli.py headless): it identifies
as Caelumite, and the Nexus login stays off until Nexus registers Caelumite
(Utils/macos/nexus.py), as in the app.

Run from src/: python -m Utils.macos._headless_selftest

Runs `cli.py headless --stdio` with HOME and TMPDIR in a temporary folder,
so the real config isn't read or written. Nothing reaches Nexus.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2]


def _headless(*requests: dict) -> list[dict]:
    lines = "".join(json.dumps({"jsonrpc": "2.0", "id": i, **r}) + "\n"
                    for i, r in enumerate(requests, 1))
    with tempfile.TemporaryDirectory() as home:
        (Path(home) / "tmp").mkdir()
        env = {**os.environ, "HOME": home, "TMPDIR": str(Path(home) / "tmp")}
        out = subprocess.run([sys.executable, "cli.py", "headless", "--stdio"],
                             cwd=SRC, input=lines, capture_output=True, text=True,
                             env=env, timeout=120).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def test_handshake_names_caelumite() -> None:
    reply = _headless({"method": "system.handshake", "params": {"protocol_version": 1}})[0]
    assert reply["result"]["application"]["name"] == "Caelumite", reply


def test_login_stays_off() -> None:
    reply = _headless({"method": "nexus.auth.login.start", "params": {}})[0]
    assert reply.get("error", {}).get("data", {}).get("name") == "nexus_login_unavailable", reply


def _memory_keyring():
    import keyring.backend

    class MemoryKeyring(keyring.backend.KeyringBackend):
        priority = 1

        def __init__(self):
            super().__init__()
            self.items = {}

        def get_password(self, service, username):
            return self.items.get((service, username))

        def set_password(self, service, username, password):
            self.items[(service, username)] = password

        def delete_password(self, service, username):
            self.items.pop((service, username), None)

    return MemoryKeyring()


def test_status_matches_what_nexus_calls_use() -> None:
    # The status is read-only, yet must say "logged in" exactly when
    # require_api() (the call every Nexus method makes) finds the testing
    # personal key: in the Keychain, only while Caelumite uses the Keychain;
    # in the old key file, which require_api would move.
    import keyring
    from Nexus import nexus_api
    from Nexus.session import NexusSession, NexusSessionError
    from Utils.config_paths import get_config_dir
    from Utils.macos import nexus

    def require():
        try:
            NexusSession().require_api()
            return True
        except NexusSessionError:
            return False

    def case(*, allowed=True, keychain=False, keychain_ok=True, legacy_file=False):
        with tempfile.TemporaryDirectory() as home, \
                patch.dict(os.environ, {"HOME": home}), \
                patch.object(nexus, "registered", return_value=False), \
                patch.object(nexus, "personal_key_allowed", return_value=allowed), \
                patch.object(nexus_api, "_keyring_ok", return_value=keychain_ok), \
                patch.object(nexus, "_session_key", ""):
            ring = _memory_keyring()
            previous = keyring.get_keyring()
            keyring.set_keyring(ring)
            try:
                if keychain:
                    ring.set_password(nexus.KEYRING_SERVICE, nexus_api._KEYRING_USER, "k1")
                if legacy_file:
                    get_config_dir().mkdir(parents=True, exist_ok=True)
                    nexus_api._api_key_path().write_text("k2", encoding="utf-8")
                before = dict(ring.items)
                status = NexusSession().status()["authenticated"]
                assert ring.items == before, "the status changed the Keychain"
                return status, require()
            finally:
                keyring.set_keyring(previous)

    assert case(keychain=True) == (True, True)
    assert case(keychain=True, keychain_ok=False) == (False, False)
    assert case(legacy_file=True) == (True, True)
    assert case() == (False, False)
    assert case(keychain=True, allowed=False) == (False, False)


class _Sent(Exception):
    """Stops a download once its request is built."""


class _Control:
    """A job control that is never paused or cancelled."""

    def __getattr__(self, name):
        return lambda *args, **kwargs: False


def test_downloads_identify_as_caelumite() -> None:
    from types import SimpleNamespace
    from amethyst_backend import modio_versions, tool_acquisition
    from Utils.macos.app import USER_AGENT
    sent: list[str] = []

    def urlopen(request, *args, **kwargs):
        sent.append(request.get_header("User-agent"))
        raise _Sent

    class Session:
        def __init__(self):
            self.headers = {}
            self.verify = True
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def get(self, *args, **kwargs):
            sent.append(self.headers.get("User-Agent"))
            raise _Sent

    with tempfile.TemporaryDirectory() as tmp, \
            patch("Utils.config_paths.get_download_cache_dir_for_game", return_value=tmp):
        with patch("urllib.request.urlopen", urlopen):
            try:
                tool_acquisition._download(
                    SimpleNamespace(name="Starfield"), "tool", 0,
                    {"archive_keywords": [], "source": {"kind": "url"}},
                    "https://example.com/tool.zip", "1.0", _Control(), None)
            except _Sent:
                pass
        with patch("requests.Session", Session):
            file = SimpleNamespace(download_url="https://example.com/mod.zip",
                                   download_expires=0, file_id=1)
            try:
                modio_versions.download(SimpleNamespace(name="Baldur's Gate 3"), 2, file,
                                        {}, print, None, _Control())
            except _Sent:
                pass
    assert sent == [USER_AGENT, USER_AGENT], sent


if __name__ == "__main__":
    test_handshake_names_caelumite()
    print("✓ headless mode identifies as Caelumite")
    test_login_stays_off()
    print("✓ headless mode can't start a Nexus login while Caelumite is unregistered")
    test_status_matches_what_nexus_calls_use()
    print("✓ the login status matches the key Nexus calls would use, read-only")
    test_downloads_identify_as_caelumite()
    print("✓ headless tool and mod.io downloads identify as Caelumite")
