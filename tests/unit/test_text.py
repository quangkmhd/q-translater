import unittest
from qtranslate.text import split_text


class TextTests(unittest.TestCase):
    def test_chunks_preserve_source_and_break_at_whitespace(self):
        source = "Tôi muốn dịch. " * 1000
        parts = split_text(source, 100)
        self.assertEqual("".join(parts), source)
        self.assertTrue(all(p.endswith((" ", "\n")) for p in parts[:-1]))

    def test_unbroken_identifier_not_cut_in_half(self):
        source = "identifier_" * 200
        self.assertEqual(split_text(source, 100), [source])
