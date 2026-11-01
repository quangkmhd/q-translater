"""Versioned, data-only IPC validation; no secrets or shell execution."""

import json

ACTIONS = {"translate", "rewrite", "image_translate"}


def validate_message(value, *, epoch=None):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("UNSUPPORTED_PROTOCOL")
    if value.get("action") not in ACTIONS:
        raise ValueError("UNKNOWN_ACTION")
    if epoch is not None and value.get("epoch") != epoch:
        raise ValueError("STALE_EPOCH")
    if not isinstance(value.get("epoch"), str) or not value["epoch"]:
        raise ValueError("MISSING_EPOCH")
    if value["action"] != "image_translate" and not isinstance(value.get("text"), str):
        raise ValueError("INVALID_TEXT")
    context = value.get("context", {})
    if not isinstance(context, dict):
        raise ValueError("INVALID_CONTEXT")
    if any(k in value for k in ("key", "api_key", "authorization", "secret")):
        raise ValueError("SECRET_IN_PROTOCOL")
    return dict(value)


class ProtocolGate:
    def __init__(self):
        self.owner = None
        self.epoch = None

    def set_owner(self, owner, epoch):
        self.owner = owner
        self.epoch = epoch

    def validate(self, sender, message):
        if not self.owner or sender != self.owner:
            raise ValueError("UNTRUSTED_CALLER")
        return validate_message(message, epoch=self.epoch)


def validate_crop_path(path, root):
    import os
    from pathlib import Path

    p = Path(path)
    root = Path(root).resolve()
    if not p.is_absolute() or p.is_symlink() or not p.is_file():
        raise ValueError("INVALID_CROP")
    resolved = p.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("INVALID_CROP")
    stat = p.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise ValueError("INSECURE_CROP")
    return str(resolved)


class TextTransfer:
    def __init__(self):
        self.entries = {}

    def begin(self, id, count):
        import tempfile

        if (
            id in self.entries
            or not isinstance(count, int)
            or count < 1
            or len(self.entries) >= 3
        ):
            raise ValueError("INVALID_TRANSFER")
        self.entries[id] = {
            "count": count,
            "next": 0,
            "file": tempfile.TemporaryFile(mode="w+", encoding="utf-8"),
        }

    def append(self, id, index, text):
        entry = self.entries[id]
        if (
            index != entry["next"]
            or not isinstance(text, str)
            or len(text.encode()) > 65536
        ):
            raise ValueError("INVALID_CHUNK")
        entry["file"].write(text)
        entry["next"] += 1

    def finish(self, id):
        entry = self.entries[id]
        if entry["next"] != entry["count"]:
            raise ValueError("INCOMPLETE_TRANSFER")
        entry["file"].seek(0)
        text = entry["file"].read()
        self.discard(id)
        return text

    def discard(self, id):
        entry = self.entries.pop(id, None)
        if entry:
            entry["file"].close()

    def close(self):
        for id in list(self.entries):
            self.discard(id)
