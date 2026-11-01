"""Five verified-provider payloads; one shared streaming/capability contract."""

import base64
import mimetypes
from pathlib import Path
from qtranslate.audit.legacy import (
    inference_request,
    contains_reasoning,
    CLOUDFLARE_MODELS,
)
from .base import ProviderChunk, ProviderResponse
from .http import request_stream


class AIAdapter:
    def __init__(self, store, transport=request_stream):
        self.store = store
        self.transport = transport

    def run(self, payload, candidate, deadline, cancelled, on_delta=None):
        pid = candidate.provider
        model = candidate.model
        credential = self.store.credential(candidate.credential)
        if (
            (pid == "cloudflare" and model not in CLOUDFLARE_MODELS)
            or "glm-5.3" in model
            or (pid == "google" and model.startswith("gemini-3"))
        ):
            return ProviderResponse(error_code="MODEL_NOT_ALLOWED")
        if pid == "openrouter" and not model.endswith(":free"):
            return ProviderResponse(error_code="COST_POLICY")
        url, headers, body = inference_request(
            pid, credential, model, payload.get("text", "")
        )
        prompt = payload.get("prompt")
        if prompt:
            if pid == "google":
                body["systemInstruction"] = {"parts": [{"text": prompt}]}
            else:
                body["messages"][0] = {"role": "system", "content": prompt}
        if payload.get("messages"):
            messages = [dict(m) for m in payload["messages"]]
            if any(
                m.get("role") not in ("user", "assistant")
                or not isinstance(m.get("content"), str)
                for m in messages
            ):
                return ProviderResponse(error_code="INVALID_MESSAGES")
            if pid == "google":
                body["contents"] = [
                    {
                        "role": "model" if m["role"] == "assistant" else "user",
                        "parts": [{"text": m["content"]}],
                    }
                    for m in messages
                ]
                if not model.startswith("gemini"):
                    # Gemma has no systemInstruction support. Include instructions
                    # in the first user turn; preserve subsequent message roles.
                    body.pop("systemInstruction", None)
                    body["contents"][0]["parts"][0]["text"] = (
                        prompt + "\n\n" if prompt else ""
                    ) + messages[0]["content"]
            else:
                body["messages"] = (
                    [{"role": "system", "content": prompt}] if prompt else []
                ) + messages
        if pid == "google":
            url = url.replace(":generateContent", ":streamGenerateContent") + "?alt=sse"
            body["generationConfig"]["maxOutputTokens"] = 4096
        else:
            body["stream"] = True
            if pid == "ollama":
                body["options"]["num_predict"] = 4096
            else:
                body["max_tokens"] = 4096
        if payload.get("image_path"):
            path = Path(payload["image_path"])
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode()
            if pid == "google":
                body["contents"] = [
                    {
                        "parts": [
                            {"inline_data": {"mime_type": mime, "data": encoded}},
                            {"text": payload.get("text", "Translate this image.")},
                        ]
                    }
                ]
            else:
                message = body["messages"][-1]
                if pid == "ollama":
                    message["images"] = [encoded]
                else:
                    message["content"] = [
                        {
                            "type": "text",
                            "text": payload.get("text", "Translate this image."),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ]
        output = []
        finished = False
        finish_reason = None
        error = None

        def receive(data):
            nonlocal finished, finish_reason, error
            if data == "[DONE]":
                finished = True
                return
            if not isinstance(data, dict):
                return
            if contains_reasoning(data):
                error = "THINKING_STILL_ENABLED"
                return
            if data.get("error") or data.get("success") is False:
                error = "PROVIDER_ERROR"
                return
            delta = ""
            if pid == "google":
                for c in data.get("candidates", []):
                    for part in c.get("content", {}).get("parts", []):
                        if not part.get("thought"):
                            delta += part.get("text", "")
                    reason = c.get("finishReason")
                    if reason:
                        finished = True
                        finish_reason = reason
            elif pid == "ollama":
                delta = data.get("message", {}).get("content", "")
                if data.get("done"):
                    finished = True
                    finish_reason = data.get("done_reason")
            elif isinstance(data.get("response"), str):
                delta = data["response"]
            else:
                for choice in data.get("choices", []):
                    delta += choice.get("delta", {}).get("content") or ""
                    if choice.get("finish_reason"):
                        finished = True
                        finish_reason = choice["finish_reason"]
            if delta and not error:
                output.append(delta)
                if on_delta:
                    on_delta(ProviderChunk(delta))

        result = self.transport(
            url,
            headers,
            body,
            deadline,
            cancelled,
            receive,
            format="ndjson" if pid == "ollama" else "sse",
        )
        text = "".join(output).strip()
        error = error or result.error_code
        if finish_reason and finish_reason.lower() not in ("stop", "end_turn"):
            error = error or "INCOMPLETE_OUTPUT"
        if not finished or not text:
            error = error or "INCOMPLETE_OUTPUT"
        return ProviderResponse(
            text, not error, finish_reason, error, result.status, result.retry_after
        )
