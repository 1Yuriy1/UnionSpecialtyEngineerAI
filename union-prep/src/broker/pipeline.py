"""The state machine that ties the steps together.

A submission lives for days or weeks: you market it on Monday, a carrier
replies on Thursday, another never replies at all. So the unit of work is a
persisted state machine with resumable steps, not one long agent loop that
has to stay alive. In production this is Temporal or a durable queue; here it
is a dataclass and a JSON file, which is enough to show the shape.

Two gates are deliberate:
  - low-confidence extraction stops for a human before anything goes to market
  - drafted emails are returned, never sent
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .appetite import match as match_carriers
from .extract import extract_risk
from .llm import Client
from .models import CarrierAppetite, Submission, SubmissionState
from .submit import DraftEmail, draft_submission, parse_reply


def load_carriers(path: str | Path) -> list[CarrierAppetite]:
    raw = yaml.safe_load(Path(path).read_text())
    return [CarrierAppetite.model_validate(c) for c in raw["carriers"]]


class Broker:
    def __init__(
        self,
        client: Client,
        carriers: list[CarrierAppetite],
        state_dir: str | Path = ".state",
    ):
        self.client = client
        self.carriers = carriers
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)

    # --- persistence -----------------------------------------------------

    def save(self, sub: Submission) -> None:
        path = self.state_dir / f"{sub.submission_id}.json"
        path.write_text(sub.model_dump_json(indent=2))

    def load(self, submission_id: str) -> Submission:
        path = self.state_dir / f"{submission_id}.json"
        return Submission.model_validate(json.loads(path.read_text()))

    # --- steps -----------------------------------------------------------

    def intake(self, sub: Submission) -> Submission:
        sub.risk = extract_risk(self.client, sub.source_text)
        queue = sub.risk.review_queue()
        if queue:
            sub.state = SubmissionState.NEEDS_HUMAN
            sub.log(f"held for review: {', '.join(queue)}")
        else:
            sub.state = SubmissionState.EXTRACTED
            sub.log("extraction clean")
        self.save(sub)
        return sub

    def market(self, sub: Submission, override_review: bool = False) -> list[DraftEmail]:
        if sub.risk is None:
            raise ValueError("extract before marketing")
        if sub.state is SubmissionState.NEEDS_HUMAN and not override_review:
            raise ValueError(
                f"fields need review: {', '.join(sub.risk.review_queue())}. "
                "Pass override_review=True once a human has signed off."
            )

        sub.matches = match_carriers(self.client, sub.risk, self.carriers)
        targets = [m for m in sub.matches if m.decision == "submit"]
        sub.log(
            f"{len(targets)} of {len(self.carriers)} carriers in appetite: "
            + ", ".join(m.carrier_name for m in targets)
        )

        drafts: list[DraftEmail] = []
        by_id = {c.carrier_id: c for c in self.carriers}
        for m in targets:
            drafts.append(
                draft_submission(self.client, sub.risk, by_id[m.carrier_id], m.reasons)
            )

        sub.state = SubmissionState.MARKETED
        self.save(sub)
        return drafts

    def ingest_reply(self, sub: Submission, carrier_id: str, reply: str) -> Submission:
        quote = parse_reply(self.client, carrier_id, reply)
        sub.quotes.append(quote)
        sub.log(f"{carrier_id}: {quote.outcome}")
        if any(q.comparable for q in sub.quotes):
            sub.state = SubmissionState.QUOTES_IN
        self.save(sub)
        return sub

    def summarise(self, sub: Submission) -> str:
        best = sub.best_quote()
        lines = [f"Submission {sub.submission_id} [{sub.state.value}]"]
        if sub.risk:
            lines.append(f"  Insured: {sub.risk.named_insured.value}")
        for q in sub.quotes:
            if q.comparable:
                lines.append(
                    f"  {q.carrier_id}: ${q.premium_usd:,.0f} "
                    f"@ ${q.limit_usd:,.0f} limit"
                    + (f" ({len(q.subjectivities)} subjectivities)" if q.subjectivities else "")
                )
            else:
                lines.append(f"  {q.carrier_id}: {q.outcome} - {q.decline_reason or ''}")
        if best:
            lines.append(f"  Best: {best.carrier_id} at ${best.premium_usd:,.0f}")
        return "\n".join(lines)
