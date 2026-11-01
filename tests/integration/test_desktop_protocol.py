import tempfile, unittest, os
from pathlib import Path
from qtranslate.desktop.protocol import ProtocolGate, validate_crop_path, TextTransfer


class ProtocolTests(unittest.TestCase):
    def test_wrong_owner_or_epoch_rejected(self):
        gate = ProtocolGate()
        gate.set_owner(":1.5", "new")
        msg = {"version": 1, "epoch": "new", "action": "rewrite", "text": "Hello"}
        self.assertEqual(gate.validate(":1.5", msg)["text"], "Hello")
        for sender, epoch in [(":1.6", "new"), (":1.5", "old")]:
            with self.assertRaises(ValueError):
                gate.validate(sender, {**msg, "epoch": epoch})

    def test_crop_path_outside_cache_or_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "captures"
            root.mkdir()
            f = root / "a.png"
            f.write_bytes(b"png")
            f.chmod(0o600)
            self.assertEqual(validate_crop_path(str(f), root), str(f))
            (root / "link.png").symlink_to(f)
            with self.assertRaises(ValueError):
                validate_crop_path(str(root / "link.png"), root)
            with self.assertRaises(ValueError):
                validate_crop_path("/etc/passwd", root)

    def test_large_text_chunk_order_and_utf8(self):
        t = TextTransfer()
        self.addCleanup(t.close)
        t.begin("a", 2)
        t.append("a", 0, "Việt " * 8000)
        with self.assertRaises(ValueError):
            t.append("a", 0, "duplicate")
        t.append("a", 1, "End")
        self.assertTrue(t.finish("a").endswith("End"))
