"""The review-submission client: POST a review to an Hrz7-compatible service intake, S2S-authed.

Reuses the shared S2S transport hardening from ``hex-service-kit`` (the https-only base-URL guard
and the bearer / signed-actor headers) rather than re-implementing it. The HTTP transport is
pluggable so the client is unit-testable offline with no live server; the default is a small
stdlib ``urllib`` POST (no third-party HTTP dependency).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from hex_service_kit.s2s import client_headers, validate_base_url

from .models import Review, ReviewSubmitted

#: A transport is (url, body, headers, timeout) -> parsed JSON dict. Injectable for testing.
Transport = Callable[[str, bytes, Mapping[str, str], float], dict[str, Any]]

_SERVICE_PATH = "/v1/service/reviews"


class ReviewClientError(RuntimeError):
    """Raised when a review submission fails (non-2xx response or an unreachable console)."""


def _urllib_transport(
    url: str, body: bytes, headers: Mapping[str, str], timeout: float
) -> dict[str, Any]:  # pragma: no cover - exercised against a live server, not in the offline gate
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return payload
    except urllib.error.HTTPError as exc:
        raise ReviewClientError(f"Hrz7 review intake returned {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ReviewClientError(f"Hrz7 review intake unreachable: {exc.reason}") from exc


class ReviewClient:
    """Submit a review to an Hrz7-compatible console at ``base_url`` (rule R8's client half)."""

    def __init__(
        self,
        base_url: str,
        *,
        service: str = "hrz7-review-console",
        token_env: str = "HRZ7_S2S_TOKEN",
        signing_key_env: str = "HRZ7_S2S_SIGNING_KEY",
        timeout: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        # https-only outside loopback; a plaintext non-loopback URL is refused at construction.
        self._base = validate_base_url(base_url, service=service)
        self._token_env = token_env
        self._signing_key_env = signing_key_env
        self._timeout = timeout
        self._transport: Transport = transport or _urllib_transport

    def submit(self, review: Review, *, actor: str = "") -> ReviewSubmitted:
        """Submit one review. ``actor`` is the submitting service's identity for the S2S header."""
        headers = {
            "Content-Type": "application/json",
            **client_headers(
                actor, token_env=self._token_env, signing_key_env=self._signing_key_env
            ),
        }
        body = json.dumps(review.to_payload()).encode("utf-8")
        data = self._transport(self._base + _SERVICE_PATH, body, headers, self._timeout)
        try:
            return ReviewSubmitted(
                review_id=str(data["review_id"]),
                tenant=str(data.get("tenant", review.tenant)),
                state=str(data.get("state", "pending")),
            )
        except (KeyError, TypeError) as exc:
            raise ReviewClientError(f"malformed Hrz7 response: {data!r}") from exc
