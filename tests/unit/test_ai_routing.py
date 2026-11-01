import tempfile, threading, unittest
from pathlib import Path
from qtranslate.actions import Engine
from qtranslate.tasks.types import TaskRequest
from qtranslate.providers.base import ProviderResponse
from qtranslate.config.secrets import SecretStore
from qtranslate.config.settings import defaults
from tests.fixtures.clock import FakeClock
from tests.unit.test_import_merge import bundle


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = SecretStore(self.root / "keys.json")
        self.store.merge(bundle())
        self.clock = FakeClock()
        self.settings = defaults()

    def tearDown(self):
        self.tmp.cleanup()

    def test_five_seconds_whole_attempt_and_no_repeat(self):
        deadlines = []

        class Adapter:
            def run(inner, payload, candidate, deadline, cancelled, on_delta=None):
                deadlines.append(deadline)
                self.clock.advance(deadline - self.clock.monotonic())
                return ProviderResponse(error_code="KEY_TIMEOUT")

        engine = Engine(
            self.store, self.root / "routing.json", Adapter(), clock=self.clock
        )
        r = engine(
            TaskRequest("a", "rewrite", text="Hello"),
            self.settings,
            30,
            threading.Event(),
            lambda e: None,
        )
        self.assertEqual(deadlines, [5, 10])
        self.assertEqual(r.state, "error")
        self.assertLessEqual(self.clock.monotonic(), 30)

    def test_last_attempt_uses_remaining_budget(self):
        deadlines = []
        self.clock.advance(28)

        class Adapter:
            def run(inner, p, c, d, e, on_delta=None):
                deadlines.append(d)
                self.clock.advance(d - self.clock.monotonic())
                return ProviderResponse(error_code="KEY_TIMEOUT")

        r = Engine(self.store, self.root / "routing.json", Adapter(), clock=self.clock)(
            TaskRequest("a", "rewrite", text="x"),
            self.settings,
            30,
            threading.Event(),
            lambda e: None,
        )
        self.assertEqual(deadlines, [30])
        self.assertEqual(r.error_code, "TASK_TIMEOUT")

    def test_success_remembers_model_pair_and_returns_ready(self):
        class Adapter:
            def run(inner, p, c, d, e, on_delta=None):
                return ProviderResponse("Simple English", True, "stop")

        engine = Engine(
            self.store, self.root / "routing.json", Adapter(), clock=self.clock
        )
        r = engine(
            TaskRequest("a", "rewrite", text="Xin chào"),
            self.settings,
            30,
            threading.Event(),
            lambda e: None,
        )
        self.assertEqual(r.state, "ready")
        self.assertTrue((self.root / "routing.json").exists())

    def test_image_requires_verified_vision(self):
        class Adapter:
            def run(*args, **kwargs):
                raise AssertionError("Text key cannot enter image pool")

        r = Engine(self.store, self.root / "routing.json", Adapter(), clock=self.clock)(
            TaskRequest("a", "image_translate", image_path="/unused.png"),
            self.settings,
            30,
            threading.Event(),
            lambda e: None,
        )
        self.assertEqual(r.error_code, "NO_VISION_PROVIDER")

    def test_selected_model_overrides_old_sticky_choice(self):
        b = bundle()
        b["providers"][0]["credentials"] = b["providers"][0]["credentials"][:1]
        b["providers"][0]["credentials"][0]["verified_text_model"] = "m2"
        b["providers"][0]["models"] = ["m2"]
        self.store.merge(b)
        seen = []

        class Adapter:
            def run(inner, p, c, d, e, on_delta=None):
                seen.append(c.model)
                return ProviderResponse("English", True, "stop")

        engine = Engine(
            self.store, self.root / "routing.json", Adapter(), clock=self.clock
        )
        request = TaskRequest("a", "rewrite", text="x")
        engine(request, self.settings, 30, threading.Event(), lambda e: None)
        self.settings["selected_models"] = {"cloudflare": "m2"}
        engine(
            TaskRequest("b", "rewrite", text="x"),
            self.settings,
            30,
            threading.Event(),
            lambda e: None,
        )
        self.assertEqual(seen, ["m1", "m2"])

    def test_shared_account_respects_retry_after(self):
        b = bundle()
        b["providers"][0]["credentials"] = b["providers"][0]["credentials"][:1]
        other = dict(b["providers"][0]["credentials"][0], key="second-token", id="new")
        b["providers"][0]["credentials"].append(other)
        store = SecretStore(self.root / "scope.json")
        store.merge(b)
        calls = []

        class Adapter:
            def run(inner, p, c, d, e, on_delta=None):
                calls.append(c.credential.id)
                return ProviderResponse(
                    error_code="RATE_LIMITED", status=429, retry_after=120
                )

        engine = Engine(store, self.root / "routing.json", Adapter(), clock=self.clock)
        for id in ["a", "b"]:
            engine(
                TaskRequest(id, "rewrite", text="Hello"),
                self.settings,
                self.clock.monotonic() + 30,
                threading.Event(),
                lambda _: None,
            )
            self.clock.advance(61)
        self.assertEqual(len(calls), 1)

    def test_attempt_deadline_stops_late_deltas(self):
        from qtranslate.providers.base import ProviderChunk

        events = []

        class Adapter:
            def run(inner, p, c, d, e, on_delta=None):
                self.clock.advance(4)
                on_delta(ProviderChunk("First"))
                self.clock.advance(2)
                on_delta(ProviderChunk("Late"))
                return ProviderResponse(error_code="KEY_TIMEOUT")

        Engine(self.store, self.root / "route.json", Adapter(), clock=self.clock)(
            TaskRequest("a", "rewrite", text="Hello"),
            self.settings,
            30,
            threading.Event(),
            events.append,
        )
        self.assertFalse(any("Late" in e.text for e in events))

    def test_long_rewrite_preserves_source_and_stream_never_rewinds(self):
        source = "".join(
            f"Part {n}: Please send the full report tomorrow.\n" for n in range(110)
        )
        events = []
        sizes = []

        class Adapter:
            def run(inner, p, c, d, e, on_delta=None):
                sizes.append(len(p["text"]))
                if len(p["text"]) > 400:
                    self.clock.advance(5)
                    return ProviderResponse(error_code="KEY_TIMEOUT")
                return ProviderResponse(p["text"].strip(), True, "stop")

        r = Engine(self.store, self.root / "routing.json", Adapter(), clock=self.clock)(
            TaskRequest("long", "rewrite", text=source),
            self.settings,
            30,
            threading.Event(),
            events.append,
        )
        self.assertEqual(r.state, "ready")
        self.assertEqual(r.text, source)
        self.assertLessEqual(max(sizes), 400)
        displayed = [e.text for e in events if e.state == "streaming"]
        self.assertTrue(displayed)
        for before, after in zip(displayed, displayed[1:]):
            self.assertTrue(after.startswith(before))

    def test_long_rewrite_has_bounded_parallel_requests(self):
        import time

        lock = threading.Lock()
        active = 0
        peak = 0

        class Adapter:
            def run(inner, p, c, d, e, on_delta=None):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                time.sleep(0.015)
                with lock:
                    active -= 1
                return ProviderResponse(p["text"].strip(), True, "stop")

        engine = Engine(self.store, self.root / "route.json", Adapter(), max_parallel=2)
        self.addCleanup(engine.close)
        r = engine(
            TaskRequest("parallel", "rewrite", text="A simple sentence. " * 200),
            self.settings,
            time.monotonic() + 30,
            threading.Event(),
            lambda _: None,
        )
        self.assertEqual(r.state, "ready")
        self.assertEqual(peak, 2)
