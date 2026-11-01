import unittest, threading, time
from qtranslate.providers.http import StreamDecoder, request_stream


class StreamTests(unittest.TestCase):
    def test_document_network_failure_is_not_malformed_response(self):
        import subprocess
        from unittest.mock import patch

        real_popen = subprocess.Popen

        def child(*args, **kwargs):
            return real_popen(
                [
                    "/usr/bin/python3",
                    "-c",
                    'import sys;sys.stdin.read();sys.stderr.write("QT_DOCUMENT_ERROR\\n");sys.exit(1)',
                ],
                **kwargs,
            )

        with patch("qtranslate.providers.http.subprocess.Popen", side_effect=child):
            result = request_stream(
                "https://api.cognitive.microsofttranslator.com/translate",
                {},
                {},
                time.monotonic() + 5,
                threading.Event(),
                lambda _: None,
                format="json",
                client="document",
            )
        self.assertEqual(result.error_code, "NETWORK_ERROR")

    def test_sse_frames_split_across_reads(self):
        d = StreamDecoder("sse")
        raw = 'data: {"choices":[{"delta":{"content":"Việt"}}]}\n\ndata: [DONE]\n\n'.encode()
        events = []
        for part in [raw[:42], raw[42:44], raw[44:]]:
            events += d.feed(part)
        self.assertEqual(events[0]["choices"][0]["delta"]["content"], "Việt")
        self.assertEqual(events[1], "[DONE]")

    def test_ndjson_waits_for_complete_line(self):
        d = StreamDecoder("ndjson")
        self.assertEqual(d.feed(b'{"message":'), [])
        self.assertEqual(
            d.feed(b'{"content":"Hello"}}\n'), [{"message": {"content": "Hello"}}]
        )

    def test_untrusted_endpoint_never_receives_credentials(self):
        with self.assertRaises(ValueError):
            request_stream(
                "https://evil.example/chat",
                {"Authorization": "Bearer fake-secret"},
                {},
                time.monotonic() + 5,
                threading.Event(),
                lambda e: None,
            )

    def test_expired_deadline_does_not_launch_process(self):
        r = request_stream(
            "https://api.cloudflare.com/",
            {},
            {},
            time.monotonic() - 1,
            threading.Event(),
            lambda e: None,
        )
        self.assertEqual(r.error_code, "KEY_TIMEOUT")

    def test_retry_after_seconds_and_http_date(self):
        from qtranslate.providers.http import retry_delay

        self.assertEqual(retry_delay("120", 0), 120)
        self.assertEqual(retry_delay("Thu, 01 Jan 1970 00:02:00 GMT", 60), 60)
        self.assertEqual(retry_delay("bad", 0), 60)

    def test_stalled_stream_is_killed_at_whole_request_deadline(self):
        import subprocess
        from unittest.mock import patch

        real_popen = subprocess.Popen
        events = []

        def child(*args, **kwargs):
            return real_popen(
                [
                    "/usr/bin/python3",
                    "-u",
                    "-c",
                    'import sys,time;sys.stdin.read();print(\'data: {"text":"First"}\\n\',flush=True);time.sleep(2)',
                ],
                **kwargs,
            )

        start = time.monotonic()
        with patch("qtranslate.providers.http.subprocess.Popen", side_effect=child):
            result = request_stream(
                "https://api.cloudflare.com/",
                {},
                {},
                start + 0.12,
                threading.Event(),
                events.append,
            )
        self.assertEqual(result.error_code, "KEY_TIMEOUT")
        self.assertLess(time.monotonic() - start, 0.7)
        self.assertEqual(events, [{"text": "First"}])
