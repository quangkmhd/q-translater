"""Place only our own X11/XWayland popup; never send input to other apps."""

import ctypes as C


def bottom_right(geometry, width, height, margin=22, scale=1):
    x, y, w, h = geometry
    return (x + max(margin, w - width - margin)) * scale, (
        y + max(32, h - height - margin)
    ) * scale


def place_chat(window, width=None, height=None):
    try:
        from gi.repository import GdkX11

        surface = window.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return False
        monitor = surface.get_display().get_monitor_at_surface(surface)
        if not monitor:
            return False
        rect = monitor.get_geometry()
        x, y = bottom_right(
            (rect.x, rect.y, rect.width, rect.height),
            width if width is not None else surface.get_width(),
            height if height is not None else surface.get_height(),
            scale=surface.get_scale_factor(),
        )
        lib = C.CDLL("libX11.so.6")
        lib.XOpenDisplay.argtypes = [C.c_char_p]
        lib.XOpenDisplay.restype = C.c_void_p
        lib.XMoveWindow.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int]
        lib.XFlush.argtypes = [C.c_void_p]
        lib.XCloseDisplay.argtypes = [C.c_void_p]
        display = lib.XOpenDisplay(None)
        if not display:
            return False
        try:
            lib.XMoveWindow(display, surface.get_xid(), x, y)
            lib.XFlush(display)
        finally:
            lib.XCloseDisplay(display)
        return True
    except (ImportError, OSError, AttributeError):
        return False
