"""Private merge-by-identity store. Model capabilities belong to each credential."""

import copy
import hashlib
import json
import fcntl
import os
import re
from contextlib import contextmanager
from functools import wraps
from dataclasses import dataclass
from pathlib import Path
from qtranslate.audit.legacy import PROVIDERS, write_private


def translation_credential(key, region="global"):
    if (
        not isinstance(key, str)
        or not key.strip()
        or any(ord(c) < 33 or ord(c) > 126 for c in key.strip())
    ):
        raise ValueError("AZURE_INVALID_CONFIG")
    region = region.strip().lower() if isinstance(region, str) else ""
    region = region or "global"
    if not re.fullmatch(r"[a-z][a-z0-9]{0,63}", region):
        raise ValueError("AZURE_INVALID_CONFIG")
    return {"key": key.strip(), "region": region}


def serialized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.transaction():
            return method(self, *args, **kwargs)

    return wrapper


@dataclass(frozen=True)
class CredentialRef:
    id: str
    provider: str
    secret_ref: str
    account_ref: str | None = None


@dataclass(frozen=True)
class Candidate:
    provider: str
    credential: CredentialRef
    model: str
    capability: str


@dataclass(frozen=True)
class ImportReport:
    added: int
    duplicates: int
    quarantined: int
    model_pairs: int


class SecretStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @serialized
    def remove_invalid(self, ids):
        data = self.load()
        quarantined = {
            row.get("credential", {}).get("id") for row in data["quarantine"]
        }
        for provider in data["providers"]:
            keep = []
            for c in provider["credentials"]:
                if c["id"] not in ids:
                    keep.append(c)
                elif c["id"] not in quarantined:
                    data["quarantine"].append(
                        {"reason": "invalid_auth_confirmed", "credential": c}
                    )
                    quarantined.add(c["id"])
            provider["credentials"] = keep
        write_private(self.path, data)

    def load(self):
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {
                "format": "qtranslate-store",
                "version": 1,
                "providers": [],
                "routing": {},
                "quarantine": [],
            }

    @serialized
    def merge(self, bundle):
        if (
            not isinstance(bundle, dict)
            or bundle.get("format") not in ("qtranslate-portable", "qtranslate-store")
            or bundle.get("version") != 1
            or not isinstance(bundle.get("providers"), list)
        ):
            raise ValueError("INVALID_IMPORT")
        data = self.load()
        added = duplicates = pairs = 0
        for p in bundle["providers"]:
            if p.get("id") not in (*PROVIDERS, "azure_translator") or not isinstance(
                p.get("credentials"), list
            ):
                raise ValueError("INVALID_PROVIDER")
            dest = next((x for x in data["providers"] if x["id"] == p["id"]), None)
            if dest is None:
                dest = {"id": p["id"], "models": [], "credentials": []}
                data["providers"].append(dest)
            for m in p.get("models", []):
                if isinstance(m, str) and m not in dest["models"]:
                    dest["models"].append(m)
            for source in p["credentials"]:
                if p["id"] == "azure_translator":
                    source = {
                        **source,
                        **translation_credential(
                            source.get("key"), source.get("region", "global")
                        ),
                    }
                if not isinstance(source.get("key"), str) or not source["key"]:
                    raise ValueError("INVALID_CREDENTIAL")
                if p["id"] == "cloudflare" and not source.get("account_id"):
                    raise ValueError("MISSING_ACCOUNT_BINDING")
                c = next(
                    (
                        x
                        for x in dest["credentials"]
                        if (
                            x["key"],
                            x.get("region", "global")
                            if p["id"] == "azure_translator"
                            else x.get("account_id", ""),
                        )
                        == (
                            source["key"],
                            source.get("region", "global")
                            if p["id"] == "azure_translator"
                            else source.get("account_id", ""),
                        )
                    ),
                    None,
                )
                if c is None:
                    c = copy.deepcopy(source)
                    fingerprint = hashlib.sha256(
                        (
                            p["id"]
                            + "\0"
                            + source["key"]
                            + "\0"
                            + (
                                source["region"]
                                if p["id"] == "azure_translator"
                                else source.get("account_id", "")
                            )
                        ).encode()
                    ).hexdigest()[:16]
                    c["id"] = p["id"] + "-" + fingerprint
                    c["capabilities"] = {}
                    dest["credentials"].append(c)
                    added += 1
                else:
                    duplicates += 1
                if p["id"] == "azure_translator":
                    if source.get("status") == "translation_verified":
                        c["status"] = "translation_verified"
                        c["verified_at"] = source.get("verified_at", "")
                    continue
                if (
                    p["id"] in ("tavily", "jina", "datalab")
                    and source.get("status") == "capability_verified"
                ):
                    for field in ("status", "verified_at", "median_seconds"):
                        if field in source:
                            c[field] = source[field]
                caps = copy.deepcopy(source.get("capabilities", {}))
                if (
                    source.get("status") == "text_verified"
                    and source.get("thinking_disabled") is True
                    and source.get("verified_text_model")
                ):
                    caps.setdefault("text", {})[source["verified_text_model"]] = {
                        "thinking_disabled": True,
                        "verified_at": source.get("verified_at", ""),
                    }
                for capability, models in caps.items():
                    if capability not in ("text", "vision") or not isinstance(
                        models, dict
                    ):
                        continue
                    for model, evidence in models.items():
                        if (
                            not isinstance(evidence, dict)
                            or evidence.get("thinking_disabled") is not True
                        ):
                            continue
                        pool = c["capabilities"].setdefault(capability, {})
                        if model not in pool:
                            pairs += 1
                        pool[model] = evidence
        data["routing"] = data.get("routing") or copy.deepcopy(
            bundle.get("routing", {})
        )
        data["quarantine"] += copy.deepcopy(bundle.get("quarantine", []))
        if self.path.exists():
            write_private(self.path.with_suffix(".backup.json"), self.load())
        write_private(self.path, data)
        return ImportReport(added, duplicates, len(bundle.get("quarantine", [])), pairs)

    def candidates(self, capability="text", order=None):
        data = self.load()
        result = []
        providers = data["providers"]
        order = order or data.get("routing", {}).get("provider_order", [])
        providers.sort(key=lambda p: order.index(p["id"]) if p["id"] in order else 999)
        for p in providers:
            models = list(p["models"])
            for c in p["credentials"]:
                for model in c.get("capabilities", {}).get(capability, {}):
                    if model not in models:
                        models.append(model)
            for model in models:
                for c in p["credentials"]:
                    if model in c.get("capabilities", {}).get(capability, {}):
                        result.append(
                            Candidate(
                                p["id"],
                                CredentialRef(
                                    c["id"], p["id"], c["id"], c.get("account_id")
                                ),
                                model,
                                capability,
                            )
                        )
        return result

    def credential(self, ref):
        for p in self.load()["providers"]:
            if p["id"] == ref.provider:
                for c in p["credentials"]:
                    if c["id"] == ref.id:
                        return c
        raise KeyError("UNKNOWN_CREDENTIAL")

    def get(self, ref):
        return self.credential(ref)["key"]

    def all_secrets(self):
        return [c["key"] for p in self.load()["providers"] for c in p["credentials"]]

    def translation_credentials(self, verified=True):
        return [
            c
            for p in self.load()["providers"]
            if p["id"] == "azure_translator"
            for c in p["credentials"]
            if not verified or c.get("status") == "translation_verified"
        ]

    def export_verified(self, path):
        data = self.load()
        data["format"] = "qtranslate-portable"
        data["quarantine"] = []
        for p in data["providers"]:
            p["credentials"] = [
                c
                for c in p["credentials"]
                if c.get("capabilities")
                or c.get("status") in ("capability_verified", "translation_verified")
            ]
        data["providers"] = [p for p in data["providers"] if p["credentials"]]
        write_private(path, data)
