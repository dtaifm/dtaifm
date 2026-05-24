"""Minimal JSON-over-HTTP client used by local teacher adapters.

Wraps stdlib urllib so the framework keeps zero runtime dependencies for the
local providers (Ollama, Lemonade). The client exposes a tiny interface that
tests can satisfy with a hand-built fake — no real network calls run in CI.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class HttpJsonClient:
    """JSON POST/GET over stdlib urllib. All non-2xx responses raise OSError."""

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    def post_json(self, url: str, payload: dict, *, headers: dict | None = None) -> Any:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                **(headers or {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            # URLError covers HTTPError (non-2xx) and connection failures.
            raise OSError(f"HTTP POST {url} failed: {exc}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"HTTP POST {url} returned non-JSON body: {exc}") from exc

    def get(self, url: str, *, headers: dict | None = None) -> Any:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", **(headers or {})},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise OSError(f"HTTP GET {url} failed: {exc}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"HTTP GET {url} returned non-JSON body: {exc}") from exc
