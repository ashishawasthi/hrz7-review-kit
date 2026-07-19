"""The review-submission payload: the wire shape a producer sends to Hrz7's service intake.

Domain-neutral: it names the maker-checker concepts (action, severity, approvals, segregation
group) but no vertical policy. ``maker`` and ``tenant`` are asserted by the submitting service and
trusted because the service is an authenticated S2S caller (Hrz7 verifies the caller, not the
end user, on this path; per-hop OBO token-exchange is the deferred next layer).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: str
    title: str
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class Review:
    """One item to route to Hrz7 for human review (four-eyes / maker-checker)."""

    action: str
    subject: str
    maker: str
    tenant: str
    summary: str = ""
    severity: str = "medium"
    required_approvals: int = 1
    sod_group: str = ""
    case_ref: str = ""
    citations: tuple[Citation, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "subject": self.subject,
            "maker": self.maker,
            "tenant": self.tenant,
            "summary": self.summary,
            "severity": self.severity,
            "required_approvals": self.required_approvals,
            "sod_group": self.sod_group,
            "case_ref": self.case_ref,
            "citations": [
                {"source_id": c.source_id, "title": c.title, "snippet": c.snippet}
                for c in self.citations
            ],
        }


@dataclass(frozen=True, slots=True)
class ReviewSubmitted:
    """The result of a successful submission: the id Hrz7 assigned and the resulting state."""

    review_id: str
    tenant: str
    state: str
