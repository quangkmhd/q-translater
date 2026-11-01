import unittest
import json
import sqlite3
import tempfile
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch
from qtranslate.desktop import tui_selection
from qtranslate.desktop.x11_owner import new_orca_publisher
from qtranslate.desktop.tui_selection import active_terminal, CODEX_COPY


class TuiSelectionTests(unittest.TestCase):
    def test_structured_chat_without_a_terminal_uses_native_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles/test").mkdir(parents=True)
            (root / "orca-profile-index.json").write_text(
                json.dumps({"activeProfileId": "test"})
            )
            session = {
                "activeWorktreeId": "workspace",
                "activeTabId": None,
                "activeTabTypeByWorktree": {"workspace": "agent-session"},
                "activeTabIdByWorktree": {"workspace": None},
                "activeGroupIdByWorktree": {"workspace": "group"},
                "tabGroups": {
                    "workspace": [{"id": "group", "activeTabId": "chat"}]
                },
                "unifiedTabs": {
                    "workspace": [
                        {"id": "chat", "groupId": "group", "contentType": "agent-session"}
                    ]
                },
            }
            with sqlite3.connect(root / "profiles/test/profile-state.db") as db:
                db.execute(
                    "CREATE TABLE profile_state_documents (domain TEXT, payload TEXT)"
                )
                db.execute(
                    "INSERT INTO profile_state_documents VALUES (?, ?)",
                    ("workspaceSession", json.dumps(session)),
                )
            with (
                patch.dict(tui_selection.os.environ, {"ORCA_USER_DATA_PATH": tmp}),
                patch.object(tui_selection, "cli") as cli,
            ):
                self.assertEqual(tui_selection.profile(), {"agentIdentity": "native"})
                cli.assert_not_called()
                # Missing/mismatched tab metadata must still fail closed.
                session["tabGroups"]["workspace"][0]["activeTabId"] = "unknown"
                with sqlite3.connect(root / "profiles/test/profile-state.db") as db:
                    db.execute(
                        "UPDATE profile_state_documents SET payload=?",
                        (json.dumps(session),),
                    )
                with self.assertRaisesRegex(ValueError, "TUI_SOURCE_UNAVAILABLE"):
                    tui_selection.profile()

    def test_only_new_orca_publisher_process_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publisher = root / "clipboard-publishers" / ("a" * 64)
            publisher.parent.mkdir()
            shutil.copy2("/bin/sleep", publisher)
            started = time.clock_gettime(time.CLOCK_BOOTTIME)
            child = subprocess.Popen([str(publisher), "5"])
            try:
                # Popen waits for exec; this is a real executable identity/PID.
                with patch.dict(tui_selection.os.environ, {"ORCA_USER_DATA_PATH": tmp}):
                    self.assertTrue(new_orca_publisher(child.pid, started))
                    self.assertFalse(new_orca_publisher(child.pid, started + 1))
                    self.assertFalse(
                        new_orca_publisher(tui_selection.os.getpid(), started)
                    )
            finally:
                child.terminate()
                child.wait()

    def test_codex_process_is_bound_to_exact_terminal_handle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for pid, handle in [(123, "selected"), (456, "background")]:
                proc = root / str(pid)
                proc.mkdir()
                (proc / "comm").write_text("codex\n")
                (proc / "environ").write_bytes(
                    ("ORCA_TERMINAL_HANDLE=" + handle + "\0").encode()
                )
            with patch.object(tui_selection, "Path", return_value=root):
                self.assertEqual(tui_selection.codex_pid({"handle": "selected"}), 123)
                with self.assertRaisesRegex(ValueError, "AMBIGUOUS"):
                    tui_selection.codex_pid({"handle": "unknown"})

    def test_workspace_switch_during_cli_query_refuses_old_terminal(self):
        with (
            patch.object(
                tui_selection,
                "gui_source",
                side_effect=[("workspace-a", "tab-a"), ("workspace-b", "tab-b")],
            ),
            patch.object(tui_selection, "cli", return_value={}),
        ):
            with self.assertRaisesRegex(ValueError, "TUI_SOURCE_CHANGED"):
                tui_selection.profile()

    def test_profile_uses_gui_workspace_instead_of_process_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles/test").mkdir(parents=True)
            (root / "orca-profile-index.json").write_text(
                json.dumps({"activeProfileId": "test"})
            )
            db = sqlite3.connect(root / "profiles/test/profile-state.db")
            db.execute(
                "CREATE TABLE profile_state_documents (domain TEXT, payload TEXT)"
            )
            db.execute(
                "INSERT INTO profile_state_documents VALUES (?, ?)",
                (
                    "workspaceSession",
                    json.dumps(
                        {
                            "activeWorktreeId": "repo::/workspace/gui",
                            "activeTabId": "visible",
                        }
                    ),
                ),
            )
            db.commit()
            db.close()
            terminal = {"handle": "selected", "agentIdentity": "codex"}
            data = {
                "terminals": [terminal],
                "visualLayouts": [
                    {
                        "root": {
                            "type": "group",
                            "activeTabId": "visible",
                            "tabs": [
                                {
                                    "tabId": "visible",
                                    "activeLeafId": "leaf",
                                    "panes": {
                                        "type": "terminal",
                                        "leafId": "leaf",
                                        "handle": "selected",
                                    },
                                }
                            ],
                        }
                    }
                ],
            }

            def query(args):
                self.assertEqual(
                    args,
                    [
                        "terminal",
                        "list",
                        "--worktree",
                        "id:repo::/workspace/gui",
                        "--include-visual-layouts",
                    ],
                )
                return data

            with (
                patch.dict(
                    tui_selection.os.environ, {"ORCA_USER_DATA_PATH": str(root)}
                ),
                patch.object(tui_selection, "cli", side_effect=query),
            ):
                self.assertEqual(tui_selection.profile()["handle"], "selected")

    def test_visual_active_tab_wins_over_caller_agent(self):
        data = {
            "terminals": [
                {"handle": "caller", "agentIdentity": "codex"},
                {"handle": "hello", "agentIdentity": "codex"},
            ],
            "visualLayouts": [
                {
                    "root": {
                        "type": "group",
                        "activeTabId": "hello-tab",
                        "tabs": [
                            {
                                "tabId": "caller-tab",
                                "activeLeafId": "a",
                                "panes": {
                                    "type": "terminal",
                                    "handle": "caller",
                                    "leafId": "a",
                                },
                            },
                            {
                                "tabId": "hello-tab",
                                "activeLeafId": "b",
                                "panes": {
                                    "type": "terminal",
                                    "handle": "hello",
                                    "leafId": "b",
                                },
                            },
                        ],
                    }
                }
            ],
        }
        self.assertEqual(active_terminal(data)["handle"], "hello")

    def test_ambiguous_groups_do_not_guess_a_terminal(self):
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS"):
            active_terminal(
                {
                    "terminals": [],
                    "visualLayouts": [
                        {
                            "root": {
                                "type": "split",
                                "children": [{"type": "group"}, {"type": "group"}],
                            }
                        }
                    ],
                }
            )

    def test_codex_copy_protocol_never_sends_interrupt_or_enter(self):
        self.assertEqual(CODEX_COPY, "\x1b[2;5~")
        self.assertNotIn("\x03", CODEX_COPY)
        self.assertNotIn("\r", CODEX_COPY)
        self.assertNotIn("\n", CODEX_COPY)
