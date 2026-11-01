"""Cancelable HTTPS stream transport with an absolute whole-request deadline."""

import codecs
import json
import os
import selectors
import subprocess
import sys
from pathlib import Path
import time
import urllib.parse
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from qtranslate.audit.legacy import ALLOWED_HOSTS


@dataclass(frozen=True)
class HttpResult:
    status: int
    error_code: str | None = None
    retry_after: float = 60.0


def retry_delay(value, now=None):
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            return max(
                0.0,
                parsedate_to_datetime(value).timestamp()
                - (time.time() if now is None else now),
            )
        except (TypeError, ValueError, OverflowError):
            return 60.0


class StreamDecoder:
    def __init__(self, format="sse"):
        self.format = format
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.buffer = ""
        self.data = []

    def feed(self, raw):
        self.buffer += self.decoder.decode(raw)
        events = []
        if self.format in ("json", "text"):
            return events
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.rstrip("\r")
            if self.format == "ndjson":
                if line.strip():
                    events.append(json.loads(line))
            elif line.startswith("data:"):
                self.data.append(line[5:].lstrip())
            elif not line and self.data:
                text = "\n".join(self.data)
                self.data = []
                events.append("[DONE]" if text == "[DONE]" else json.loads(text))
        return events

    def finish(self):
        if self.format in ("json", "text"):
            value = self.buffer
            self.buffer = ""
            return [json.loads(value) if self.format == "json" else value]
        if self.buffer.strip() or self.data:
            raise ValueError("INCOMPLETE_FRAME")


def _quote(value):
    return (
        '"'
        + value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        + '"'
    )


def request_stream(
    url,
    headers,
    body,
    deadline,
    cancelled,
    on_event,
    format="sse",
    clock=time,
    client="curl",
):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname
        not in (
            ALLOWED_HOSTS
            | {
                "translate.googleapis.com",
                "translate.google.com",
                "edge.microsoft.com",
                "api-edge.cognitive.microsofttranslator.com",
                "api.cognitive.microsofttranslator.com",
                "www.bing.com",
            }
        )
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("UNTRUSTED_ENDPOINT")
    remaining = deadline - clock.monotonic()
    if remaining <= 0:
        return HttpResult(0, "KEY_TIMEOUT")
    if cancelled.is_set():
        return HttpResult(0, "CANCELLED")
    config = (
        "url = "
        + _quote(url)
        + "\n"
        + "".join(
            "header = " + _quote(k + ": " + v) + "\n"
            for k, v in {
                "Content-Type": "application/json",
                "Expect": "",
                **headers,
            }.items()
        )
        + (
            "data = "
            + _quote(
                body if isinstance(body, str) else json.dumps(body, ensure_ascii=True)
            )
            + "\n"
            if body is not None
            else ""
        )
    )
    command = [
        "curl",
        "--disable",
        "--config",
        "-",
        "--silent",
        "--no-buffer",
        "--proto",
        "=https",
        "--max-time",
        str(remaining),
        "--write-out",
        "%{stderr}\nQT_STATUS:%{http_code}\nQT_RETRY_AFTER:%header{retry-after}\n",
    ]
    if client == "document":
        command = [
            sys.executable,
            "-I",
            "-u",
            str(Path(__file__).with_name("document_client.py")),
        ]
        config = json.dumps(
            {"url": url, "headers": headers, "body": body, "timeout": remaining}
        )
    elif client != "curl":
        raise ValueError("UNKNOWN_HTTP_CLIENT")
    proc = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    selector = selectors.DefaultSelector()
    decoder = StreamDecoder(format)
    error = None
    status = 0
    retry_after = 60.0
    try:
        proc.stdin.write(config.encode())
        proc.stdin.close()
        selector.register(proc.stdout, selectors.EVENT_READ)
        eof = False
        while not eof:
            if cancelled.is_set():
                error = "CANCELLED"
                break
            if clock.monotonic() >= deadline:
                error = "KEY_TIMEOUT"
                break
            for key, _ in selector.select(
                min(0.05, max(0.001, deadline - clock.monotonic()))
            ):
                raw = os.read(key.fd, 16384)
                if not raw:
                    eof = True
                    break
                for event in decoder.feed(raw):
                    if cancelled.is_set() or clock.monotonic() >= deadline:
                        error = "CANCELLED" if cancelled.is_set() else "KEY_TIMEOUT"
                        break
                    on_event(event)
        if error:
            proc.kill()
        proc.wait(timeout=1)
        if not error:
            for event in decoder.finish() or []:
                if cancelled.is_set() or clock.monotonic() >= deadline:
                    error = "CANCELLED" if cancelled.is_set() else "KEY_TIMEOUT"
                    break
                on_event(event)
    except (ValueError, UnicodeError, json.JSONDecodeError):
        error = "INVALID_RESPONSE"
    except (OSError, subprocess.TimeoutExpired):
        error = "NETWORK_ERROR"
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        selector.close()
        proc.stdout.close()
        stderr = proc.stderr.read().decode(errors="replace")
        proc.stderr.close()
        for line in stderr.splitlines():
            if line.startswith("QT_RETRY_AFTER:"):
                retry_after = retry_delay(line.split(":", 1)[1])
            if line.startswith("QT_STATUS:"):
                try:
                    status = int(line.split(":")[1])
                except ValueError:
                    pass
    if proc.returncode == 28:
        error = "KEY_TIMEOUT"
    elif (
        client == "document"
        and proc.returncode
        and status == 0
        and "QT_DOCUMENT_ERROR" in stderr
        and error not in ("CANCELLED", "KEY_TIMEOUT")
    ):
        error = "NETWORK_ERROR"
    elif proc.returncode and error is None:
        error = "NETWORK_ERROR"
    if status >= 400:
        error = {
            401: "INVALID_AUTH",
            403: "PERMISSION_DENIED",
            429: "RATE_LIMITED",
            402: "QUOTA_OR_CREDIT",
            404: "MODEL_UNAVAILABLE",
        }.get(status, "PROVIDER_ERROR")
    if 300 <= status < 400:
        error = "REDIRECT_REJECTED"
    return HttpResult(status, error, retry_after)


def request_document(url, headers, body, deadline, cancelled, on_event, format="json"):
    return request_stream(
        url,
        headers,
        body,
        deadline,
        cancelled,
        on_event,
        format=format,
        client="document",
    )
