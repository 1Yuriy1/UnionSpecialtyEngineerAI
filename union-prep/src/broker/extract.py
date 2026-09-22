"""Step 1: an application arrives as an email, a PDF, or a mess. Get a Risk out.

Design note: the model is asked to quote its source text for
every field. That quote is checked against the document before the field is
trusted. A confident hallucination that cannot be found in the source gets its
confidence floored, which is cheap and catches the failure mode that matters
most when a wrong value ends up on a bound policy.
"""

from __future__ import annotations

from .llm import Client
from .models import Extracted, Risk

SYSTEM = """You are an insurance submission analyst at a specialty brokerage.
You read commercial insurance applications (ACORD 125/126/140 forms, broker
emails, loss runs) and extract structured facts.

Rules:
- Never infer a value that is not stated. If the document does not say, use null
  with confidence 0.0.
- For every field, set source_quote to the exact substring of the document the
  value came from, verbatim, under 15 words.
- Confidence reflects how unambiguous the document is, not how plausible the
  value is. A clearly stated revenue is 0.95+. A figure you had to derive from
  two places is 0.6. Anything you guessed is 0.0 with a null value.
- Revenue and limits are in US dollars as a number, not a string."""


def extract_risk(client: Client, document_text: str) -> Risk:
    prompt = f"<application>\n{document_text}\n</application>\n\nExtract the risk."
    risk = client.structured(prompt, Risk, system=SYSTEM)
    return _ground(risk, document_text)


def _ground(risk: Risk, document_text: str) -> Risk:
    """Floor the confidence of any field whose quote is not in the document."""
    haystack = _normalise(document_text)
    for field in risk.__dict__.values():
        if not isinstance(field, Extracted):
            continue
        if field.value is None:
            continue
        if not field.source_quote:
            field.confidence = min(field.confidence, 0.5)
            continue
        if _normalise(field.source_quote) not in haystack:
            field.confidence = 0.0
            field.source_quote = None
    return risk


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())
