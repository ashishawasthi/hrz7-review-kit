"""hrz7-review-kit: the shared client for routing a review to an Hrz7 Human-Review console.

The producer half of dependency rule R8 ("any consequential action that sets
``requires_human_review`` MUST route to Hrz7"): a small, domain-neutral review-submission
primitive plus a transactional outbox, so every producer submits reviews the same way instead of
copy-pasting an HTTP call into each repo. Reuses ``hex-service-kit`` for the S2S transport
hardening; the HTTP transport is pluggable so the client is unit-testable with no live server.
"""

from __future__ import annotations

from .client import ReviewClient, ReviewClientError, Transport
from .models import Citation, Review, ReviewSubmitted
from .outbox import InMemoryOutbox, Outbox, OutboxEntry

__version__ = "0.1.0"

__all__ = [
    "Citation",
    "InMemoryOutbox",
    "Outbox",
    "OutboxEntry",
    "Review",
    "ReviewClient",
    "ReviewClientError",
    "ReviewSubmitted",
    "Transport",
    "__version__",
]
