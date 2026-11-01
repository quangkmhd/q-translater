"""Keep utility windows out of the dock; the Shell indicator owns discovery."""

import gi

gi.require_version("GdkX11", "4.0")
from gi.repository import GdkX11  # noqa: E402 -- require the installed namespace version first.


def hide_from_dock(window):
    surface = window.get_surface()
    if not isinstance(surface, GdkX11.X11Surface):
        return False
    surface.set_skip_taskbar_hint(True)
    surface.set_skip_pager_hint(True)
    return True
