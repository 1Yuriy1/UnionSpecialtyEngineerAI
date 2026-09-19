"""The hard filter is the safety rail. It gets unit tests, not evals."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from broker.appetite import hard_filter
from broker.models import LineOfBusiness, Risk
from broker.pipeline import load_carriers

CARRIERS = {c.carrier_id: c for c in load_carriers(
    Path(__file__).resolve().parents[1] / "data" / "carriers.yaml"
)}


def make_risk(**kw) -> Risk:
    base = {
        "named_insured": {"value": "Test Co", "confidence": 1.0},
        "mailing_state": {"value": "NY", "confidence": 1.0},
        "operations_description": {"value": "office", "confidence": 1.0},
        "lines_requested": [LineOfBusiness.GENERAL_LIABILITY],
    }
    base.update(kw)
    return Risk.model_validate(base)


def test_unlicensed_state_blocks():
    risk = make_risk(mailing_state={"value": "TX", "confidence": 1.0})
    assert any("licensed" in b for b in hard_filter(risk, CARRIERS["KEYSTONE_ADM"]))


def test_countrywide_carrier_passes_any_state():
    risk = make_risk(mailing_state={"value": "TX", "confidence": 1.0})
    assert hard_filter(risk, CARRIERS["HALLMARK_E&S"]) == []


def test_excluded_class_blocks():
    risk = make_risk(naics_code={"value": "238350", "confidence": 1.0})
    assert any("excluded" in b for b in hard_filter(risk, CARRIERS["KEYSTONE_ADM"]))


def test_limit_over_capacity_blocks():
    risk = make_risk(limit_requested_usd={"value": 9_000_000, "confidence": 1.0})
    assert any("capacity" in b for b in hard_filter(risk, CARRIERS["HALLMARK_E&S"]))


def test_keyword_exclusion_reads_hazards_not_just_operations():
    risk = make_risk(notable_hazards=["crane use on site"])
    assert any("crane" in b for b in hard_filter(risk, CARRIERS["HALLMARK_E&S"]))


def test_missing_revenue_does_not_block():
    """Unknown must not be treated as out of band. A missing field sends the
    submission to a human, it does not silently kill a carrier."""
    risk = make_risk(annual_revenue_usd=None)
    assert hard_filter(risk, CARRIERS["HALLMARK_E&S"]) == []


@pytest.mark.parametrize("revenue,blocked", [(100_000, True), (5_000_000, False), (90_000_000, True)])
def test_revenue_band(revenue, blocked):
    risk = make_risk(annual_revenue_usd={"value": revenue, "confidence": 1.0})
    assert bool(hard_filter(risk, CARRIERS["HALLMARK_E&S"])) is blocked
