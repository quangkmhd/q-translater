import tempfile
import threading
import unittest
from pathlib import Path

from qtranslate.actions import Engine
from qtranslate.chat import ChatSession
from qtranslate.config.secrets import SecretStore
from qtranslate.config.settings import defaults
from qtranslate.providers.base import ProviderChunk, ProviderResponse
from qtranslate.tasks.types import TaskRequest, TaskResult
from tests.fixtures.clock import FakeClock
from tests.unit.test_import_merge import bundle


class SessionTests(unittest.TestCase):
    def test_hide_keeps_history_draft_and_active_request(self):
        s = ChatSession()
        req = s.begin("My name is Linh.")
        s.apply(TaskResult(req.id, "chat", "success", "Linh."))
        next_request = s.begin("What is my name?")
        s.draft = "Unsent follow-up"
        s.hide()
        s.show()
        self.assertEqual(s.active_id, next_request.id)
        self.assertEqual(s.draft, "Unsent follow-up")
        self.assertEqual(
            [m["content"] for m in next_request.messages],
            ["My name is Linh.", "Linh.", "What is my name?"],
        )

    def test_close_clears_and_rejects_late_reply_and_new_session_is_empty(self):
        s = ChatSession()
        first_id = s.session_id
        request = s.begin("Old secret context")
        self.assertEqual(s.close(), request.id)
        self.assertFalse(s.apply(TaskResult(request.id, "chat", "success", "Late")))
        self.assertEqual(s.history, [])
        self.assertEqual(s.turns, [])
        self.assertFalse(s.visible)
        s.show()
        new = s.begin("New session")
        self.assertNotEqual(s.session_id, first_id)
        self.assertEqual(
            list(new.messages), [{"role": "user", "content": "New session"}]
        )

    def test_failed_or_stopped_partial_reply_never_enters_model_history(self):
        s = ChatSession()
        first = s.begin("Failed turn")
        s.apply(TaskResult(first.id, "chat", "streaming", "Incomplete"))
        s.apply(TaskResult(first.id, "chat", "error", error_code="KEY_TIMEOUT"))
        second = s.begin("Another question")
        self.assertEqual(len(second.messages), 1)
        self.assertEqual(s.stop(), second.id)
        self.assertFalse(s.apply(TaskResult(second.id, "chat", "success", "Late")))
        self.assertEqual(s.history, [])

    def test_clear_starts_new_conversation_and_request_is_a_snapshot(self):
        s = ChatSession()
        r = s.begin("First")
        s.apply(TaskResult(r.id, "chat", "success", "Answer"))
        second = s.begin("Second")
        s.history[0]["content"] = "Mutated"
        self.assertEqual(second.messages[0]["content"], "First")
        s.clear()
        self.assertEqual(s.history, [])
        self.assertEqual(s.draft, "")


class ChatEngineTests(unittest.TestCase):
    def test_chat_is_one_full_context_request_and_success_does_not_require_copy(self):
        with tempfile.TemporaryDirectory() as d:
            store = SecretStore(Path(d) / "keys.json")
            store.merge(bundle())
            seen = []
            updates = []

            class Adapter:
                def run(self, payload, candidate, deadline, cancel, on_delta):
                    seen.append((payload, deadline))
                    on_delta(ProviderChunk("The answer."))
                    return ProviderResponse("The answer.", True, "stop")

            engine = Engine(store, Path(d) / "route.json", Adapter(), clock=FakeClock())
            source = "Explain this in context. " * 90
            messages = (
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
                {"role": "user", "content": source},
            )
            r = engine(
                TaskRequest("c", "chat", text=source, messages=messages),
                defaults(),
                30,
                threading.Event(),
                updates.append,
            )
            engine.close()
            self.assertEqual(r.state, "success")
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0][0]["messages"], messages)
            self.assertEqual(seen[0][0]["text"], source)
            self.assertEqual(seen[0][0]["prompt"], defaults()["prompt_chat"])
            self.assertEqual(seen[0][1], 5)
            self.assertEqual(updates[0].text, "The answer.")

    def test_fallback_retains_history_and_replaces_failed_partial(self):
        with tempfile.TemporaryDirectory() as d:
            store = SecretStore(Path(d) / "keys.json")
            store.merge(bundle())
            payloads = []
            updates = []

            class Adapter:
                def run(self, p, c, deadline, cancel, on_delta):
                    payloads.append(p)
                    if len(payloads) == 1:
                        on_delta(ProviderChunk("Wrong partial"))
                        return ProviderResponse(error_code="NETWORK_ERROR")
                    on_delta(ProviderChunk("Correct"))
                    return ProviderResponse("Correct", True, "stop")

            engine = Engine(store, Path(d) / "route.json", Adapter(), clock=FakeClock())
            messages = ({"role": "user", "content": "Question"},)
            r = engine(
                TaskRequest("c", "chat", text="Question", messages=messages),
                defaults(),
                30,
                threading.Event(),
                updates.append,
            )
            engine.close()
            self.assertEqual(r.text, "Correct")
            self.assertEqual([p["messages"] for p in payloads], [messages, messages])
            self.assertEqual(updates[-1].text, "Correct")

    def test_defaults_merge_old_shortcuts_and_concise_chat_prompt(self):
        from qtranslate.config.settings import SettingsStore
        import json

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            p.write_text(json.dumps({"shortcuts": {"rewrite": "<Alt>b"}}))
            s = SettingsStore(p).load()
            self.assertEqual(s["shortcuts"]["chat"], "<Alt>d")
            self.assertEqual(s["shortcuts"]["rewrite"], "<Alt>b")
            prompt = s["prompt_chat"].lower()
            for rule in [
                "q-translate",
                "shortest",
                "no greetings",
                "no flattery",
                "directly",
            ]:
                self.assertIn(rule, prompt)
