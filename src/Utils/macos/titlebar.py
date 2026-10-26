"""
Utils.macos.titlebar
Paints each window's title bar in the theme's header color.

A standard macOS title bar is drawn by AppKit in the system's light or dark
gray, which clashes with most themes. Making it transparent
(``titlebarAppearsTransparent``) shows the NSWindow's background color
there instead; Qt paints the whole content area itself, so that color is only
visible in the title bar. The appearance is set to dark or light Aqua so the
title text and window buttons stay legible on the theme color.

The color is the application palette's Button role, which upstream's
apply_theme() fills with the header bar color (BG_HEADER), so a header bar at
the top of the window continues seamlessly into the title bar. An application
event filter applies it to every top-level window as it is shown and again
whenever the theme changes.
"""

from __future__ import annotations

import ctypes
import ctypes.util

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QWidget

_objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
_objc.objc_getClass.restype = ctypes.c_void_p
_objc.objc_getClass.argtypes = [ctypes.c_char_p]
_objc.sel_registerName.restype = ctypes.c_void_p
_objc.sel_registerName.argtypes = [ctypes.c_char_p]
_MSG = ctypes.cast(_objc.objc_msgSend, ctypes.c_void_p).value

_CF = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_CF.CFStringCreateWithCString.restype = ctypes.c_void_p
_CF.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
_CF.CFRelease.argtypes = [ctypes.c_void_p]
_UTF8 = 0x08000100


def _send(restype, receiver, selector: str, *args):
    """objc_msgSend with an exact prototype (required on Apple silicon)."""
    argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [type(a) for a in args]
    fn = ctypes.CFUNCTYPE(restype, *argtypes)(_MSG)
    return fn(receiver, _objc.sel_registerName(selector.encode()), *args)


def _ns_window(widget: QWidget):
    view = ctypes.c_void_p(int(widget.winId()))  # NSView*
    return _send(ctypes.c_void_p, view, "window")


def _appearance(dark: bool):
    name = _CF.CFStringCreateWithCString(
        None, b"NSAppearanceNameDarkAqua" if dark else b"NSAppearanceNameAqua", _UTF8)
    try:
        return _send(ctypes.c_void_p, _objc.objc_getClass(b"NSAppearance"),
                     "appearanceNamed:", ctypes.c_void_p(name))
    finally:
        _CF.CFRelease(name)


def paint(widget: QWidget) -> None:
    """Give *widget*'s window a title bar in the theme's header color."""
    color = QApplication.palette().color(QPalette.Button)
    window = _ns_window(widget)
    if not window:
        return
    ns_color = _send(
        ctypes.c_void_p, _objc.objc_getClass(b"NSColor"),
        "colorWithSRGBRed:green:blue:alpha:",
        ctypes.c_double(color.redF()), ctypes.c_double(color.greenF()),
        ctypes.c_double(color.blueF()), ctypes.c_double(1.0))
    window = ctypes.c_void_p(window)
    _send(None, window, "setTitlebarAppearsTransparent:", ctypes.c_bool(True))
    _send(None, window, "setBackgroundColor:", ctypes.c_void_p(ns_color))
    _send(None, window, "setAppearance:",
          ctypes.c_void_p(_appearance(color.lightnessF() < 0.5)))


def _is_titled(widget) -> bool:
    """A window or dialog that has a title bar (not a popup or tooltip)."""
    return (isinstance(widget, QWidget) and widget.isWindow()
            and widget.windowType() in (Qt.Window, Qt.Dialog)
            and not widget.windowFlags() & Qt.FramelessWindowHint)


class _TitlebarFilter(QObject):
    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        kind = event.type()
        if kind == QEvent.ApplicationPaletteChange and obj is QApplication.instance():
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and _is_titled(widget):
                    _paint_safely(widget)
        elif kind in (QEvent.Show, QEvent.WindowStateChange) and _is_titled(obj):
            _paint_safely(obj)
        return False


def _paint_safely(widget) -> None:
    try:
        paint(widget)
    except Exception as exc:  # cosmetic only - never break a window
        print(f"[caelumite] title bar: {exc}", flush=True)


def install(app) -> None:
    app._caelumite_titlebar_filter = _TitlebarFilter(app)
    app.installEventFilter(app._caelumite_titlebar_filter)
