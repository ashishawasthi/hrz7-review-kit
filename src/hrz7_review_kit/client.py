"""The review-submission client: POST a review to an Hrz7-compatible service intake, S2S-authed.

Reuses the shared S2S transport hardening from ``hex-service-kit`` (the https-only base-URL guard
and the bearer / signed-actor headers) rather than re-implementing it. The HTTP transport is
pluggable so the client is unit-testable offline with no live server; the default is a small
stdlib ``urllib`` POST (no third-party HTTP dependency).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse

from .models import Review, ReviewSubmitted

#: A transport is (url, body, headers, timeout) -> parsed JSON dict. Injectable for testing.
Transport = Callable[[str, bytes, Mapping[str, str], float], dict[str, Any]]

_SERVICE_PATH = "/v1/service/reviews"
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# The S2S actor headers, kept byte-for-byte compatible with hex-service-kit's server verifier
# (``hex_service_kit.web.make_require_service_caller``) so Hrz7 accepts what this client sends.
_ACTOR_HEADER = "X-S2S-Actor"
_ACTOR_SIG_HEADER = "X-S2S-Actor-Sig"


def _validate_base_url(url: str, *, service: str) -> str:
    """Return ``url`` without a trailing slash; refuse plaintext outside loopback (https-only).

    Self-contained (no hex-service-kit dependency) so this kit installs zero-dep and zero-cred like
    ``pii-pack``, avoiding the nested git+https resolution conflict a commons-on-commons dep causes.
    """
    stripped = url.rstrip("/")
    parsed = urlparse(stripped)
    host = parsed.hostname or ""
    if parsed.scheme == "https":
        return stripped
    if parsed.scheme == "http" and host in _LOOPBACK_HOSTS:
        return stripped
    raise ValueError(f"{service} base URL must be https outside loopback (got {url!r})")


def _client_headers(actor: str, *, token_env: str, signing_key_env: str) -> dict[str, str]:
    """Auth headers for one outbound S2S request: a bearer token, and an HMAC-signed actor."""
    headers: dict[str, str] = {}
    token = os.environ.get(token_env, "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    key = os.environ.get(signing_key_env, "")
    if actor and key:
        signature = hmac.new(key.encode("utf-8"), actor.encode("utf-8"), hashlib.sha256).hexdigest()
        headers[_ACTOR_HEADER] = actor
        headers[_ACTOR_SIG_HEADER] = signature
    return headers


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
        self._base = _validate_base_url(base_url, service=service)
        self._token_env = token_env
        self._signing_key_env = signing_key_env
        self._timeout = timeout
        self._transport: Transport = transport or _urllib_transport

    def submit(self, review: Review, *, actor: str = "") -> ReviewSubmitted:
        """Submit one review. ``actor`` is the submitting service's identity for the S2S header."""
        headers = {
            "Content-Type": "application/json",
            **_client_headers(
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
