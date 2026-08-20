"""Standard-library HTTP transport for vision providers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping


class UrllibTransport:
    """Minimal JSON-over-HTTP POST transport using only urllib.

    HTTP error statuses are returned (not raised) so providers can map
    authentication, rate-limit, and server errors themselves; network
    failures raise an ``OSError`` subclass.
    """

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> tuple[int, object]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            try:
                body: object = json.loads(detail) if detail.strip() else {}
            except json.JSONDecodeError:
                body = {}
            return error.code, body
