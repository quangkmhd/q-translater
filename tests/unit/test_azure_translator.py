import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from qtranslate.actions import Engine
from qtranslate.config.env_import import parse_import
from qtranslate.config.secrets import SecretStore
from qtranslate.config.settings import defaults
from qtranslate.providers.http import HttpResult
from qtranslate.tasks.types import TaskRequest

KEY = "azure-fixture-secret-keep-private"


def azure_bundle(key=KEY, region="global", verified=True):
    return {
        "format": "qtranslate-portable",
        "version": 1,
        "providers": [
            {
                "id": "azure_translator",
                "models": [],
                "credentials": [
                    {
                        "key": key,
                        "region": region,
                        "status": "translation_verified" if verified else "unverified",
                    }
                ],
            }
        ],
    }


class AzureStoreTests(unittest.TestCase):
    def test_region_binding_deduplication_and_verified_export(self):
        with tempfile.TemporaryDirectory() as d:
            store = SecretStore(Path(d) / "credentials.json")
            self.assertEqual(store.merge(azure_bundle()).added, 1)
            self.assertEqual(store.merge(azure_bundle()).duplicates, 1)
            self.assertEqual(store.merge(azure_bundle(region="southeastasia")).added, 1)
            store.merge(azure_bundle(key="pending-fixture", verified=False))
            self.assertEqual(len(store.translation_credentials()), 2)
            self.assertEqual(store.candidates("text"), [])
            self.assertIn(KEY, store.all_secrets())
            out = Path(d) / "portable.txt"
            store.export_verified(out)
            exported = json.loads(out.read_text())
            self.assertEqual(len(exported["providers"][0]["credentials"]), 2)
            self.assertNotIn("pending-fixture", out.read_text())
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)

    def test_env_import_multiple_keys_and_region_without_legacy_quarantine(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "azure.env"
            path.write_text(
                "AZURE_TRANSLATOR_KEY=first-fixture\nAZURE_TRANSLATOR_REGION=global\nAZURE_TRANSLATOR_KEY_2=second-fixture\nAZURE_TRANSLATOR_REGION_2=southeastasia\n"
            )
            data = parse_import(path)
            self.assertEqual(data["quarantine"], [])
            p = next(p for p in data["providers"] if p["id"] == "azure_translator")
            self.assertEqual(
                [(c["key"], c["region"], c["status"]) for c in p["credentials"]],
                [
                    ("first-fixture", "global", "unverified"),
                    ("second-fixture", "southeastasia", "unverified"),
                ],
            )

    def test_alt_c_without_key_never_calls_web_or_ai(self):
        with tempfile.TemporaryDirectory() as d:
            engine = Engine(
                SecretStore(Path(d) / "keys.json"), Path(d) / "routing.json"
            )
            try:
                with patch(
                    "qtranslate.providers.free.request_document",
                    side_effect=AssertionError("No web fallback"),
                ):
                    result = engine(
                        TaskRequest("id", "translate", text="Hello"),
                        defaults(),
                        time.monotonic() + 30,
                        threading.Event(),
                        lambda _: None,
                    )
                self.assertEqual(result.error_code, "AZURE_KEY_MISSING")
                self.assertIn("Cài đặt", result.text)
                self.assertEqual(result.provider, "azure_translator")
            finally:
                engine.close()


class AzureAdapterTests(unittest.TestCase):
    def test_mixed_source_does_not_echo_when_azure_detects_vietnamese(self):
        import urllib.parse

        source = "Today mình bận. Can we họp tomorrow?"
        expected = "Hôm nay mình bận. Ngày mai mình họp được không?"

        def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            # Mirrors the real Azure response: auto-detection chooses vi and
            # vi->vi echoes this mixed input unless the source is explicit.
            text = expected if query.get("from") == ["en"] else body[0]["Text"]
            emit(
                [
                    {
                        "detectedLanguage": {"language": "vi"},
                        "translations": [{"text": text, "to": "vi"}],
                    }
                ]
            )
            return HttpResult(200)

        with patch(
            "qtranslate.providers.azure_translator.request_document",
            side_effect=transport,
        ):
            self.assertEqual(self.run_text(source), expected)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = SecretStore(self.root / "keys.json")
        self.store.merge(azure_bundle())
        from qtranslate.providers.azure_translator import AzureTranslator

        self.client = AzureTranslator(self.store, self.root / "routing.json")

    def tearDown(self):
        self.temp.cleanup()

    def run_text(self, text="Hello", target=None):
        return self.client.translate(
            text, target, time.monotonic() + 30, threading.Event()
        )

    def test_official_endpoint_headers_body_and_english_vietnamese_directions(self):
        seen = []

        def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
            seen.append((url, headers, body, deadline))
            emit(
                [
                    {
                        "detectedLanguage": {"language": "en"},
                        "translations": [
                            {
                                "text": "Bản dịch",
                                "to": __import__(
                                    "urllib.parse", fromlist=["parse_qs"]
                                ).parse_qs(
                                    __import__("urllib.parse", fromlist=["urlsplit"])
                                    .urlsplit(url)
                                    .query
                                )["to"][0],
                            }
                        ],
                    }
                ]
            )
            return HttpResult(200)

        with patch(
            "qtranslate.providers.azure_translator.request_document",
            side_effect=transport,
        ):
            self.assertEqual(self.run_text("Hello"), "Bản dịch")
            self.run_text("Tôi cần thêm thời gian.")
            self.run_text("Today mình bận")
        self.assertIn("api.cognitive.microsofttranslator.com/translate?", seen[0][0])
        self.assertIn("api-version=3.0", seen[0][0])
        self.assertIn("to=vi", seen[0][0])
        self.assertEqual(seen[0][1]["Ocp-Apim-Subscription-Key"], KEY)
        self.assertNotIn("Ocp-Apim-Subscription-Region", seen[0][1])
        self.assertEqual(seen[0][2], [{"Text": "Hello"}])
        self.assertIn("to=en", seen[1][0])
        self.assertIn("to=vi", seen[2][0])
        self.assertNotIn(KEY, seen[0][0])

    def test_unknown_source_detection_uses_same_five_second_attempt(self):
        from tests.fixtures.clock import FakeClock
        import qtranslate.providers.azure_translator as module

        clock = FakeClock()
        seen = []

        def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
            seen.append(deadline)
            clock.advance(5)
            emit(
                [
                    {
                        "detectedLanguage": {"language": "vi"},
                        "translations": [{"text": "Kết quả", "to": "vi"}],
                    }
                ]
            )
            return HttpResult(200)

        with (
            patch.object(module, "time", clock),
            patch.object(module, "request_document", side_effect=transport),
        ):
            with self.assertRaisesRegex(RuntimeError, "KEY_TIMEOUT"):
                self.client.translate("toi muon dich", None, 30, threading.Event())
        self.assertEqual(seen, [5])

    def test_all_non_target_response_is_rejected(self):
        def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
            emit([{"translations": [{"text": "Wrong target", "to": "en"}]}])
            return HttpResult(200)

        with patch(
            "qtranslate.providers.azure_translator.request_document",
            side_effect=transport,
        ):
            with self.assertRaisesRegex(RuntimeError, "AZURE_UNAVAILABLE"):
                self.run_text("Hello", "vi")

    def test_regional_key_and_explicit_target(self):
        self.store = SecretStore(self.root / "regional.json")
        self.store.merge(azure_bundle(region="southeastasia"))
        self.client.store = self.store

        def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
            self.assertEqual(headers["Ocp-Apim-Subscription-Region"], "southeastasia")
            self.assertIn("to=en", url)
            emit([{"translations": [{"text": "Result", "to": "en"}]}])
            return HttpResult(200)

        with patch(
            "qtranslate.providers.azure_translator.request_document",
            side_effect=transport,
        ):
            self.assertEqual(self.run_text("Hello", "en"), "Result")

    def test_quota_auth_throttle_have_distinct_errors(self):
        for status, code, want in [
            (401, 401000, "AZURE_AUTH_FAILED"),
            (403, 403001, "AZURE_QUOTA_EXCEEDED"),
            (403, 403000, "AZURE_FORBIDDEN"),
            (429, 429000, "AZURE_RATE_LIMITED"),
        ]:
            with self.subTest(status=status, code=code):

                def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
                    emit({"error": {"code": code, "message": "not logged"}})
                    return HttpResult(status, "PROVIDER_ERROR", 0)

                with patch(
                    "qtranslate.providers.azure_translator.request_document",
                    side_effect=transport,
                ):
                    with self.assertRaisesRegex(RuntimeError, want):
                        self.run_text()

    def test_fallback_sticky_and_pending_key_not_sent(self):
        self.store.merge(azure_bundle(key="second-verified"))
        self.store.merge(azure_bundle(key="pending-fixture", verified=False))
        seen = []

        def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
            key = headers["Ocp-Apim-Subscription-Key"]
            seen.append(key)
            if key == KEY:
                emit({"error": {"code": 401000}})
                return HttpResult(401, "INVALID_AUTH")
            self.assertEqual(key, "second-verified")
            emit([{"translations": [{"text": "Result", "to": "vi"}]}])
            return HttpResult(200)

        with patch(
            "qtranslate.providers.azure_translator.request_document",
            side_effect=transport,
        ):
            self.run_text()
            self.run_text()
        self.assertEqual(seen, [KEY, "second-verified", "second-verified"])
        state = json.loads((self.root / "routing.json").read_text())
        self.assertEqual(
            state["last_success"]["translation"]["provider"], "azure_translator"
        )

    def test_long_unbroken_input_is_complete_and_each_request_bounded(self):
        source = "a" * 100001
        sent = []

        def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
            part = body[0]["Text"]
            sent.append(part)
            self.assertLessEqual(len(part), 50000)
            emit([{"translations": [{"text": part, "to": "vi"}]}])
            return HttpResult(200)

        with patch(
            "qtranslate.providers.azure_translator.request_document",
            side_effect=transport,
        ):
            self.assertEqual(self.run_text(source, "vi"), source)
        self.assertEqual("".join(sent), source)

    def test_failed_key_is_not_retried_for_every_long_text_chunk(self):
        from tests.fixtures.clock import FakeClock
        import qtranslate.providers.azure_translator as module

        clock = FakeClock()
        seen = []
        self.store.merge(azure_bundle(key="second-verified"))

        def transport(url, headers, body, deadline, cancelled, emit, **kwargs):
            key = headers["Ocp-Apim-Subscription-Key"]
            seen.append(key)
            if key == KEY:
                clock.advance(5)
                return HttpResult(0, "KEY_TIMEOUT")
            part = body[0]["Text"]
            emit([{"translations": [{"text": part, "to": "vi"}]}])
            return HttpResult(200)

        source = "a" * 270001
        with (
            patch.object(module, "time", clock),
            patch.object(module, "request_document", side_effect=transport),
        ):
            text = self.client.translate(source, "vi", 30, threading.Event())
        self.assertEqual(text, source)
        self.assertEqual(seen.count(KEY), 1)
        self.assertEqual(clock.monotonic(), 5)

    def test_cancel_and_expired_deadline_never_send(self):
        cancel = threading.Event()
        cancel.set()
        with patch(
            "qtranslate.providers.azure_translator.request_document",
            side_effect=AssertionError("No request"),
        ):
            with self.assertRaisesRegex(RuntimeError, "CANCELLED"):
                self.client.translate("Hello", None, time.monotonic() + 30, cancel)
            with self.assertRaisesRegex(RuntimeError, "TASK_TIMEOUT"):
                self.client.translate(
                    "Hello", None, time.monotonic() - 1, threading.Event()
                )


class AzureDashboardTests(unittest.TestCase):
    def test_save_verifies_then_persists_masked_status_and_failed_save_keeps_keys(self):
        from qtranslate.ui.model import DashboardModel
        from qtranslate.config.settings import SettingsStore

        with tempfile.TemporaryDirectory() as d:
            model = DashboardModel(
                SettingsStore(Path(d) / "settings.json"),
                SecretStore(Path(d) / "keys.json"),
            )

            def good(key, region):
                self.assertEqual((key, region), (KEY, "global"))

            model.save_translator(KEY, "global", verifier=good)
            status = model.translator_status()
            self.assertEqual(status["verified"], 1)
            self.assertNotIn(KEY, str(status))
            before = model.store.path.read_bytes()

            def bad(*args):
                raise RuntimeError("AZURE_AUTH_FAILED")

            with self.assertRaisesRegex(RuntimeError, "AZURE_AUTH_FAILED"):
                model.save_translator("wrong-key", "global", verifier=bad)
            self.assertEqual(model.store.path.read_bytes(), before)

    def test_pending_import_verification_and_llm_audit_are_separate(self):
        from qtranslate.ui.model import DashboardModel
        from qtranslate.config.settings import SettingsStore

        with tempfile.TemporaryDirectory() as d:
            store = SecretStore(Path(d) / "keys.json")
            store.merge(azure_bundle(verified=False))
            model = DashboardModel(SettingsStore(Path(d) / "settings.json"), store)

            def no_llm(data):
                raise AssertionError("Translator must not go through the LLM audit")

            model.audit_new(no_llm)
            self.assertEqual(model.translator_status()["pending"], 1)
            report = model.verify_translators(verifier=lambda key, region: None)
            self.assertEqual(report["verified"], 1)
            self.assertEqual(model.translator_status()["pending"], 0)
