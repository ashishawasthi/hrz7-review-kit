"""The review client + outbox, exercised with a fake transport (no live server)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from hrz7_review_kit import (
    InMemoryOutbox,
    Review,
    ReviewClient,
    ReviewClientError,
)


def _review(action: str = "disburse_facility") -> Review:
    return Review(
        action=action,
        subject="Acme Holdings (FICTIONAL)",
        maker="demo.analyst@bank.example",
        tenant="demo-bank",
        summary="Disburse SGD 2.5m facility",
        severity="high",
        required_approvals=2,
        case_ref="case-123",
    )


def test_submit_posts_the_payload_and_parses_the_result() -> None:
    seen: dict[str, Any] = {}

    def transport(
        url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> dict[str, Any]:
        import json

        seen["url"] = url
        seen["payload"] = json.loads(body)
        seen["headers"] = dict(headers)
        return {"review_id": "rev-1", "tenant": "demo-bank", "state": "pending"}

    client = ReviewClient("http://localhost:8087", transport=transport)
    result = client.submit(_review(), actor="hrz6-case-engine")

    assert result.review_id == "rev-1"
    assert result.tenant == "demo-bank"
    assert seen["url"] == "http://localhost:8087/v1/service/reviews"
    # The maker + tenant are asserted in the body (the S2S caller is trusted on this path).
    assert seen["payload"]["maker"] == "demo.analyst@bank.example"
    assert seen["payload"]["tenant"] == "demo-bank"
    assert seen["payload"]["required_approvals"] == 2


def test_plaintext_non_loopback_url_is_refused() -> None:
    with pytest.raises(ValueError):
        ReviewClient("http://review.example.com")  # https required off loopback


def test_malformed_response_raises() -> None:
    def transport(
        url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> dict[str, Any]:
        return {"unexpected": "shape"}

    client = ReviewClient("https://review.internal", transport=transport)
    with pytest.raises(ReviewClientError):
        client.submit(_review(), actor="svc")


def test_outbox_keeps_failed_entries_for_retry() -> None:
    calls = {"n": 0}

    def flaky(url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ReviewClientError("console down")
        return {"review_id": f"rev-{calls['n']}", "tenant": "demo-bank", "state": "pending"}

    client = ReviewClient("https://review.internal", transport=flaky)
    outbox = InMemoryOutbox()
    outbox.enqueue(_review(), actor="svc")

    # First flush fails: the entry is kept, nothing submitted.
    assert outbox.flush(client) == []
    assert len(outbox.pending()) == 1

    # Second flush succeeds: the entry is submitted and drained.
    submitted = outbox.flush(client)
    assert len(submitted) == 1
    assert outbox.pending() == ()
