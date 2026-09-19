"""Domain models for a specialty insurance submission.

Field names follow ACORD/broker convention where one exists, so that anyone
who has worked in the industry recognises them immediately.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class LineOfBusiness(str, Enum):
    GENERAL_LIABILITY = "general_liability"
    PROPERTY = "property"
    PROFESSIONAL_LIABILITY = "professional_liability"
    CYBER = "cyber"
    EXCESS = "excess"
    INLAND_MARINE = "inland_marine"


class Extracted[T](BaseModel):
    """A value pulled out of an unstructured document, with its evidence.

    Every extracted field carries a confidence and the span of source text it
    came from. This is what makes human review cheap: a reviewer checks the
    six low-confidence fields, not all sixty.
    """

    value: T | None
    confidence: float = Field(ge=0.0, le=1.0)
    source_quote: str | None = None
    source_page: int | None = None

    @property
    def needs_review(self) -> bool:
        return self.value is None or self.confidence < 0.85


class Risk(BaseModel):
    """The insured and what they want covered."""

    named_insured: Extracted[str]
    mailing_state: Extracted[str]
    operations_description: Extracted[str]
    naics_code: Extracted[str] | None = None
    annual_revenue_usd: Extracted[float] | None = None
    employee_count: Extracted[int] | None = None
    years_in_business: Extracted[int] | None = None
    lines_requested: list[LineOfBusiness] = Field(default_factory=list)
    limit_requested_usd: Extracted[float] | None = None
    deductible_requested_usd: Extracted[float] | None = None
    effective_date: Extracted[date] | None = None
    prior_losses_usd_5yr: Extracted[float] | None = None
    notable_hazards: list[str] = Field(default_factory=list)

    def review_queue(self) -> list[str]:
        """Field names a human should eyeball before this goes to market."""
        out: list[str] = []
        for name, field in self.__dict__.items():
            if isinstance(field, Extracted) and field.needs_review:
                out.append(name)
        return out


class CarrierAppetite(BaseModel):
    """What one insurer will and will not look at.

    In the real world this lives in a broker's head, in a PDF appetite guide,
    and in the memory of whoever last got declined. Encoding it is most of
    the value of an AI-native brokerage.
    """

    carrier_id: str
    carrier_name: str
    admitted: bool
    lines: list[LineOfBusiness]
    states: list[str]  # "*" means countrywide
    min_revenue_usd: float | None = None
    max_revenue_usd: float | None = None
    max_limit_usd: float | None = None
    excluded_naics_prefixes: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    preferred_keywords: list[str] = Field(default_factory=list)
    submission_channel: Literal["email", "portal", "api"] = "email"
    submission_email: str | None = None
    typical_turnaround_days: int = 5
    notes: str = ""


class AppetiteMatch(BaseModel):
    carrier_id: str
    carrier_name: str
    score: float = Field(ge=0.0, le=1.0)
    decision: Literal["submit", "maybe", "skip"]
    reasons: list[str]
    hard_blocks: list[str] = Field(default_factory=list)


class Quote(BaseModel):
    """A carrier's response, normalised for comparison."""

    carrier_id: str
    outcome: Literal["quoted", "declined", "more_info_needed", "unclear"]
    premium_usd: float | None = None
    limit_usd: float | None = None
    deductible_usd: float | None = None
    subjectivities: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    valid_until: date | None = None
    decline_reason: str | None = None
    information_requested: list[str] = Field(default_factory=list)
    raw_excerpt: str = ""

    @property
    def comparable(self) -> bool:
        return self.outcome == "quoted" and self.premium_usd is not None


class SubmissionState(str, Enum):
    RECEIVED = "received"
    EXTRACTED = "extracted"
    NEEDS_HUMAN = "needs_human"
    MARKETED = "marketed"
    QUOTES_IN = "quotes_in"
    PRESENTED = "presented"
    BOUND = "bound"
    DEAD = "dead"


class Submission(BaseModel):
    """The unit of work. One of these lives for days or weeks."""

    submission_id: str
    received_at: date
    source_text: str
    state: SubmissionState = SubmissionState.RECEIVED
    risk: Risk | None = None
    matches: list[AppetiteMatch] = Field(default_factory=list)
    quotes: list[Quote] = Field(default_factory=list)
    audit: list[str] = Field(default_factory=list)

    def log(self, event: str) -> None:
        self.audit.append(event)

    def best_quote(self) -> Quote | None:
        priced = [q for q in self.quotes if q.comparable]
        if not priced:
            return None
        return min(priced, key=lambda q: q.premium_usd or float("inf"))
