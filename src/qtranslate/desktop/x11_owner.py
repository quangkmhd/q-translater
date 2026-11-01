"""Local X11 selection attribution via the X-Resource 1.2 client PID API."""

import ctypes as C
import os
import re
import time
from pathlib import Path


def new_orca_publisher(pid, since):
    """Orca forwards OSC52 through a fresh local X11 clipboard publisher.

    Require an owned executable in Orca's exact publisher directory, created
    after this copy was sent. Existing publishers and other applications fail.
    """
    try:
        proc = Path("/proc") / str(pid)
        if proc.stat().st_uid != os.getuid():
            return False
        exe = (proc / "exe").resolve(strict=True)
        root = Path(os.environ.get("ORCA_USER_DATA_PATH", Path.home() / ".config/orca"))
        if exe.parent != (root / "clipboard-publishers").resolve() or not re.fullmatch(
            r"[0-9a-f]{64}", exe.name
        ):
            return False
        if exe.stat().st_uid != os.getuid():
            return False
        # stat field 22, with the parenthesized process name handled separately.
        fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        hz = os.sysconf("SC_CLK_TCK")
        created = int(fields[19]) / hz
        return since - 1 / hz <= created <= time.clock_gettime(time.CLOCK_BOOTTIME)
    except (OSError, ValueError, IndexError):
        return False


class Spec(C.Structure):
    _fields_ = [("client", C.c_ulong), ("mask", C.c_uint)]


class Value(C.Structure):
    _fields_ = [("spec", Spec), ("length", C.c_long), ("value", C.c_void_p)]


def clipboard_owner(with_pid=False):
    x = C.CDLL("libX11.so.6")
    x.XOpenDisplay.argtypes = [C.c_char_p]
    x.XOpenDisplay.restype = C.c_void_p
    x.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
    x.XInternAtom.restype = C.c_ulong
    x.XGetSelectionOwner.argtypes = [C.c_void_p, C.c_ulong]
    x.XGetSelectionOwner.restype = C.c_ulong
    x.XCloseDisplay.argtypes = [C.c_void_p]
    display = x.XOpenDisplay(None)
    if not display:
        raise ValueError("CLIPBOARD_UNAVAILABLE")
    try:
        owner = x.XGetSelectionOwner(display, x.XInternAtom(display, b"CLIPBOARD", 0))
        if not with_pid or not owner:
            return owner, None
        try:
            res = C.CDLL("libXRes.so.1")
        except OSError:
            # User-local development install; packaged builds depend on libxres1.
            res = C.CDLL(str(Path.home() / ".local/lib/libXRes.so.1"))
        res.XResQueryExtension.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_int),
            C.POINTER(C.c_int),
        ]
        res.XResQueryVersion.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_int),
            C.POINTER(C.c_int),
        ]
        major, minor = C.c_int(), C.c_int()
        if not res.XResQueryExtension(display, C.byref(major), C.byref(minor)):
            raise ValueError("CLIPBOARD_UNAVAILABLE")
        if not res.XResQueryVersion(display, C.byref(major), C.byref(minor)) or (
            major.value,
            minor.value,
        ) < (1, 2):
            raise ValueError("CLIPBOARD_UNAVAILABLE")
        res.XResQueryClientIds.argtypes = [
            C.c_void_p,
            C.c_long,
            C.POINTER(Spec),
            C.POINTER(C.c_long),
            C.POINTER(C.POINTER(Value)),
        ]
        res.XResGetClientPid.argtypes = [C.POINTER(Value)]
        res.XResGetClientPid.restype = C.c_int
        res.XResClientIdsDestroy.argtypes = [C.c_long, C.POINTER(Value)]
        count, values = C.c_long(), C.POINTER(Value)()
        # Xlib Success is zero, unlike XResQueryExtension/Version booleans.
        if (
            res.XResQueryClientIds(
                display, 1, C.byref(Spec(owner, 2)), C.byref(count), C.byref(values)
            )
            != 0
        ):
            raise ValueError("CLIPBOARD_UNAVAILABLE")
        try:
            pids = [
                res.XResGetClientPid(C.byref(values[i])) for i in range(count.value)
            ]
            pid = next((pid for pid in pids if pid > 0), None)
            return owner, pid
        finally:
            res.XResClientIdsDestroy(count, values)
    finally:
        x.XCloseDisplay(display)
