import unittest
from qtranslate.desktop.chat_window import bottom_right


class WindowPositionTests(unittest.TestCase):
    def test_hidpi_position_maps_logical_coordinates_to_x11_pixels(self):
        self.assertEqual(bottom_right((0, 0, 960, 540), 540, 350, scale=2), (796, 336))

    def test_negative_monitor_position_is_preserved(self):
        self.assertEqual(bottom_right((-1280, 0, 1280, 900), 540, 376), (-562, 502))
