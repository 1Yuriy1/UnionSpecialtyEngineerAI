"""app_003 is the deliberately messy submission: no revenue figure, two
conflicting effective dates, a narrative that lies about losses, and room
for paraphrased evidence.

These tests pin the mechanics that keep its landmines in front of a human
instead of on a bound policy. The extraction is crafted by hand -- what the
extraction rules tell the model to return for this document -- and run
through the same _ground -> review_queue -> hard_filter path the pipeline
uses. No API, no network.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from broker.appetite import hard_filter
from broker.extract import _ground
from broker.models import LineOfBusiness, Risk, Submission, SubmissionState
from broker.pipeline import Broker, load_carriers

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "data" / "samples" / "app_003_messy.txt").read_text()

# A paraphrase of the operations line that appears nowhere in the document --
# the verbatim-quote rule is exactly what this field violates.
PARAPHRASE = "shop specializes in high-precision CNC milling and turning"


def app_003_extraction() -> Risk:
    """The honest extraction for app_003, landmines and all.

    Each landmine and the response the extraction rules call for:
      revenue absent         -> null at confidence 0.0, no quote
      two effective dates    -> narrative value, confidence dropped for conflict
      loss run vs narrative  -> loss run total, confidence dropped for conflict
      paraphrased quote      -> stated as if verbatim; grounding catches it
    """
    return _ground(
        Risk.model_validate({
            "named_insured": {
                "value": "Talcott Precision Manufacturing LLC",
                "confidence": 0.98,
                "source_quote": "Talcott Precision Manufacturing LLC",
            },
            "mailing_state": {"value": "OH", "confidence": 0.97,
                              "source_quote": "Cleveland OH 44114"},
            "operations_description": {
                "value": "precision CNC machining of aluminum and titanium components",
                "confidence": 0.92,
                "source_quote": PARAPHRASE,
            },
            "naics_code": {"value": "332710", "confidence": 0.95,
                           "source_quote": "NAICS: 332710"},
            "annual_revenue_usd": {"value": None, "confidence": 0.0},
            "employee_count": {"value": 26, "confidence": 0.95,
                               "source_quote": "Employees: 26 full time"},
            "years_in_business": {"value": 11, "confidence": 0.7,
                                  "source_quote": "in business since 2015"},
            "lines_requested": [LineOfBusiness.GENERAL_LIABILITY, LineOfBusiness.PROPERTY],
            "limit_requested_usd": {"value": 2_000_000, "confidence": 0.9,
                                    "source_quote": "$2M/$4M"},
            "deductible_requested_usd": {"value": 25_000, "confidence": 0.95,
                                         "source_quote": "Requested deductible: $25,000"},
            "effective_date": {"value": date(2026, 11, 1), "confidence": 0.6,
                               "source_quote": "Effective 11/01/2026"},
            "prior_losses_usd_5yr": {"value": 50_000.0, "confidence": 0.7,
                                     "source_quote": "closed $38,000"},
            "notable_hazards": [
                "sprinkler water damage (2023)",
                "customer slip-and-fall (2024)",
            ],
        }),
        DOC,
    )


def test_missing_revenue_is_missing_not_out_of_band():
    """The document has no revenue figure. Null at 0.0 must land in the review
    queue as missing -- the invariant behind test_missing_revenue_does_not_block:
    unknown is not out-of-band, so it must not trip the revenue band filter."""
    risk = app_003_extraction()

    assert risk.annual_revenue_usd.value is None
    assert "annual_revenue_usd" in risk.review_queue()

    carriers = {c.carrier_id: c for c in load_carriers(ROOT / "data" / "carriers.yaml")}
    assert hard_filter(risk, carriers["HALLMARK_E&S"]) == []


def test_paraphrased_quote_floors_to_zero():
    """The quote is a paraphrase that appears nowhere in the document, so
    grounding floors the field to 0.0 and drops the quote: the reviewer sees
    a gap instead of a plausible-looking value."""
    risk = app_003_extraction()

    assert risk.operations_description.confidence == 0.0
    assert risk.operations_description.source_quote is None


def test_loss_contradiction_surfaces_for_human_review():
    """The narrative swears the account is loss-free; the attached loss run
    shows $50k of paid claims. The extraction takes the loss run at reduced
    confidence, and the conflict lands in front of a human."""
    risk = app_003_extraction()

    assert risk.prior_losses_usd_5yr.value == 50_000.0
    assert "prior_losses_usd_5yr" in risk.review_queue()


def test_effective_date_conflict_surfaces_for_human_review():
    """Narrative says 11/01/2026, the renewal certificate says 01/11/2026 --
    same digits, opposite reading depending on day/month convention. Whatever
    the model picks, the ambiguity must not sail through unreviewed."""
    risk = app_003_extraction()

    assert risk.effective_date.value == date(2026, 11, 1)
    assert "effective_date" in risk.review_queue()


class _ReplayClient:
    """Returns the crafted extraction instead of calling the API."""

    def structured(self, prompt: str, schema: type, system: str = "") -> Risk:
        return app_003_extraction()


def test_intake_holds_app_003_for_human_review(tmp_path):
    """End to end through the real pipeline gate: the queue is non-empty, so
    intake holds the submission for a human and never reaches marketing."""
    broker = Broker(_ReplayClient(), [], state_dir=tmp_path)
    sub = Submission(
        submission_id="app_003",
        received_at=date(2026, 9, 19),
        source_text=DOC,
    )

    broker.intake(sub)

    assert sub.state is SubmissionState.NEEDS_HUMAN
    assert "held for review" in sub.audit[-1]
    assert "annual_revenue_usd" in sub.audit[-1]
    assert "prior_losses_usd_5yr" in sub.audit[-1]
