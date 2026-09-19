"""Thin wrapper over the Claude API.

Two things this buys us that a bare SDK call does not:
  1. Structured output that actually validates, with a bounded repair loop.
  2. A single place to log every call, which is where evals and cost
     tracking both hang off later.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, TypeVar

from anthropic import Anthropic, APIStatusError
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.environ.get("BROKER_MODEL", "claude-sonnet-5")


class LLMError(RuntimeError):
    pass


class Client:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        self.model = model
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.call_log: list[dict[str, Any]] = []

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.0,
    ) -> str:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                started = time.time()
                resp = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system or "You are a careful assistant.",
                    messages=[{"role": "user", "content": prompt}],
                )
                text = "".join(b.text for b in resp.content if b.type == "text")
                self.call_log.append(
                    {
                        "model": self.model,
                        "latency_s": round(time.time() - started, 2),
                        "input_tokens": resp.usage.input_tokens,
                        "output_tokens": resp.usage.output_tokens,
                    }
                )
                return text
            except APIStatusError as exc:  # transient: back off and retry
                last_err = exc
                if exc.status_code not in (429, 500, 502, 503, 529):
                    raise
                time.sleep(2**attempt)
        raise LLMError(f"exhausted retries: {last_err}")

    def structured(
        self,
        prompt: str,
        schema: type[T],
        system: str = "",
        max_tokens: int = 4000,
    ) -> T:
        """Get a validated pydantic object back, repairing once on failure."""
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        full_system = (
            f"{system}\n\n"
            "Reply with a single JSON object and nothing else. No prose, no "
            "markdown fences. It must validate against this JSON schema:\n"
            f"{schema_json}"
        ).strip()

        raw = self.complete(prompt, system=full_system, max_tokens=max_tokens)
        try:
            return schema.model_validate_json(_strip_fences(raw))
        except (ValidationError, json.JSONDecodeError) as exc:
            log.warning("structured output failed validation, repairing: %s", exc)
            repair = (
                f"This JSON failed validation:\n{raw}\n\n"
                f"The error was:\n{exc}\n\n"
                "Return corrected JSON only."
            )
            fixed = self.complete(repair, system=full_system, max_tokens=max_tokens)
            return schema.model_validate_json(_strip_fences(fixed))


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()
