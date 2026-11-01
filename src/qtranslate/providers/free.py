"""Google/Bing web adapters; never call an AI model."""

import re
import time
import urllib.parse
import json
from functools import lru_cache
from pathlib import Path
from .http import request_document
from qtranslate.text import split_text

VI = re.compile("[À-ỹĐđ]")
EN_WORDS = re.compile(
    r"\b(today|hello|can|we|the|please|this|with|how|are|you)\b", re.I
)
TECHNICAL_TERMS = set(
    "ai api app azure bing button chrome cli clipboard cloudflare code codex copy ctrl dashboard desktop endpoint enter export file folder global gnome google gtk gui html http https import key keys linux microsoft model models nmt nvidia ocr ollama openrouter paste popup provider providers python region sdk setup shift terminal text timeout token translate translator ui ubuntu url wayland windows x11 xorg alt".split()
)


@lru_cache(maxsize=1)
def english_words():
    # System dictionary is managed by Ubuntu's hunspell-en-us package.
    try:
        return {
            line.split("/")[0].strip().lower()
            for line in Path("/usr/share/hunspell/en_US.dic")
            .read_text()
            .splitlines()[1:]
        }
    except OSError:
        return set(EN_WORDS.pattern.split("|")[1:-1]) | {
            "submit",
            "report",
            "deadline",
            "meeting",
            "update",
            "review",
            "send",
            "file",
        }


def direction(text):
    if VI.search(text):
        # ASCII Vietnamese syllables can also be English words; do not count them
        # as English evidence. Remaining dictionary words indicate a mixed source.
        vietnamese_ascii = set(
            "a ai an anh ao ba bac ban bao be bi bo bon bu cha chi cho co con cu da dang dao day de di do du em ga gia hai hay he ho hoa khi la lai lam lo ma mai mang may me moi mot mu mua nam ngay ngo nha nhe nhu no noi o qua quan quang ra roi sau sao se so tai tam tan tao tay ten tha thanh the thi thu to tom toi ton tra tu tuy vao ve vi voi vua xa xin yeu".split()
        )
        ascii_words = list(
            re.finditer(
                r"(?<![\wÀ-ỹĐđ])[A-Za-z]+(?:'[A-Za-z]+)?(?![\wÀ-ỹĐđ])", text.lower()
            )
        )

        def english_word(match):
            word = match.group()
            return (
                len(word) > 1
                and word in english_words()
                and word not in vietnamese_ascii
                and word not in TECHNICAL_TERMS
            )

        # Isolated borrowed terms are common Vietnamese prose. Require an
        # English phrase, or an explicit English function word below.
        mixed = any(
            english_word(a) and english_word(b) and text[a.end() : b.start()].isspace()
            for a, b in zip(ascii_words, ascii_words[1:])
        )
        return "vi" if mixed or EN_WORDS.search(text) else "en"
    return "vi" if EN_WORDS.search(text) else "auto"


def join_google(data):
    return "".join(
        row[0]
        for row in data[0]
        if isinstance(row, list) and row and isinstance(row[0], str)
    )


def parse_bing_page(html):
    params = json.loads(
        re.search(r"params_AbusePreventionHelper\s*=\s*(\[[^\]]+\])", html)[1]
    )
    return {
        "ig": re.search(r'IG:"([^"]+)"', html)[1],
        "iid": re.search(r'data-iid="([^"]+)"', html)[1],
        "key": params[0],
        "token": params[1],
        "ttl": min(float(params[2]) / 1000, 3600),
    }


class FreeTranslator:
    def __init__(self, log=None):
        self.log = log
        self.token = None
        self.token_expires = 0
        self.google_until = 0

    def _request(self, url, headers, body, deadline, cancelled, format="json"):
        values = []
        start = time.monotonic()
        result = request_document(
            url, headers, body, deadline, cancelled, values.append, format=format
        )
        if self.log:
            self.log.record(
                {
                    "action": "translate",
                    "provider": "google_free"
                    if "googleapis.com" in url
                    else "bing_free",
                    "http_status": result.status,
                    "error": result.error_code,
                    "elapsed_seconds": round(time.monotonic() - start, 4),
                }
            )
        if any(isinstance(v, dict) and v.get("ShowCaptcha") for v in values):
            raise RuntimeError("FREE_RATE_LIMITED")
        if result.error_code or not values:
            raise RuntimeError(
                "FREE_RATE_LIMITED"
                if result.status in (401, 429)
                else (result.error_code or "FREE_UNAVAILABLE")
            )
        return values[-1]

    def translate(self, text, target, deadline, cancelled):
        if not any(ch.isalpha() for ch in text) or re.fullmatch(
            r"https?://\S+", text.strip()
        ):
            return text
        wanted = target or direction(text)
        wanted = "vi" if wanted == "auto" else wanted
        parts = []
        for chunk in split_text(text):
            if cancelled.is_set():
                raise RuntimeError("CANCELLED")
            if time.monotonic() >= deadline:
                raise RuntimeError("TASK_TIMEOUT")
            try:
                query = urllib.parse.urlencode(
                    {"client": "gtx", "sl": "auto", "tl": wanted, "dt": "t", "q": chunk}
                )
                data = self._request(
                    "https://translate.googleapis.com/translate_a/single?" + query,
                    {},
                    None,
                    min(deadline, time.monotonic() + 5),
                    cancelled,
                )
                if (
                    not target
                    and direction(text) == "auto"
                    and len(data) > 2
                    and data[2] == "vi"
                    and wanted == "vi"
                ):
                    query = urllib.parse.urlencode(
                        {"client": "gtx", "sl": "vi", "tl": "en", "dt": "t", "q": chunk}
                    )
                    data = self._request(
                        "https://translate.googleapis.com/translate_a/single?" + query,
                        {},
                        None,
                        min(deadline, time.monotonic() + 5),
                        cancelled,
                    )
                value = join_google(data)
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("TASK_TIMEOUT")
                if self.token is None or time.monotonic() >= self.token_expires:
                    html = self._request(
                        "https://www.bing.com/translator",
                        {},
                        None,
                        min(deadline, time.monotonic() + 5),
                        cancelled,
                        format="text",
                    )
                    self.token = parse_bing_page(html)
                    self.token_expires = time.monotonic() + self.token["ttl"]
                token = self.token
                url = "https://www.bing.com/ttranslatev3?" + urllib.parse.urlencode(
                    {"isVertical": 1, "IG": token["ig"], "IID": token["iid"]}
                )
                form = {
                    "fromLang": "auto-detect",
                    "text": chunk,
                    "to": wanted,
                    "token": token["token"],
                    "key": token["key"],
                }
                data = self._request(
                    url,
                    {"Content-Type": "application/x-www-form-urlencoded"},
                    urllib.parse.urlencode(form),
                    min(deadline, time.monotonic() + 5),
                    cancelled,
                )
                if (
                    not target
                    and direction(text) == "auto"
                    and data[0].get("detectedLanguage", {}).get("language") == "vi"
                    and wanted == "vi"
                ):
                    form.update(fromLang="vi", to="en")
                    data = self._request(
                        url,
                        {"Content-Type": "application/x-www-form-urlencoded"},
                        urllib.parse.urlencode(form),
                        min(deadline, time.monotonic() + 5),
                        cancelled,
                    )
                value = data[0]["translations"][0]["text"]
            if not value.strip():
                raise RuntimeError("FREE_UNAVAILABLE")
            separator = re.search(r"\s+$", chunk)
            parts.append(value.rstrip() + (separator[0] if separator else ""))
        return "".join(parts)
