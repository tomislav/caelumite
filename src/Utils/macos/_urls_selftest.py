"""Self-check for Utils.macos.urls.

Run from src/: python -m Utils.macos._urls_selftest
"""

from __future__ import annotations

from unittest.mock import patch

from Utils.macos import urls
from Utils.macos.app import BUNDLE_ID


def test_undeclared_schemes_are_left_alone() -> None:
    # Upstream's gale:// and wabbajack:// handlers subclass Ror2mmHandler and
    # inherit its LaunchServices hook, but the app bundle doesn't declare
    # those schemes: making Caelumite their default handler would claim
    # links it never receives, again on every start.
    with (patch.object(urls, "running_bundle_id", return_value=BUNDLE_ID),
          patch.object(urls, "default_handler", return_value=None),
          patch.object(urls._CS, "LSSetDefaultHandlerForURLScheme",
                       return_value=0) as set_default):
        for scheme in ("gale", "wabbajack"):
            assert urls.registration_is_current(scheme), scheme
            assert not urls.register_default(scheme), scheme
        assert set_default.call_count == 0
        assert urls.register_default("ror2mm")
        assert set_default.call_count == 1


if __name__ == "__main__":
    test_undeclared_schemes_are_left_alone()
    print("✓ only the schemes the app bundle declares are registered")
