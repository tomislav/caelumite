"""
Utils.macos.branding
Shows the app as "Caelumite" without editing upstream's UI strings.

Every user-visible string goes through Qt's tr(), so a translator installed
last (Qt asks the most recently installed translator first) can rewrite the
upstream name at display time. It first asks the language translators that
were installed before it, so a translated UI keeps its translation and only
the name changes.

Strings that mean the upstream project itself (the Nexus "Endorse" button,
Ko-fi, credits) are left alone - see _KEEP.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QTranslator

from Utils.macos.app import APP_NAME

_RENAMES = (
    (re.compile(r"Amethyst Mod Manager"), APP_NAME),
    (re.compile(r"\bAMM\b"), APP_NAME),
    (re.compile(r"\bAmethyst\b(?![-_.])"), APP_NAME),
)

# Source strings that refer to upstream on purpose.
_KEEP = re.compile(r"Endorse|Ko-?fi|upstream|ChrisDKN", re.IGNORECASE)

# Whole strings that describe the Linux runtime; on macOS the game's
# CrossOver bottle plays that role.
_EXACT = {
    "Proton": "CrossOver",
    "Proton prefix": "CrossOver bottle",
    "{0} prefix": "{0} in CrossOver",
    "Run an .exe in this prefix\u2026": "Run an .exe in this bottle\u2026",
    "Auto detects Steam/Heroic/Lutris/Faugus/Bottles ownership. Force a specific "
    "launcher, or None to always launch the exe directly via Proton.":
        "Auto launches through Steam in the game's CrossOver bottle. None always "
        "runs the exe directly in the bottle.",
}
_SUBSTRINGS: tuple[tuple[str, str], ...] = ()


def rebrand(text: str) -> str:
    if not text or _KEEP.search(text):
        return text
    if text in _EXACT:
        return _EXACT[text]
    for old, new in _SUBSTRINGS:
        text = text.replace(old, new)
    for pattern, repl in _RENAMES:
        text = pattern.sub(repl, text)
    return text


class RenameTranslator(QTranslator):
    """Rewrites the upstream app name in every translated or source string."""

    def __init__(self, parent, language_translators):
        super().__init__(parent)
        self._language = list(language_translators)

    def translate(self, context, source_text, disambiguation=None, n=-1):
        if not source_text:
            return None
        text = ""
        for tr in self._language:
            text = tr.translate(context, source_text, disambiguation, n)
            if text:
                break
        base = text or source_text
        renamed = rebrand(base)
        # None (a null QString) tells Qt this translator has no opinion, so
        # the language translators or the source string answer unchanged. An
        # empty string would be taken as a translation and blank the label.
        return renamed if renamed != base else None

    def isEmpty(self) -> bool:
        return False


def install_rename_translator(app, language_translators) -> QTranslator:
    translator = RenameTranslator(app, language_translators)
    app.installTranslator(translator)
    return translator


def apply_identity(app) -> None:
    """Application name for the menu bar and About on macOS, and the filter
    that hides Linux-only controls. The window icon comes from
    icons/Logo.png, which Caelumite replaces (scripts/make_icon.py)."""
    from Utils.macos import ui_prune

    app.setApplicationName(APP_NAME)
    ui_prune.install(app)
