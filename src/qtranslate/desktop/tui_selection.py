"""Orca/Codex selection bridge. Copy uses Ctrl+Insert, never Ctrl+C or Enter."""

import collections
from contextlib import closing
import json
import os
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from gi.repository import GLib

CODEX_COPY = "\x1b[2;5~"


def active_terminal(data):
    groups = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "group":
            groups.append(node)
        else:
            for key, value in node.items():
                if isinstance(value, dict):
                    walk(value)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)

    for layout in data.get("visualLayouts", []):
        walk(layout.get("root", {}))
    if len(groups) != 1:
        raise ValueError("TUI_SOURCE_AMBIGUOUS")
    group = groups[0]
    tab = next(
        (
            t
            for t in group.get("tabs", [])
            if t.get("tabId") == group.get("activeTabId")
        ),
        None,
    )
    if not tab:
        raise ValueError("TUI_SOURCE_AMBIGUOUS")
    leaves = []

    def leaf(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "terminal" and node.get("leafId") == tab.get(
            "activeLeafId"
        ):
            leaves.append(node)
        for value in node.values():
            if isinstance(value, dict):
                leaf(value)
            elif isinstance(value, list):
                for child in value:
                    leaf(child)

    leaf(tab.get("panes", {}))
    if len(leaves) != 1:
        raise ValueError("TUI_SOURCE_AMBIGUOUS")
    return next(
        (
            t
            for t in data.get("terminals", [])
            if t.get("handle") == leaves[0]["handle"]
        ),
        leaves[0],
    )


def cli(args):
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "ORCA_TERMINAL_HANDLE",
            "ORCA_PANE_KEY",
            "ORCA_WORKTREE_ID",
            "ORCA_WORKSPACE_ID",
        )
    }
    binary = str(Path.home() / ".local/bin/orca-ide")
    result = subprocess.run(
        [binary, *args, "--json"],
        cwd=Path.home(),
        env=env,
        capture_output=True,
        text=True,
        timeout=2,
    )
    value = json.loads(result.stdout)
    if result.returncode or not value.get("ok"):
        raise ValueError("TUI_SOURCE_UNAVAILABLE")
    return value["result"]


def gui_source():
    """Read only current UI identity; CLI `active` resolves cwd, not the GUI.

    This is Orca's version-specific persisted metadata, opened read-only. Refuse
    unknown schemas/profiles rather than guess the most recent workspace.
    """
    root = Path(os.environ.get("ORCA_USER_DATA_PATH", Path.home() / ".config/orca"))
    index = json.loads((root / "orca-profile-index.json").read_text())
    profile_id = index["activeProfileId"]
    if not isinstance(profile_id, str) or Path(profile_id).name != profile_id:
        raise ValueError("TUI_SOURCE_UNAVAILABLE")
    path = root / "profiles" / profile_id / "profile-state.db"
    with closing(
        sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.3)
    ) as db:
        row = db.execute(
            "SELECT payload "
            "FROM profile_state_documents WHERE domain='workspaceSession'"
        ).fetchone()
    if not row:
        raise ValueError("TUI_SOURCE_UNAVAILABLE")
    session = json.loads(row[0])
    workspace = session.get("activeWorktreeId")
    if not isinstance(workspace, str) or not workspace:
        raise ValueError("TUI_SOURCE_UNAVAILABLE")
    if session.get("activeTabTypeByWorktree", {}).get(workspace) == "agent-session":
        tab = session.get("activeTabIdByWorktree", {}).get(workspace)
        group_id = session.get("activeGroupIdByWorktree", {}).get(workspace)
        if group_id is not None:
            groups = [
                group
                for group in session.get("tabGroups", {}).get(workspace, [])
                if group.get("id") == group_id
            ]
            if len(groups) != 1:
                raise ValueError("TUI_SOURCE_UNAVAILABLE")
            # Orca's legacy per-worktree tab may be null in a structured chat;
            # its focused group's active tab remains the current UI identity.
            tab = groups[0].get("activeTabId")
        tabs = session.get("unifiedTabs", {}).get(workspace, [])
        if not isinstance(tab, str) or not any(
            item.get("id") == tab and item.get("contentType") == "agent-session"
            and (group_id is None or item.get("groupId") == group_id)
            for item in tabs
        ):
            raise ValueError("TUI_SOURCE_UNAVAILABLE")
        # Structured chats are native Electron text, with no terminal/PTY.
        # None explicitly routes them through the Shell's PRIMARY reader.
        return workspace, None
    tab = session.get("activeTabId")
    if not isinstance(tab, str) or not tab:
        raise ValueError("TUI_SOURCE_UNAVAILABLE")
    return workspace, tab


def profile():
    workspace, tab = gui_source()
    if tab is None:
        return {"agentIdentity": "native"}
    data = cli(
        [
            "terminal",
            "list",
            "--worktree",
            "id:" + workspace,
            "--include-visual-layouts",
        ]
    )
    # Bind the live layout to the global GUI tab, and check it did not change
    # while the CLI was reading it. All background tabs also have active panes.
    if gui_source() != (workspace, tab):
        raise ValueError("TUI_SOURCE_CHANGED")
    layouts = data.get("visualLayouts", [])

    def has_tab(node):
        if isinstance(node, dict):
            if node.get("type") == "group" and node.get("activeTabId") == tab:
                return True
            return any(has_tab(value) for value in node.values())
        if isinstance(node, list):
            return any(has_tab(value) for value in node)
        return False

    if not any(has_tab(layout.get("root", {})) for layout in layouts):
        raise ValueError("TUI_SOURCE_AMBIGUOUS")
    return active_terminal(data)


def codex_pid(terminal):
    """Bind a local Codex process to this exact Orca PTY, not just its label."""
    if terminal.get("executionHostId") not in (None, "local"):
        raise ValueError("TUI_SOURCE_UNAVAILABLE")
    expected = ("ORCA_TERMINAL_HANDLE=" + terminal["handle"]).encode()
    matches = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (
                proc.stat().st_uid != os.getuid()
                or (proc / "comm").read_text().strip() != "codex"
            ):
                continue
            if expected in (proc / "environ").read_bytes().split(b"\0"):
                matches.append(int(proc.name))
        except (OSError, UnicodeError):
            continue
    if len(matches) != 1:
        raise ValueError("TUI_SOURCE_AMBIGUOUS")
    return matches[0]


class TuiSelectionReader:
    def __init__(self, log=None):
        self.log = log
        self.pending = collections.OrderedDict()
        self.active = None
        self.broker = None
        self.closed = False

    def read(self, request, done):
        action = request["action"]
        if self.active and self.active["action"] == action:
            self.active["cancel"].set()
        previous = self.pending.pop(action, None)
        if previous:
            previous["done"]({"error": "CANCELLED"})
        self.pending[action] = {
            "action": action,
            "done": done,
            "cancel": threading.Event(),
            "at": time.monotonic(),
            "id": request.get("id"),
        }
        self._dispatch()

    def _dispatch(self):
        if self.closed or self.active or not self.pending:
            return
        _, job = self.pending.popitem(last=False)
        self.active = job

        def work():
            try:
                result = profile()
                if result.get("agentIdentity") == "codex":
                    result = {**result, "source_pid": codex_pid(result)}
                error = None
            except Exception:
                result = None
                error = "TUI_SOURCE_UNAVAILABLE"
            GLib.idle_add(self._profile_done, job, result, error)

        threading.Thread(target=work, daemon=True).start()

    def _complete(self, job, result):
        if self.active is not job:
            return GLib.SOURCE_REMOVE
        if self.log:
            self.log.record(
                {
                    "action": "selection",
                    "method": "orca-codex",
                    "error": result.get("error"),
                    "source_chars": len(result.get("text", "")),
                    "elapsed_seconds": round(time.monotonic() - job["at"], 4),
                }
            )
        job["done"]({"error": "CANCELLED"} if job["cancel"].is_set() else result)
        self.active = None
        self._dispatch()
        return GLib.SOURCE_REMOVE

    def _profile_done(self, job, terminal, error):
        if self.closed or job["cancel"].is_set():
            return self._complete(job, {"error": "CANCELLED"})
        if error:
            return self._complete(job, {"error": error})
        agent = terminal.get("agentIdentity")
        if agent != "codex":
            return self._complete(job, {"native": True})
        # Composer selections have no transcript "copy / esc clear" footer.
        # Ctrl+Insert copies either selection without editing/submitting a draft;
        # only a fresh, attributed clipboard claim below proves a selection.
        try:
            if self.broker is None:
                from .clipboard import ClipboardBroker

                self.broker = ClipboardBroker()
        except Exception:
            return self._complete(job, {"error": "CLIPBOARD_UNAVAILABLE"})

        def saved(token, error):
            if error:
                self._complete(job, {"error": error})
                return
            if job["cancel"].is_set():
                self.broker.discard(token)
                self._complete(job, {"error": "CANCELLED"})
                return

            def copy():
                try:
                    current = profile()
                    if (
                        current.get("handle") != terminal.get("handle")
                        or current.get("agentIdentity") != "codex"
                    ):
                        raise ValueError("TUI_SOURCE_CHANGED")
                    if job["cancel"].is_set():
                        raise ValueError("CANCELLED")
                    original = self.broker.saved.get(token)
                    if not original or self.broker.serial != original["serial"]:
                        raise ValueError("CLIPBOARD_CHANGED")
                    job["copy_at"] = time.clock_gettime(time.CLOCK_BOOTTIME)
                    cli(
                        [
                            "terminal",
                            "send",
                            "--terminal",
                            terminal["handle"],
                            "--text",
                            CODEX_COPY,
                        ]
                    )
                    error = None
                except Exception:
                    error = "TUI_SOURCE_CHANGED"
                GLib.idle_add(copied, error)

            def copied(error):
                # A lost CLI acknowledgement does not mean no copy occurred.
                # Still read/restore the attributed clipboard before reporting
                # failure. Never restore over a different process's clipboard.
                end = time.monotonic() + 0.8

                def wait_copy():
                    original = self.broker.saved.get(token)
                    if not original:
                        self._complete(job, {"error": "CLIPBOARD_UNAVAILABLE"})
                        return GLib.SOURCE_REMOVE
                    if (
                        self.broker.serial > original["serial"]
                        and self.broker.clip.get_formats().get_mime_types()
                    ):
                        self.broker.finish(
                            token,
                            lambda text, error: self._complete(
                                job, {"error": error} if error else {"text": text}
                            ),
                            expected_pid=terminal["source_pid"],
                            publisher_since=job.get("copy_at"),
                        )
                        return GLib.SOURCE_REMOVE
                    if time.monotonic() >= end:
                        self.broker.discard(token)
                        self._complete(job, {"error": error or "NO_SELECTION"})
                        return GLib.SOURCE_REMOVE
                    return GLib.SOURCE_CONTINUE

                GLib.timeout_add(20, wait_copy)
                return GLib.SOURCE_REMOVE

            threading.Thread(target=copy, daemon=True).start()

        self.broker.snapshot(saved)
        return GLib.SOURCE_REMOVE

    def cancel(self, id):
        if self.active and self.active.get("id") == id:
            self.active["cancel"].set()
            return True
        for action, job in list(self.pending.items()):
            if job.get("id") == id:
                self.pending.pop(action)
                job["done"]({"error": "CANCELLED"})
                return True
        return False

    def close(self):
        self.closed = True
        if self.active:
            self.active["cancel"].set()
        for job in self.pending.values():
            job["done"]({"error": "CANCELLED"})
        self.pending.clear()
