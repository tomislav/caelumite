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


def keychain_usable() -> bool:
    """Keyring probe for macOS: keyring's Keychain backend is active.
    (Upstream's probe asks DBus for the Linux Secret Service, which a Mac
    never has, so every credential would go to the file fallback.)"""
    try:
        import keyring
        from keyring.backends import macOS
        return isinstance(keyring.get_keyring(), macOS.Keyring)
    except Exception:
        return False


# A key the Keychain couldn't store: used for this session only (see
# no_key_file), so logging in still works.
_session_key = ""


def no_key_file(key: str) -> None:
    """macOS replacement for upstream's key-file fallback. That file's
    encryption key comes from /etc/machine-id, which macOS doesn't have, so
    it would only be obfuscated; keep the key in memory instead."""
    global _session_key
    _session_key = key
    from Utils.app_log import app_log
    app_log("Nexus API key: the macOS Keychain is unavailable - the key is "
            "used for this session only and not saved.")


def _move_file_key_to_keychain() -> str:
    """One-time move of a personal key that the file fallback saved (before
    Caelumite checked for the Keychain) into an empty Keychain entry; the
    file is deleted once the Keychain holds the key. Never overwrites a key
    already in the Keychain or the session. Returns the moved key, or ""."""
    import keyring
    from Nexus import nexus_api
    if not nexus_api._keyring_ok():
        return ""
    if nexus_api.load_api_key():
        nexus_api._clear_key_file()   # an older copy; the Keychain's is current
        return ""
    key = nexus_api._load_key_file()
    if not key:
        return ""
    try:
        keyring.set_password(nexus_api._KEYRING_SERVICE, nexus_api._KEYRING_USER, key)
    except Exception:
        return ""
    if nexus_api.load_api_key() == key:
        nexus_api._clear_key_file()
    return key


def load_saved_api() -> dict:
    """Worker-safe replacement for upstream's saved-login load while
    Caelumite is unregistered: the personal key in testing setups, else none
    (stored upstream OAuth tokens belong to the Amethyst app and are ignored).
    A key left in the old key file moves to the Keychain either way."""
    result = {"api": None, "error": "", "revoked": False}
    moved = _move_file_key_to_keychain()
    if not personal_key_allowed():
        return result
    from Nexus.nexus_api import NexusAPI, load_api_key
    # A key typed in this session (kept in memory when the Keychain failed)
    # is the newest one, so it wins.
    key = _session_key or load_api_key() or moved
    if key:
        result["api"] = NexusAPI(key)
    return result


UNREGISTERED = (f"{APP_NAME} isn't registered with Nexus Mods yet, so it "
                "can't log in to Nexus.")


def _stored_key() -> bool:
    """A personal key is saved in the Keychain (or typed this session).
    Read-only: unlike load_saved_api, nothing is moved or loaded."""
    if _session_key:
        return True
    import keyring
    from Nexus.nexus_api import _KEYRING_USER
    return bool(keyring.get_password(KEYRING_SERVICE, _KEYRING_USER))


def session_status(api) -> dict:
    """Upstream's NexusSession.status() (headless mode) while Caelumite is
    unregistered: the testing personal key counts as the login, saved OAuth
    tokens don't (they'd be Amethyst's). Read-only, so polling it is cheap."""
    status = {"authenticated": False, "credential_type": None,
              "access_token_expires_at": None, "access_token_expired": None,
              "refresh_required": None, "error": None}
    try:
        authenticated = api is not None or (personal_key_allowed() and _stored_key())
    except Exception as exc:
        status["error"] = str(exc) or type(exc).__name__
        return status
    if authenticated:
        status.update(authenticated=True, credential_type="api_key")
    return status


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
    try:
        save_api_key(key)
    except OSError as exc:
        window._notify(window.tr("Could not save the Nexus API key: {0}").format(exc),
                       "error")
        _reset_onboarding(window)
        return
    window._append_log("[nexus] personal API key saved")

    # Report the outcome once Nexus has checked the key (upstream's
    # validation worker), not before. A slot left from an earlier attempt
    # that never got a result is replaced, so results aren't shown twice.
    previous = getattr(window, "_caelumite_key_check", None)
    if previous is not None:
        try:
            window._nexus_validated.disconnect(previous)
        except (RuntimeError, TypeError):
            pass

    def _checked(result):
        if isinstance(result, dict) and result.get("api") is not window._nexus_api:
            return
        window._nexus_validated.disconnect(_checked)
        window._caelumite_key_check = None
        name = result.get("name") if isinstance(result, dict) else result
        error = result.get("error") if isinstance(result, dict) else ""
        if name:
            window._notify(window.tr("Logged in to Nexus Mods as {0}.").format(name),
                           "info")
            view = getattr(window, "_onboarding_view", None)
            if view is not None:
                view.on_logged_in()
        else:
            # An error here can be a rejected key or a network problem; the
            # key stays saved either way.
            window._notify(window.tr("Couldn't verify the Nexus API key: {0}")
                           .format(error or window.tr("no response")), "error")
            _reset_onboarding(window)

    window._caelumite_key_check = _checked
    window._nexus_validated.connect(_checked)
    window._notify(window.tr("Checking your Nexus API key\u2026"), "info")
    # As upstream does after an OAuth login: reload the shared API (through
    # load_saved_api), which validates it and refreshes the UI.
    window._nexus_api = None
    window._nexus_api_reload_pending = True
    window._start_nexus_api_init()


def _reset_onboarding(window) -> None:
    """Undo the onboarding page's "Waiting for browser..." state."""
    view = getattr(window, "_onboarding_view", None)
    button = getattr(view, "_sso_btn", None)
    if button is not None:
        button.setEnabled(True)
        button.setText(view.tr("Log in via Nexus Mods"))
        view._set_nexus_status("", "")
