import tempfile, unittest
from pathlib import Path
from qtranslate.ui.model import DashboardModel
from qtranslate.config.secrets import SecretStore
from qtranslate.config.settings import SettingsStore
from tests.unit.test_import_merge import bundle, KEY


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = SecretStore(root / "keys.json")
        self.store.merge(bundle())
        self.model = DashboardModel(SettingsStore(root / "settings.json"), self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_view_uses_masked_report(self):
        self.assertNotIn(KEY, str(self.model.providers("text")))

    def test_text_capability_not_vision_green(self):
        self.assertEqual(self.model.providers("vision")[0]["models"], [])

    def test_cannot_save_empty_pool(self):
        settings = self.model.settings.load()
        settings["enabled"] = {p: False for p in settings["provider_order"]}
        with self.assertRaises(ValueError):
            self.model.settings.save(settings)

    def test_provider_change_persists_for_next_snapshot(self):
        before = self.model.settings.load()
        self.model.toggle("cloudflare", False)
        self.assertTrue(before["enabled"]["cloudflare"])
        self.assertFalse(self.model.settings.load()["enabled"]["cloudflare"])

    def test_audit_new_does_not_retest_verified_keys(self):
        def forbidden(_bundle):
            raise AssertionError(
                "Already verified keys must not be audited again automatically"
            )

        report = self.model.audit_new(forbidden)
        self.assertEqual(report["credentials"], [])

    def test_audit_is_single_flight(self):
        import threading

        started = threading.Event()
        release = threading.Event()
        errors = []
        b = bundle()
        for c in b["providers"][0]["credentials"]:
            c.pop("verified_text_model")
            c["status"] = "unverified"
            c["key"] += "new"
        self.store.merge(b)

        def runner(data):
            started.set()
            release.wait(2)
            return {
                "credentials": [],
                "rankings": [],
                "status": "complete",
                "created_at": "today",
            }

        thread = threading.Thread(target=lambda: self.model.audit_new(runner))
        thread.start()
        self.assertTrue(started.wait(1))
        try:
            with self.assertRaisesRegex(ValueError, "AUDIT_RUNNING"):
                self.model.audit_new(runner)
        finally:
            release.set()
            thread.join(3)
