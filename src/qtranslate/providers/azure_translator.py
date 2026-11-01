"""Official Azure Translator standard NMT; no web scraping or LLM fallback."""

import re
import threading
import time
import urllib.parse
from qtranslate.audit.legacy import read_routing, remember_success
from qtranslate.config.secrets import translation_credential
from qtranslate.providers.http import request_document
from qtranslate.providers.free import direction, VI
from qtranslate.text import split_text

PROVIDER = "azure_translator"
ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate"
MESSAGES = {
    "AZURE_KEY_MISSING": "Chưa có key Azure Translator. Mở Cài đặt → Alt+C để nhập và kiểm tra key.",
    "AZURE_AUTH_FAILED": "Không xác thực được. Kiểm tra key Translator và region.",
    "AZURE_QUOTA_EXCEEDED": "Azure Translator đã hết hạn mức miễn phí của kỳ này.",
    "AZURE_RATE_LIMITED": "Azure Translator đang giới hạn request. Thử lại sau.",
    "AZURE_FORBIDDEN": "Azure từ chối truy cập. Kiểm tra trạng thái resource trên Azure.",
    "AZURE_INVALID_CONFIG": "Key hoặc region không hợp lệ.",
    "AZURE_REQUEST_REJECTED": "Azure không chấp nhận nội dung yêu cầu.",
    "AZURE_UNAVAILABLE": "Azure Translator chưa phản hồi hợp lệ.",
    "KEY_TIMEOUT": "Azure chưa trả xong trong 5 giây.",
    "TASK_TIMEOUT": "Không hoàn tất trong 30 giây.",
    "NETWORK_ERROR": "Không kết nối được Azure Translator.",
    "CANCELLED": "Đã hủy tác vụ.",
}
ERRORS = {
    "AZURE_KEY_MISSING",
    "AZURE_AUTH_FAILED",
    "AZURE_QUOTA_EXCEEDED",
    "AZURE_RATE_LIMITED",
    "AZURE_FORBIDDEN",
    "AZURE_UNAVAILABLE",
    "AZURE_INVALID_CONFIG",
    "AZURE_REQUEST_REJECTED",
    "NETWORK_ERROR",
    "KEY_TIMEOUT",
    "TASK_TIMEOUT",
    "CANCELLED",
}


class AzureTranslator:
    def __init__(self, store, state_path, log=None, routing_lock=None):
        self.store = store
        self.state_path = state_path
        self.log = log
        self.routing_lock = routing_lock or threading.Lock()
        self.cooldown = {}

    @staticmethod
    def _check(deadline, cancelled, timeout="TASK_TIMEOUT"):
        if cancelled.is_set():
            raise RuntimeError("CANCELLED")
        if time.monotonic() >= deadline:
            raise RuntimeError(timeout)

    def _request(self, credential, text, target, deadline, cancelled):
        self._check(deadline, cancelled, "KEY_TIMEOUT")
        headers = {
            "Ocp-Apim-Subscription-Key": credential["key"],
            "Content-Type": "application/json; charset=UTF-8",
        }
        region = credential.get("region", "global")
        if region != "global":
            headers["Ocp-Apim-Subscription-Region"] = region
        query = {"api-version": "3.0", "to": target, "textType": "plain"}
        # Azure may detect mixed EN/VI as vi and return the source unchanged
        # for vi->vi. An English source hint translates its English clauses.
        if target == "vi" and VI.search(text) and direction(text) == "vi":
            query["from"] = "en"
        url = ENDPOINT + "?" + urllib.parse.urlencode(query)
        values = []
        started = time.monotonic()
        result = request_document(
            url, headers, [{"Text": text}], deadline, cancelled, values.append
        )
        payload = values[-1] if values else None
        detail = payload.get("error", {}) if isinstance(payload, dict) else {}
        code = str(detail.get("code", "")) if isinstance(detail, dict) else ""
        error = None
        if cancelled.is_set():
            error = "CANCELLED"
        elif result.status == 401:
            error = "AZURE_AUTH_FAILED"
        elif code == "403001":
            error = "AZURE_QUOTA_EXCEEDED"
        elif result.status == 403:
            error = "AZURE_FORBIDDEN"
        elif result.status == 429:
            error = "AZURE_RATE_LIMITED"
        elif result.status == 400:
            error = "AZURE_REQUEST_REJECTED"
        elif result.error_code:
            error = (
                result.error_code
                if result.error_code in ERRORS
                else "AZURE_UNAVAILABLE"
            )
        elif result.status != 200:
            error = "AZURE_UNAVAILABLE"
        if self.log:
            self.log.record(
                {
                    "action": "translate",
                    "provider": PROVIDER,
                    "credential_id": credential.get("id"),
                    "http_status": result.status,
                    "azure_code": code or None,
                    "error": error,
                    "elapsed_seconds": round(time.monotonic() - started, 4),
                }
            )
        if error:
            if error == "AZURE_RATE_LIMITED" and credential.get("id"):
                self.cooldown[credential["id"]] = time.monotonic() + result.retry_after
            raise RuntimeError(error)
        self._check(deadline, cancelled, "KEY_TIMEOUT")
        try:
            if not isinstance(payload, list) or len(payload) != 1:
                raise ValueError
            row = payload[0]
            translations = row["translations"]
            value = next(t["text"] for t in translations if t.get("to") == target)
            if not isinstance(value, str) or not value.strip():
                raise ValueError
            detected = row.get("detectedLanguage", {}).get("language")
            return value, detected
        except (ValueError, KeyError, TypeError, StopIteration, AttributeError):
            raise RuntimeError("AZURE_UNAVAILABLE") from None

    @classmethod
    def probe(cls, key, region="global"):
        credential = translation_credential(key, region)
        client = cls(None, None)
        client._request(
            credential, "Hello.", "vi", time.monotonic() + 5, threading.Event()
        )
        return credential

    def translate(self, text, target, deadline, cancelled):
        self._check(deadline, cancelled)
        credentials = self.store.translation_credentials()
        if not credentials:
            raise RuntimeError("AZURE_KEY_MISSING")
        if target not in (None, "en", "vi"):
            raise RuntimeError("AZURE_REQUEST_REJECTED")
        if not any(c.isalpha() for c in text) or re.fullmatch(
            r"https?://\S+", text.strip()
        ):
            return text
        sticky = (
            read_routing(self.state_path)
            .get("last_success", {})
            .get("translation", {})
            .get("credential_id")
        )
        index = next((i for i, c in enumerate(credentials) if c["id"] == sticky), 0)
        credentials = credentials[index:] + credentials[:index]
        wanted = target or direction(text)
        unknown = wanted == "auto"
        wanted = "vi" if unknown else wanted
        parts = []
        chosen = None
        failed = set()
        chunks = (
            part[i : i + 45000]
            for part in split_text(text, 45000)
            for i in range(0, len(part), 45000)
        )
        for chunk in chunks:
            self._check(deadline, cancelled)
            error = "AZURE_RATE_LIMITED"
            for credential in credentials:
                self._check(deadline, cancelled)
                if credential["id"] in failed:
                    continue
                if self.cooldown.get(credential["id"], 0) > time.monotonic():
                    continue
                attempt_deadline = min(deadline, time.monotonic() + 5)
                try:
                    value, detected = self._request(
                        credential, chunk, wanted, attempt_deadline, cancelled
                    )
                    resolved = "en" if unknown and detected == "vi" else wanted
                    if resolved != wanted:
                        value, _ = self._request(
                            credential, chunk, resolved, attempt_deadline, cancelled
                        )
                    wanted, unknown = resolved, False
                    chosen = credential
                    index = credentials.index(credential)
                    credentials = credentials[index:] + credentials[:index]
                    break
                except RuntimeError as exc:
                    error = str(exc)
                    failed.add(credential["id"])
                    self._check(deadline, cancelled)
            else:
                raise RuntimeError(error)
            separator = re.search(r"\s+$", chunk)
            parts.append(value.rstrip() + (separator[0] if separator else ""))
        self._check(deadline, cancelled)
        with self.routing_lock:
            self._check(deadline, cancelled)
            remember_success(
                self.state_path,
                "translation",
                {
                    "provider": PROVIDER,
                    "credential_id": chosen["id"],
                    "model": "standard",
                },
            )
        return "".join(parts)
