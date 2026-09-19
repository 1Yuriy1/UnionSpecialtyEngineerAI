"""The part that matters.

Three kinds of eval, because the three steps fail in different ways and a
single accuracy number would hide all of it.

1. Extraction - deterministic. Compare each field to a labelled answer.
   Report per-field accuracy, not a document average, because one wrong
   revenue figure matters and one wrong employee count does not.
   Track two error classes separately:
     miss        - said null when the document had a value (cheap: a human
                   fills it in)
     wrong       - said something the document does not support (expensive:
                   it flows onto a policy)
   A system that misses more and is wrong less is the better system, and an
   average accuracy score cannot tell you that.

2. Appetite - regression, not accuracy. The hard filter must never block an
   eligible carrier and must always block an ineligible one; that is a unit
   test and it should be 100%. The soft score is graded on rank correlation
   against a broker's ordering, because the exact number is meaningless and
   the order is the product.

3. Drafts - LLM judge against a rubric, with the known caveats: the judge is
   graded too (agreement with human labels on a held-out set), the rubric is
   specific rather than "is this good", and the judge never sees which
   version produced which draft.

Run:  python evals/run_evals.py --suite all
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from broker.appetite import hard_filter
from broker.extract import extract_risk
from broker.llm import Client
from broker.models import Extracted, Risk
from broker.pipeline import load_carriers

ROOT = Path(__file__).resolve().parents[1]
CASES = yaml.safe_load((ROOT / "evals" / "cases.yaml").read_text())

JUDGE_SYSTEM = """You grade submission emails written by a wholesale broker to
a carrier underwriter. Score each criterion 0 or 1, strictly.

factual      - every claim appears in the risk data provided. Any invented
               number, name or date scores 0.
brevity      - body under 150 words.
appetite_fit - names a specific reason this carrier in particular would want
               this account, not a generic pitch.
loss_candour - if prior losses exist in the risk data, they are disclosed.
               If there are none, score 1.
subject_line - follows NAMED INSURED | LINE | EFFECTIVE DATE.

Return JSON: {"scores": {...}, "failures": ["..."]}"""


def _field_pairs(risk: Risk) -> dict[str, Extracted]:
    return {k: v for k, v in risk.__dict__.items() if isinstance(v, Extracted)}


def eval_extraction(client: Client) -> dict:
    per_field: dict[str, dict[str, int]] = {}
    confidences_right: list[float] = []
    confidences_wrong: list[float] = []

    for case in CASES["extraction"]:
        text = (ROOT / "data" / "samples" / case["file"]).read_text()
        risk = extract_risk(client, text)
        got = _field_pairs(risk)

        for field, expected in case["expect"].items():
            bucket = per_field.setdefault(field, {"correct": 0, "miss": 0, "wrong": 0})
            actual = got.get(field)
            value = actual.value if actual else None

            if _equal(value, expected):
                bucket["correct"] += 1
                if actual:
                    confidences_right.append(actual.confidence)
            elif value is None:
                bucket["miss"] += 1
            else:
                bucket["wrong"] += 1
                if actual:
                    confidences_wrong.append(actual.confidence)

    total = sum(sum(b.values()) for b in per_field.values())
    wrong = sum(b["wrong"] for b in per_field.values())
    missed = sum(b["miss"] for b in per_field.values())

    return {
        "fields_checked": total,
        "correct_rate": round((total - wrong - missed) / total, 3) if total else 0,
        "wrong_rate": round(wrong / total, 3) if total else 0,
        "miss_rate": round(missed / total, 3) if total else 0,
        "mean_confidence_when_right": _mean(confidences_right),
        "mean_confidence_when_wrong": _mean(confidences_wrong),
        "per_field": per_field,
    }


def eval_appetite() -> dict:
    """Pure regression. No model call, so this runs on every commit in CI."""
    carriers = {c.carrier_id: c for c in load_carriers(ROOT / "data" / "carriers.yaml")}
    failures: list[str] = []
    checks = 0

    for case in CASES["appetite"]:
        risk = Risk.model_validate(case["risk"])
        for carrier_id, should_block in case["expect_blocked"].items():
            checks += 1
            blocks = hard_filter(risk, carriers[carrier_id])
            if bool(blocks) != should_block:
                failures.append(
                    f"{case['name']} / {carrier_id}: "
                    f"expected blocked={should_block}, got {blocks or 'eligible'}"
                )

    return {
        "checks": checks,
        "passed": checks - len(failures),
        "failures": failures,
    }


def eval_drafts(client: Client) -> dict:
    from broker.submit import draft_submission

    carriers = {c.carrier_id: c for c in load_carriers(ROOT / "data" / "carriers.yaml")}
    rows = []
    for case in CASES["drafts"]:
        text = (ROOT / "data" / "samples" / case["file"]).read_text()
        risk = extract_risk(client, text)
        carrier = carriers[case["carrier_id"]]
        draft = draft_submission(client, risk, carrier, case["reasons"])

        verdict = client.complete(
            f"<risk>\n{risk.model_dump_json()}\n</risk>\n\n"
            f"<email>\nSubject: {draft.subject}\n\n{draft.body}\n</email>",
            system=JUDGE_SYSTEM,
        )
        rows.append({"case": case["name"], "verdict": _loads(verdict)})

    criteria = ["factual", "brevity", "appetite_fit", "loss_candour", "subject_line"]
    summary = {
        c: _mean([r["verdict"].get("scores", {}).get(c, 0) for r in rows])
        for c in criteria
    }
    return {"by_criterion": summary, "detail": rows}


def _equal(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 0.01
        except (TypeError, ValueError):
            return False
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return a == b


def _mean(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 3) if xs else None


def _loads(text: str) -> dict:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"scores": {}, "failures": ["judge returned unparseable output"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="appetite", choices=["extraction", "appetite", "drafts", "all"])
    args = ap.parse_args()

    results: dict = {}
    if args.suite in ("appetite", "all"):
        results["appetite"] = eval_appetite()
    if args.suite in ("extraction", "all"):
        results["extraction"] = eval_extraction(Client())
    if args.suite in ("drafts", "all"):
        results["drafts"] = eval_drafts(Client())

    print(json.dumps(results, indent=2))
    failed = results.get("appetite", {}).get("failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
