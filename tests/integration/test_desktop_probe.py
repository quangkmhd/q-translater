import unittest
from qtranslate.desktop.capabilities import collect_capabilities
from qtranslate.desktop.protocol import validate_message


class DesktopProbeTests(unittest.TestCase):
    def test_missing_session_is_blocked(self):
        report = collect_capabilities({})
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.selection)
        self.assertFalse(report.capture)

    def test_source_context_rejects_stale_epoch(self):
        with self.assertRaises(ValueError):
            validate_message(
                {"version": 1, "action": "rewrite", "epoch": "old", "text": "Hello"},
                epoch="new",
            )

    def test_protocol_rejects_unknown_version(self):
        with self.assertRaises(ValueError):
            validate_message(
                {"version": 2, "action": "rewrite", "epoch": "new", "text": "Hello"},
                epoch="new",
            )

    def test_valid_source_preserves_unicode(self):
        msg = {
            "version": 1,
            "action": "rewrite",
            "epoch": "new",
            "text": "Tôi muốn dịch",
        }
        self.assertEqual(validate_message(msg, epoch="new")["text"], "Tôi muốn dịch")
