"""Steps 3 and 4: send the risk to market, then read what comes back.

Nothing here sends mail. draft_submission returns an object; a human or a
queue decides whether it goes out. Any agent with send authority needs an
approval gate in front of it — the gate is the product, not a limitation.
"""

from __future__ import annotations

from pydantic import BaseModel

from .llm import Client
from .models import CarrierAppetite, Quote, Risk

SUBMISSION_SYSTEM = """You write submission emails from a wholesale broker to a
carrier underwriter.

House style:
- Subject line: NAMED INSURED | LINE | EFFECTIVE DATE
- Under 150 words. Underwriters triage dozens of these a day.
- Lead with the class of business, revenue and limit requested.
- Name the one thing that makes this account attractive to THIS carrier,
  drawn from their appetite notes.
- Disclose loss history plainly. Hiding it and having it surface later costs
  the relationship.
- Never state a fact that is not in the risk data. No filler adjectives.
- Sign off as "Union Specialty" with no invented names or phone numbers."""

QUOTE_SYSTEM = """You read underwriter replies and normalise them.

A reply is one of: quoted (a price is stated), declined, more_info_needed, or
unclear. Do not infer a premium that is not written down. Subjectivities are
the conditions attached to the quote, for example a signed application or a
satisfactory loss run. Copy the excerpt you based the outcome on."""


class DraftEmail(BaseModel):
    subject: str
    body: str


def draft_submission(
    client: Client, risk: Risk, carrier: CarrierAppetite, match_reasons: list[str]
) -> DraftEmail:
    prompt = (
        f"<carrier>\n{carrier.carrier_name}\n"
        f"appetite notes: {carrier.notes}\n"
        f"</carrier>\n\n"
        f"<why_we_picked_them>\n{'; '.join(match_reasons)}\n</why_we_picked_them>\n\n"
        f"<risk>\n{risk.model_dump_json(indent=2)}\n</risk>\n\n"
        "Draft the submission email."
    )
    return client.structured(prompt, DraftEmail, system=SUBMISSION_SYSTEM)


def parse_reply(client: Client, carrier_id: str, reply_text: str) -> Quote:
    prompt = f"<reply>\n{reply_text}\n</reply>\n\nNormalise this reply."
    quote = client.structured(prompt, Quote, system=QUOTE_SYSTEM)
    quote.carrier_id = carrier_id  # never trust the model for the join key
    return quote
