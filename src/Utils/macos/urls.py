"""
Utils.macos.urls
nxm:// links on macOS.

The app bundle declares the ``nxm`` scheme (scripts/build-app.sh), and
LaunchServices delivers a clicked link to the running app as an Apple event,
which Qt turns into a QFileOpenEvent - there is no second process with the
link in argv as on Linux. On a cold start the event can arrive before the
main window exists, so links are queued until :func:`attach` hands over the
window; they then go through the same signals upstream's link IPC uses.

Upstream's ``NxmHandler`` (``.desktop`` files and xdg-mime) is mapped onto
LaunchServices: registering makes this bundle the default nxm handler.
"""

from __future__ import annotations

import ctypes

from PySide6.QtCore import QEvent, QObject, QTimer

from Utils.macos.app import BUNDLE_ID

SCHEMES = ("nxm",)

_CF = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_CS = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreServices.framework/CoreServices")
_UTF8 = 0x08000100  # kCFStringEncodingUTF8

_CF.CFStringCreateWithCString.restype = ctypes.c_void_p
_CF.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
_CF.CFStringGetCString.restype = ctypes.c_bool
_CF.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
_CF.CFRelease.argtypes = [ctypes.c_void_p]
_CF.CFBundleGetMainBundle.restype = ctypes.c_void_p
_CF.CFBundleGetIdentifier.restype = ctypes.c_void_p
_CF.CFBundleGetIdentifier.argtypes = [ctypes.c_void_p]
_CS.LSSetDefaultHandlerForURLScheme.restype = ctypes.c_int32
_CS.LSSetDefaultHandlerForURLScheme.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_CS.LSCopyDefaultHandlerForURLScheme.restype = ctypes.c_void_p
_CS.LSCopyDefaultHandlerForURLScheme.argtypes = [ctypes.c_void_p]


def _cf(text: str):
    return _CF.CFStringCreateWithCString(None, text.encode(), _UTF8)


def _py(cfstr) -> str | None:
    if not cfstr:
        return None
    buf = ctypes.create_string_buffer(512)
    return buf.value.decode() if _CF.CFStringGetCString(cfstr, buf, 512, _UTF8) else None


def running_bundle_id() -> str | None:
    """This process's bundle identifier; None when not run from the .app."""
    return _py(_CF.CFBundleGetIdentifier(_CF.CFBundleGetMainBundle()))


def default_handler(scheme: str) -> str | None:
    s = _cf(scheme)
    try:
        handler = _CS.LSCopyDefaultHandlerForURLScheme(s)
        try:
            return _py(handler)
        finally:
            if handler:
                _CF.CFRelease(handler)
    finally:
        _CF.CFRelease(s)


def is_default(scheme: str = "nxm") -> bool:
    handler = default_handler(scheme)
    return bool(handler) and handler.lower() == BUNDLE_ID.lower()


def register_default(scheme: str = "nxm") -> bool:
    """Make Caelumite the default *scheme* handler. Only possible from the
    app bundle - LaunchServices needs the bundle that declares the scheme."""
    from Nexus.nxm_handler import nxm_log
    if running_bundle_id() != BUNDLE_ID:
        nxm_log(f"{scheme}:// not registered - Caelumite is not running from "
                "Caelumite.app (build it with scripts/build-app.sh).")
        return False
    if is_default(scheme):
        return True
    s, b = _cf(scheme), _cf(BUNDLE_ID)
    try:
        status = _CS.LSSetDefaultHandlerForURLScheme(s, b)
    finally:
        _CF.CFRelease(s)
        _CF.CFRelease(b)
    nxm_log(f"{scheme}:// default handler set to {BUNDLE_ID} (status {status})")
    return status == 0


# ---------------------------------------------------------------------------
# Receiving links
# ---------------------------------------------------------------------------

class _LinkFilter(QObject):
    """Catches link Apple events (QFileOpenEvent) for the whole app."""

    def __init__(self, parent):
        super().__init__(parent)
        self.window = None
        self.pending: list[str] = []

    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        if event.type() != QEvent.FileOpen:
            return False
        url = event.url().toString() or event.file()
        if not url.lower().startswith(tuple(f"{s}://" for s in SCHEMES)):
            return False
        from Nexus.nxm_handler import nxm_log
        nxm_log(f"macOS link event: {url.split('?', 1)[0]}")
        if self.window is None:
            self.pending.append(url)
        else:
            self.window._nxm_received.emit(url)
        return True


_filter: _LinkFilter | None = None


def install(app) -> None:
    """Start receiving link events (right after QApplication exists)."""
    global _filter
    _filter = _LinkFilter(app)
    app.installEventFilter(_filter)


def attach(window) -> None:
    """Deliver links to *window*; queued ones once it has finished building
    (the same delay upstream gives an nxm:// link from argv)."""
    if _filter is None:
        return
    _filter.window = window
    pending, _filter.pending = _filter.pending, []
    for url in pending:
        QTimer.singleShot(500, lambda u=url: window._nxm_received.emit(u))
