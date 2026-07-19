"""A minimal transactional-outbox helper, so a review submission survives Hrz7 being down.

A producer enqueues the review durably as part of its own work, then a relay flushes pending
reviews to Hrz7. On a submission failure the entry stays enqueued (retried on the next flush), so
an escalation is never silently lost. The in-memory implementation exercises the pattern in tests
and the offline demo; a real deployment binds a durable store (the same seam as the case store).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .client import ReviewClient, ReviewClientError
from .models import Review, ReviewSubmitted


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    review: Review
    actor: str


@runtime_checkable
class Outbox(Protocol):
    def enqueue(self, review: Review, *, actor: str = "") -> None: ...
    def pending(self) -> tuple[OutboxEntry, ...]: ...
    def flush(self, client: ReviewClient) -> list[ReviewSubmitted]: ...


@dataclass(slots=True)
class InMemoryOutbox:
    """A non-durable outbox for tests / demos. Keeps failed entries for the next flush."""

    _entries: list[OutboxEntry] = field(default_factory=list)

    def enqueue(self, review: Review, *, actor: str = "") -> None:
        self._entries.append(OutboxEntry(review=review, actor=actor))

    def pending(self) -> tuple[OutboxEntry, ...]:
        return tuple(self._entries)

    def flush(self, client: ReviewClient) -> list[ReviewSubmitted]:
        """Submit each pending entry; keep any that fail so they retry on the next flush."""
        submitted: list[ReviewSubmitted] = []
        remaining: list[OutboxEntry] = []
        for entry in self._entries:
            try:
                submitted.append(client.submit(entry.review, actor=entry.actor))
            except ReviewClientError:
                remaining.append(entry)  # keep it; the console may be down or slow
        self._entries = remaining
        return submitted
