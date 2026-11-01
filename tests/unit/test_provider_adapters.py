import tempfile
import unittest
import threading
import time
from pathlib import Path
from qtranslate.providers.ai import AIAdapter
from qtranslate.providers.http import HttpResult
from qtranslate.config.secrets import SecretStore
from tests.unit.test_import_merge import bundle


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SecretStore(Path(self.tmp.name) / "keys.json")
        b = bundle()
        b["providers"][0]["models"] = ["@cf/google/gemma-4-26b-a4b-it"]
        for c in b["providers"][0]["credentials"]:
            c["verified_text_model"] = "@cf/google/gemma-4-26b-a4b-it"
        self.store.merge(b)
        self.candidate = self.store.candidates()[0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_provider_disables_thinking_and_returns_only_text(self):
        bodies = []

        def transport(url, headers, body, deadline, cancel, on_event, **kwargs):
            bodies.append(body)
            on_event({"choices": [{"delta": {"role": "assistant"}}]})
            on_event(
                {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]}
            )
            on_event({"choices": [{"delta": {}, "finish_reason": "stop"}]})
            return HttpResult(200)

        r = AIAdapter(self.store, transport).run(
            {"text": "Xin chào", "prompt": "Rewrite"},
            self.candidate,
            time.monotonic() + 5,
            threading.Event(),
        )
        self.assertEqual(r.text, "Hello")
        self.assertTrue(r.complete)
        self.assertFalse(bodies[0]["chat_template_kwargs"]["enable_thinking"])

    def test_eof_without_completion_is_not_success(self):
        def transport(u, h, b, d, c, event, **kw):
            event({"choices": [{"delta": {"content": "Part"}}]})
            return HttpResult(200)

        r = AIAdapter(self.store, transport).run(
            {"text": "x"}, self.candidate, time.monotonic() + 5, threading.Event()
        )
        self.assertFalse(r.complete)
        self.assertEqual(r.error_code, "INCOMPLETE_OUTPUT")

    def test_reasoning_is_rejected(self):
        def transport(u, h, b, d, c, event, **kw):
            event(
                {
                    "choices": [
                        {
                            "delta": {"reasoning": "hidden", "content": "Answer"},
                            "finish_reason": "stop",
                        }
                    ]
                }
            )
            return HttpResult(200)

        r = AIAdapter(self.store, transport).run(
            {"text": "x"}, self.candidate, time.monotonic() + 5, threading.Event()
        )
        self.assertFalse(r.complete)
        self.assertEqual(r.error_code, "THINKING_STILL_ENABLED")

    def test_chat_messages_are_unwrapped_and_ordered_for_every_provider(self):
        from dataclasses import replace

        messages = (
            {"role": "user", "content": "My name is Linh."},
            {"role": "assistant", "content": "Linh."},
            {"role": "user", "content": "What is my name?"},
        )
        for provider, model in [
            ("cloudflare", self.candidate.model),
            ("nvidia", "m"),
            ("ollama", "m"),
            ("openrouter", "m:free"),
            ("google", "gemini-2.5-flash"),
            ("google", "gemma-4-31b-it"),
        ]:
            with self.subTest(provider=provider, model=model):
                bodies = []

                def transport(url, headers, body, deadline, cancel, event, **kwargs):
                    bodies.append(body)
                    if provider == "google":
                        event(
                            {
                                "candidates": [
                                    {
                                        "content": {"parts": [{"text": "Linh."}]},
                                        "finishReason": "STOP",
                                    }
                                ]
                            }
                        )
                    elif provider == "ollama":
                        event(
                            {
                                "message": {"content": "Linh."},
                                "done": True,
                                "done_reason": "stop",
                            }
                        )
                    else:
                        event(
                            {
                                "choices": [
                                    {
                                        "delta": {"content": "Linh."},
                                        "finish_reason": "stop",
                                    }
                                ]
                            }
                        )
                    return HttpResult(200)

                c = replace(self.candidate, provider=provider, model=model)
                r = AIAdapter(self.store, transport).run(
                    {
                        "text": messages[-1]["content"],
                        "messages": messages,
                        "prompt": "Be concise.",
                    },
                    c,
                    time.monotonic() + 5,
                    threading.Event(),
                )
                self.assertTrue(r.complete, r.error_code)
                body = bodies[0]
                self.assertNotIn("<source_text>", str(body))
                if provider == "google":
                    self.assertEqual(
                        [m["role"] for m in body["contents"]], ["user", "model", "user"]
                    )
                    self.assertEqual(
                        body["contents"][-1]["parts"][0]["text"], "What is my name?"
                    )
                    if model.startswith("gemma"):
                        self.assertNotIn("systemInstruction", body)
                        self.assertIn(
                            "Be concise.", body["contents"][0]["parts"][0]["text"]
                        )
                else:
                    self.assertEqual(
                        body["messages"],
                        [{"role": "system", "content": "Be concise."}, *messages],
                    )
