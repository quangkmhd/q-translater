import json
import re
import shlex
from pathlib import Path
from qtranslate.audit.legacy import parse_env
from .secrets import translation_credential


def parse_import(path):
    text = Path(path).read_text()
    if text.lstrip().startswith("{"):
        return json.loads(text)
    values, remaining = {}, []
    for line in text.splitlines():
        match = re.match(
            r"^\s*(?:export\s+)?AZURE_TRANSLATOR_(KEY|REGION)(_\d+)?\s*=\s*(.*)$", line
        )
        if match:
            field, suffix, raw = match.groups()
            values[field + (suffix or "")] = " ".join(shlex.split(raw, comments=True))
            remaining.append("")
        else:
            remaining.append(line)
    bundle = parse_env("\n".join(remaining))
    credentials = []
    for name, key in values.items():
        if not name.startswith("KEY") or not key:
            continue
        region = values.get("REGION" + name[3:], values.get("REGION", "global"))
        credentials.append(
            {**translation_credential(key, region), "status": "unverified"}
        )
    if credentials:
        bundle["providers"].append(
            {"id": "azure_translator", "models": [], "credentials": credentials}
        )
    return bundle
