"""The grounding check is what stops a confident hallucination reaching a policy."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from broker.extract import _ground
from broker.models import Risk

DOC = "Named Insured: Calloway Interiors LLC. Annual revenue: $8,400,000."


def test_unsupported_quote_is_zeroed():
    risk = Risk.model_validate({
        "named_insured": {"value": "Calloway Interiors LLC", "confidence": 0.99,
                          "source_quote": "Named Insured: Calloway Interiors LLC"},
        "mailing_state": {"value": "NJ", "confidence": 0.95,
                          "source_quote": "mailing address in New Jersey"},
        "operations_description": {"value": "fit-out", "confidence": 0.9,
                                   "source_quote": None},
    })
    grounded = _ground(risk, DOC)
    assert grounded.named_insured.confidence == 0.99
    assert grounded.mailing_state.confidence == 0.0      # quote not in document
    assert grounded.operations_description.confidence <= 0.5  # no quote at all


def test_review_queue_flags_low_confidence():
    risk = Risk.model_validate({
        "named_insured": {"value": "X", "confidence": 0.99, "source_quote": None},
        "mailing_state": {"value": None, "confidence": 0.0},
        "operations_description": {"value": "y", "confidence": 0.95},
    })
    assert "mailing_state" in risk.review_queue()
