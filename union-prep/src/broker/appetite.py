"""Step 2: decide which carriers want this risk.

The core argument of this repo: appetite has a hard half and a soft half, and
they need different machinery.

  Hard half  - licence, state, line, revenue band, limit capacity, class
               exclusions. These are facts. A rule engine decides them, the
               decision is explainable, and a model is never allowed to
               overrule it. Submitting outside appetite burns the carrier
               relationship, which is the brokerage's actual asset.

  Soft half  - "they like clean contractors but hate anything touching
               residential framing". This lives in prose and only a language
               model reads it well. It ranks; it never unblocks.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .llm import Client
from .models import AppetiteMatch, CarrierAppetite, Risk


class _SoftScore(BaseModel):
    carrier_id: str
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str]


SYSTEM = """You are a wholesale broker deciding where to place a risk.
For each carrier, score 0-1 how likely their underwriters are to quote this
account based on their appetite notes and the operations described.

Judge fit of the narrative only: class of business, hazard profile, loss
history, account quality. Ignore state, licensing, revenue bands and limits,
which have already been checked.

Be blunt. Most carriers are a poor fit for most risks. Scores above 0.7 should
be rare and mean you would actually pick up the phone."""


def hard_filter(risk: Risk, carrier: CarrierAppetite) -> list[str]:
    """Return blocking reasons. Empty list means the carrier is eligible."""
    blocks: list[str] = []

    state = (risk.mailing_state.value or "").upper()
    if "*" not in carrier.states and state and state not in carrier.states:
        blocks.append(f"not licensed/appointed in {state}")

    if risk.lines_requested and not set(risk.lines_requested) & set(carrier.lines):
        wanted = ", ".join(line.value for line in risk.lines_requested)
        blocks.append(f"does not write {wanted}")

    rev = risk.annual_revenue_usd.value if risk.annual_revenue_usd else None
    if rev is not None:
        if carrier.min_revenue_usd and rev < carrier.min_revenue_usd:
            blocks.append(f"revenue ${rev:,.0f} below minimum")
        if carrier.max_revenue_usd and rev > carrier.max_revenue_usd:
            blocks.append(f"revenue ${rev:,.0f} above maximum")

    limit = risk.limit_requested_usd.value if risk.limit_requested_usd else None
    if limit is not None and carrier.max_limit_usd and limit > carrier.max_limit_usd:
        blocks.append(f"limit ${limit:,.0f} exceeds capacity")

    naics = risk.naics_code.value if risk.naics_code else None
    if naics:
        for prefix in carrier.excluded_naics_prefixes:
            if naics.startswith(prefix):
                blocks.append(f"class {naics} excluded")
                break

    ops = (risk.operations_description.value or "").lower()
    hazards = " ".join(risk.notable_hazards).lower()
    for keyword in carrier.excluded_keywords:
        if keyword.lower() in ops or keyword.lower() in hazards:
            blocks.append(f"excluded exposure: {keyword}")

    return blocks


def match(
    client: Client,
    risk: Risk,
    carriers: list[CarrierAppetite],
    submit_threshold: float = 0.55,
) -> list[AppetiteMatch]:
    eligible: list[CarrierAppetite] = []
    results: list[AppetiteMatch] = []

    for carrier in carriers:
        blocks = hard_filter(risk, carrier)
        if blocks:
            results.append(
                AppetiteMatch(
                    carrier_id=carrier.carrier_id,
                    carrier_name=carrier.carrier_name,
                    score=0.0,
                    decision="skip",
                    reasons=["blocked before underwriting review"],
                    hard_blocks=blocks,
                )
            )
        else:
            eligible.append(carrier)

    for soft in _score_soft(client, risk, eligible):
        carrier = next(c for c in eligible if c.carrier_id == soft.carrier_id)
        decision = "submit" if soft.score >= submit_threshold else "maybe"
        results.append(
            AppetiteMatch(
                carrier_id=carrier.carrier_id,
                carrier_name=carrier.carrier_name,
                score=soft.score,
                decision=decision,
                reasons=soft.reasons,
            )
        )

    results.sort(key=lambda m: m.score, reverse=True)
    return results


class _SoftScores(BaseModel):
    scores: list[_SoftScore]


def _score_soft(
    client: Client, risk: Risk, carriers: list[CarrierAppetite]
) -> list[_SoftScore]:
    if not carriers:
        return []

    carrier_block = "\n\n".join(
        f"<carrier id={c.carrier_id}>\n"
        f"name: {c.carrier_name}\n"
        f"prefers: {', '.join(c.preferred_keywords) or 'n/a'}\n"
        f"notes: {c.notes}\n"
        f"</carrier>"
        for c in carriers
    )
    risk_block = (
        f"operations: {risk.operations_description.value}\n"
        f"hazards: {', '.join(risk.notable_hazards) or 'none noted'}\n"
        f"years in business: {risk.years_in_business.value if risk.years_in_business else 'unknown'}\n"
        f"5yr losses: {risk.prior_losses_usd_5yr.value if risk.prior_losses_usd_5yr else 'unknown'}"
    )
    prompt = (
        f"<risk>\n{risk_block}\n</risk>\n\n"
        f"<carriers>\n{carrier_block}\n</carriers>\n\n"
        "Score every carrier listed."
    )
    return client.structured(prompt, _SoftScores, system=SYSTEM).scores
