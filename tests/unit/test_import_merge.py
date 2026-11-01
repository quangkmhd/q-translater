import json, tempfile, unittest, os
from pathlib import Path
from qtranslate.config.secrets import SecretStore
from qtranslate.config.settings import SettingsStore
from qtranslate.logging import RuntimeLog
from tests.fixtures.clock import FakeClock

KEY = "fixture-secret-private-abcdef123456789"


def bundle():
    return {
        "format": "qtranslate-portable",
        "version": 1,
        "routing": {"provider_order": ["cloudflare"]},
        "providers": [
            {
                "id": "cloudflare",
                "models": ["m1"],
                "credentials": [
                    {
                        "id": "one",
                        "key": KEY,
                        "account_id": "account-a",
                        "status": "text_verified",
                        "verified_text_model": "m1",
                        "thinking_disabled": True,
                    },
                    {
                        "id": "two",
                        "key": KEY,
                        "account_id": "account-b",
                        "status": "text_verified",
                        "verified_text_model": "m1",
                        "thinking_disabled": True,
                    },
                ],
            }
        ],
        "quarantine": [],
    }


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = SecretStore(self.root / "private" / "credentials.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_twice_is_idempotent_and_preserves_account_binding(self):
        self.assertEqual(self.store.merge(bundle()).added, 2)
        self.assertEqual(self.store.merge(bundle()).added, 0)
        self.assertEqual(len(self.store.candidates("text")), 2)

    def test_merge_keeps_existing_keys_and_models(self):
        self.store.merge(bundle())
        b = bundle()
        b["providers"][0]["credentials"] = b["providers"][0]["credentials"][:1]
        b["providers"][0]["credentials"][0]["verified_text_model"] = "m2"
        b["providers"][0]["models"] = ["m2"]
        self.store.merge(b)
        self.assertEqual(len(self.store.candidates("text")), 3)

    def test_secrets_private_and_redacted(self):
        report = self.store.merge(bundle())
        self.assertNotIn(KEY, repr(report))
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.path.parent.stat().st_mode & 0o777, 0o700)

    def test_failed_import_does_not_replace_store(self):
        self.store.merge(bundle())
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.merge({"format": "invalid"})
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_unverified_pair_not_candidate(self):
        b = bundle()
        b["providers"][0]["credentials"][0]["thinking_disabled"] = False
        self.store.merge(b)
        self.assertEqual(len(self.store.candidates("text")), 1)

    def test_settings_rejects_empty_pool(self):
        s = SettingsStore(self.root / "settings.json")
        settings = s.load()
        settings["provider_order"] = []
        with self.assertRaises(ValueError):
            s.save(settings)

    def test_log_clears_at_24h_and_redacts(self):
        clock = FakeClock()
        log = RuntimeLog(self.root / "state" / "q.log", lambda: [KEY], clock)
        log.record({"input": KEY, "output": "English"})
        self.assertNotIn(KEY, log.path.read_text())
        clock.advance(86400)
        log.maintain()
        self.assertEqual(log.path.read_text(), "")
        log.record({"input": "new"})
        clock.advance(86400)
        again = RuntimeLog(log.path, lambda: [KEY], clock)
        self.assertEqual(again.path.read_text(), "")

    def test_auxiliary_verification_upgrades_existing_identity(self):
        b = {
            "format": "qtranslate-portable",
            "version": 1,
            "providers": [
                {
                    "id": "tavily",
                    "models": [],
                    "credentials": [{"id": "one", "key": KEY, "status": "unverified"}],
                }
            ],
            "quarantine": [],
        }
        self.store.merge(b)
        b["providers"][0]["credentials"][0].update(
            status="capability_verified", verified_at="today", median_seconds=0.1
        )
        self.store.merge(b)
        out = self.root / "out.txt"
        self.store.export_verified(out)
        self.assertEqual(
            json.loads(out.read_text())["providers"][0]["credentials"][0]["status"],
            "capability_verified",
        )
