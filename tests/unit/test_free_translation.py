import unittest
from qtranslate.providers.free import direction, join_google
from qtranslate.providers.http import StreamDecoder


class FreeTests(unittest.TestCase):
    def test_vietnamese_prose_with_software_terms_translates_to_english(self):
        self.assertEqual(
            direction("Key dùng được, region Global. Tôi đã lưu vào app."), "en"
        )
        self.assertEqual(
            direction(
                "Đã gộp key Azure cùng model AI vào file import của Q Translate."
            ),
            "en",
        )
        self.assertEqual(
            direction("Tôi muốn dùng Alt+C trong terminal trên Ubuntu Wayland."), "en"
        )
        self.assertEqual(
            direction("Tôi muốn đổi setting trong dashboard và bật streaming."), "en"
        )
        self.assertEqual(direction("Chỉnh prompt và fallback giúp tôi."), "en")

    def test_join_all_google_segments(self):
        self.assertEqual(
            join_google([[["Xin ", "Hello "], ["chào", "there"]], None, "en"]),
            "Xin chào",
        )

    def test_english_vietnamese_mixed_direction(self):
        self.assertEqual(direction("Hello, how are you?"), "vi")
        self.assertEqual(direction("Tôi muốn dịch"), "en")
        self.assertEqual(direction("Today mình bận"), "vi")

    def test_unaccented_not_assumed_english(self):
        self.assertEqual(direction("toi muon dich"), "auto")

    def test_plain_json_is_parsed_once_complete(self):
        d = StreamDecoder("json")
        self.assertEqual(d.feed(b'{"ok":'), [])
        self.assertEqual(d.feed(b"true}"), [])
        self.assertEqual(d.finish(), [{"ok": True}])

    def test_bing_page_parameters_are_parsed_as_data(self):
        from qtranslate.providers.free import parse_bing_page

        html = 'IG:"ABC", <div id="rich_tta" data-iid="translator.1"></div><script>var params_AbusePreventionHelper = [123,"TOKEN",3600000];</script>'
        self.assertEqual(
            parse_bing_page(html),
            {
                "ig": "ABC",
                "iid": "translator.1",
                "key": 123,
                "token": "TOKEN",
                "ttl": 3600,
            },
        )

    def test_plain_text_token_and_form_requests_supported(self):
        d = StreamDecoder("text")
        d.feed(b"opaque-token")
        self.assertEqual(d.finish(), ["opaque-token"])

    def test_chunk_separators_survive_stripped_provider_outputs(self):
        import threading, time
        from unittest.mock import patch
        from qtranslate.providers.free import FreeTranslator

        for sep in [" ", "\n\n", " \n"]:
            translator = FreeTranslator()
            translator._request = lambda *args, **kwargs: [
                [["Translated", None]],
                None,
                "en",
            ]
            with patch(
                "qtranslate.providers.free.split_text",
                return_value=["First" + sep, "Second"],
            ):
                text = translator.translate(
                    "First" + sep + "Second",
                    "vi",
                    time.monotonic() + 30,
                    threading.Event(),
                )
            self.assertEqual(text, "Translated" + sep + "Translated")

    def test_mixed_dictionary_words_and_plain_vietnamese(self):
        self.assertEqual(direction("Tôi cần submit report."), "vi")
        self.assertEqual(direction("Chúng tôi gặp nhau vào ngày mai."), "en")

    def test_explicit_direction_overrides_detection(self):
        import threading, time, urllib.parse
        from qtranslate.providers.free import FreeTranslator

        translator = FreeTranslator()
        seen = []

        def fetch(url, *args, **kwargs):
            seen.append(
                urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["tl"][0]
            )
            return [[["Result", None]], None, "vi"]

        translator._request = fetch
        translator.translate(
            "Tôi cần submit report.", "en", time.monotonic() + 30, threading.Event()
        )
        self.assertEqual(seen, ["en"])
