# Extraction eval — live run record

This file is written by hand from a recorded run. The suite never runs in CI
and CI never writes this file.

- **Run date:** 2026-09-19 (UTC)
- **Model:** `claude-sonnet-5` — the `BROKER_MODEL` default, no override
- **Command:** `python evals/run_evals.py --suite extraction` (from `union-prep/`),
  exit code 0, `anthropic` SDK 1.7.0
- **Cost:** a few cents, paid once. Reproduce with `export ANTHROPIC_API_KEY=...`
  first; do not wire this into CI.

## What was labelled

Three documents, **27 labelled field checks**: app_001 labels 9 fields,
app_002 labels 8 (no `years_in_business` in its document), app_003 labels 10
(including `effective_date`, which the two clean applications do not state).

## Per-field results

Outcome per check, from the run's own per-field buckets (`correct` / `miss` /
`wrong`):

| Field | app_001 | app_002 | app_003 | Checks | Correct | Miss | Wrong |
|---|---|---|---|---|---|---|---|
| named_insured | ✓ | ✓ | ✓ | 3 | 3 | 0 | 0 |
| mailing_state | ✓ | ✓ | ✓ | 3 | 3 | 0 | 0 |
| naics_code | ✓ | ✓ | ✓ | 3 | 3 | 0 | 0 |
| annual_revenue_usd | ✓ 8,400,000 | ✓ 6,200,000 | ✓ null (label: null) | 3 | 3 | 0 | 0 |
| employee_count | ✓ 31 | ✓ 48 | ✓ 26 | 3 | 3 | 0 | 0 |
| years_in_business | ✓ 13 | — not labelled — | ✓ 11 | 2 | 2 | 0 | 0 |
| limit_requested_usd | ✓ 2,000,000 | ✓ 5,000,000 | ✓ 2,000,000 | 3 | 3 | 0 | 0 |
| deductible_requested_usd | ✓ 10,000 | ✓ 50,000 | ✓ 25,000 | 3 | 3 | 0 | 0 |
| prior_losses_usd_5yr | ✓ 159,500 | ✓ 0 | ✓ 50,000 | 3 | 3 | 0 | 0 |
| effective_date | — | — | ✓ 2026-11-01 | 1 | 1 | 0 | 0 |
| **Total** | | | | **27** | **27** | **0** | **0** |

## The two rates

Each computed from the table above, stated separately, because they fail
differently and cost differently (README, argument 1):

- **wrong-rate** = (unsupported or incorrect fields) / labelled fields
  = 0 / 27 = **0.000**
- **miss-rate** = (unextracted fields) / labelled fields
  = 0 / 27 = **0.000**

Both recompute exactly from the table's Wrong and Miss columns over the 27
labelled checks. No single averaged accuracy figure is reported here and none
should be: an average cannot distinguish a system that misses more and is
wrong less from one that is wrong more and misses less, and only one of those
is safe to put in front of a policy. The runner also emits a mean correct
rate; it is deliberately not reproduced in this file.

## app_003 landmine outcomes (live)

`run_evals.py` prints outcome buckets, not field detail, so the confidence and
review-queue evidence below comes from a supplementary single-case observation
run: app_003 only, same model, same day, one additional API call, same
extraction code path (`extract_risk` → grounding → `review_queue()`).

- **Revenue missing → review queue.** The document has no revenue figure. The
  model returned `annual_revenue_usd: null` at confidence 0.0 — matching the
  label — and the field landed in the human review queue. A missing revenue
  reaches a human; it never reaches the revenue-band filter as a number (the
  invariant behind `test_missing_revenue_does_not_block`).
- **Paraphrase → 0.0 confidence.** `prior_losses_usd_5yr` came back with a
  source quote that is not a verbatim substring of the document, so grounding
  floored the field to 0.0 and dropped the quote, and the field surfaced in
  the review queue. The reviewer sees a gap, not a plausible-looking value.
  The crafted offline test pins this trap on `operations_description`; in
  this live run the same mechanism fired on `prior_losses_usd_5yr`.
- **Contradiction surfaced.** The broker's narrative swears the account went
  five years loss-free; the attached loss run shows $50k of paid claims. The
  extraction took the loss run's $50,000 — the labelled value — and the field
  surfaced for human review at 0.0 confidence.
- **The date conflict did not trip the queue this run.** The document gives
  two conflicting effective dates (US vs EU day/month ordering). The model
  read "Effective 11/01/2026" as 2026-11-01 at 0.95 confidence, which matches
  the label but sailed past the 0.85 review gate. The offline regression test
  pins the queue behaviour when the model is less certain (0.6). Live, the
  ambiguity is resolved confidently when the US-ordered reading happens to be
  chosen — worth knowing before trusting the gate on ambiguous dates.

For completeness: the observation run's review queue held four fields
(`annual_revenue_usd` 0.0, `prior_losses_usd_5yr` 0.0, `years_in_business`
0.55, `limit_requested_usd` 0.8) — every field below the 0.85 confidence gate
was held, plus the narrative/date confidence gap on `years_in_business`.
