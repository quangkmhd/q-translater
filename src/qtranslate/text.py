"""Conservative boundary chunks. Input is never truncated or split inside a word."""

import re


def split_text(text, limit=3000):
    parts = []
    while len(text) > limit:
        matches = list(re.finditer(r"\s+", text[:limit]))
        if matches:
            end = matches[-1].end()
        else:
            match = re.search(r"\s+", text[limit:])
            if not match:
                break
            end = limit + match.end()
        parts.append(text[:end])
        text = text[end:]
    if text:
        parts.append(text)
    return parts or [""]
