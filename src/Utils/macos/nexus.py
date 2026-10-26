"""
Utils.macos.nexus
How Caelumite talks to Nexus Mods while it waits for its own registration.

Nexus's API Acceptable Use Policy treats request metadata that impersonates
another application as unacceptable, and allows personal API keys only for
testing and personal use - not in a public-facing app. Upstream ships its own
registered OAuth client ("amethyst"), which Caelumite must not use. So:

  * requests identify as Caelumite (Application-Name);
  * OAuth login uses Caelumite's own client (Utils.macos.app); while that is
    empty, OAuth is off and the inherited Amethyst login is never used;
  * a personal API key works only when the testing switch is on:
    ``[dev] nexus_personal_key = true`` in amethyst.ini, or
    ``CAELUMITE_NEXUS_PERSONAL_KEY=1``. Without it, Nexus features stay
    logged out and the login button explains why.
"""

from __future__ import annotations

from Utils.macos.app import APP_NAME, NEXUS_CLIENT_ID, NEXUS_CLIENT_SECRET

APPLICATION_NAME = APP_NAME
KEYRING_SERVICE = APP_NAME
PERSONAL_KEY_FLAG = "nexus_personal_key"
PERSONAL_KEY_ENV = "CAELUMITE_NEXUS_PERSONAL_KEY"
API_KEY_PAGE = "https://www.nexusmods.com/users/myaccount?tab=api+access"


def registered() -> bool:
    """True once Nexus has issued Caelumite its own OAuth credentials."""
    return bool(NEXUS_CLIENT_ID and NEXUS_CLIENT_SECRET)


def personal_key_allowed() -> bool:
    """The testing switch for personal API keys."""
    from Utils.ui.config import _dev_flag
    return _dev_flag(PERSONAL_KEY_FLAG, PERSONAL_KEY_ENV)


def load_saved_api() -> dict:
    """Worker-safe replacement for upstream's saved-login load while
    Caelumite is unregistered: the personal key in testing setups, else none
    (stored upstream OAuth tokens belong to the Amethyst app and are ignored)."""
    result = {"api": None, "error": "", "revoked": False}
    if not personal_key_allowed():
        return result
    from Nexus.nexus_api import NexusAPI, load_api_key
    key = load_api_key()
    if key:
        result["api"] = NexusAPI(key)
    return result


def login(window) -> None:
    """The Nexus login button while Caelumite is unregistered (UI thread)."""
    from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox

    if not personal_key_allowed():
        QMessageBox.information(
            window, "Nexus Mods",
            f"{APP_NAME} isn't registered with Nexus Mods yet, so it can't log "
            "in to Nexus. Installing mods from downloaded archives, deploying, "
            "LOOT and the wizards all work without it.\n\n"
            "Nexus allows personal API keys only for testing and personal use. "
            "To test with yours, add \"nexus_personal_key = true\" under [dev] "
            "in amethyst.ini and restart.")
        _reset_onboarding(window)
        return

    from Utils.environment.xdg import open_url
    open_url(API_KEY_PAGE)
    key, ok = QInputDialog.getText(
        window, "Nexus Mods API key",
        "Paste your personal API key from the page that just opened\n"
        "(Nexus Mods \u2192 Site preferences \u2192 API Keys).\n\n"
        "For testing and personal use only.",
        QLineEdit.Password)
    key = (key or "").strip()
    if not ok or not key:
        _reset_onboarding(window)
        return
    from Nexus.nexus_api import save_api_key
    save_api_key(key)
    # As upstream does after an OAuth login: reload the shared API (through
    # load_saved_api), which validates it and refreshes the UI.
    window._nexus_api = None
    window._nexus_api_reload_pending = True
    window._start_nexus_api_init()
    window._notify(window.tr("Logged in to Nexus Mods."), "info")
    window._append_log("[nexus] personal API key saved")
    view = getattr(window, "_onboarding_view", None)
    if view is not None:
        view.on_logged_in()


def _reset_onboarding(window) -> None:
    """Undo the onboarding page's "Waiting for browser..." state."""
    view = getattr(window, "_onboarding_view", None)
    button = getattr(view, "_sso_btn", None)
    if button is not None:
        button.setEnabled(True)
        button.setText(view.tr("Log in via Nexus Mods"))
        view._set_nexus_status("", "")
