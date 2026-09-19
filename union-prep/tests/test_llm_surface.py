"""Regression test for the Anthropic SDK surface broker.llm depends on.

broker.llm centralises the exact kwargs it hands to messages.create in
COMPLETE_KWARGS. This is the test that would have caught the 0.x→1.x
removal of temperature= before any API call was attempted — every LLM path
died with a TypeError inside the process instead. When the SDK drifts again,
it turns the next break into a red CI run instead of a dead demo.

Offline by construction: no API key, no network, no skips. The create
signature is read straight from the installed anthropic package.
"""

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anthropic import Anthropic

from broker.llm import COMPLETE_KWARGS


def test_complete_kwargs_are_accepted_by_installed_sdk():
    create_params = inspect.signature(Anthropic().messages.create).parameters
    stale = sorted(k for k in COMPLETE_KWARGS if k not in create_params)
    assert not stale, (
        f"COMPLETE_KWARGS contains kwargs the installed anthropic SDK "
        f"no longer accepts: {stale}. Update broker.llm to match the SDK."
    )


def test_complete_kwargs_is_not_empty():
    # An empty constant would let the signature test above pass vacuously
    # through any SDK drift.
    assert COMPLETE_KWARGS, "COMPLETE_KWARGS must list the create kwargs"
