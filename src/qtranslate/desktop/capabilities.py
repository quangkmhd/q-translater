from dataclasses import dataclass, asdict
import os


@dataclass(frozen=True)
class CapabilityReport:
    platform: str = "unknown"
    shell_version: str = ""
    selection: bool = False
    clipboard: bool = False
    capture: bool = False
    popup: bool = False
    popup_backend: str = "unverified"
    status: str = "BLOCKED"
    reason: str = "NO_DESKTOP_SESSION"

    def to_dict(self):
        return asdict(self)


def collect_capabilities(env=None):
    env = os.environ if env is None else env
    session = bool(
        env.get("DBUS_SESSION_BUS_ADDRESS")
        and (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
    )
    return CapabilityReport(
        platform=env.get("XDG_SESSION_TYPE", "unknown"),
        reason="BRIDGE_NOT_VERIFIED" if session else "NO_DESKTOP_SESSION",
    )
