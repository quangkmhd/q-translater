import os, tempfile, unittest
from pathlib import Path
from qtranslate.install import set_autostart, package_files


class PackageTests(unittest.TestCase):
    def test_autostart_enable_disable_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            path = set_autostart(True, Path(d))
            set_autostart(True, Path(d))
            self.assertTrue(path.exists())
            self.assertIn("Exec=qtranslate serve", path.read_text())
            set_autostart(False, Path(d))
            self.assertFalse(path.exists())

    def test_package_excludes_secrets_and_private_files(self):
        root = Path(__file__).resolve().parents[2]
        files = package_files(root)
        self.assertTrue(any(p.name == "extension.js" for p in files))
        self.assertFalse(
            any(
                p.name == ".env"
                or ".secrets" in p.parts
                or "exports" in p.parts
                or "reference" in p.parts
                for p in files
            )
        )

    def test_setup_enables_autostart_once_and_preserves_disabled_preference(self):
        from qtranslate.install import finish_setup
        from qtranslate.config.settings import SettingsStore

        with tempfile.TemporaryDirectory() as d:
            settings = SettingsStore(Path(d) / "q-translate/settings.json")
            finish_setup(settings, config_home=d)
            entry = Path(d) / "autostart/org.qtranslate.App.desktop"
            self.assertTrue(entry.exists())
            self.assertTrue(settings.load()["setup_complete"])
            value = settings.load()
            value["autostart"] = False
            settings.save(value)
            set_autostart(False, d)
            finish_setup(settings, config_home=d)
            self.assertFalse(entry.exists())

    def test_extension_candidate_is_loadable_on_both_target_shell_versions(self):
        import json

        root = Path(__file__).resolve().parents[2]
        metadata = json.loads(
            (root / "extension/qtranslate@local/metadata.json").read_text()
        )
        self.assertTrue({"46", "50"}.issubset(set(metadata["shell-version"])))
