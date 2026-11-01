"""Private stdin/stdout worker for ordinary web translation documents.

The parent validates the endpoint and owns the absolute deadline/cancellation.
No URL, input, token or headers appear in the process arguments or on disk.
"""

import json
import sys
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    config = json.load(sys.stdin)
    body = config["body"]
    if body is not None:
        body = (body if isinstance(body, str) else json.dumps(body)).encode()
    request = urllib.request.Request(
        config["url"], data=body, headers=config["headers"]
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(request, timeout=config["timeout"])
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status = response.status
        retry_after = response.headers.get("Retry-After", "")
        while True:
            chunk = response.read(16384)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    sys.stderr.write(f"\nQT_STATUS:{status}\nQT_RETRY_AFTER:{retry_after}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Provider/URL/headers can contain credentials. Keep diagnostics code-only.
        sys.stderr.write("QT_DOCUMENT_ERROR\n")
        raise SystemExit(1)
