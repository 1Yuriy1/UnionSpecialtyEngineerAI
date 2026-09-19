# UnionSpecialtyEngineer

> An AI-native specialty insurance brokerage, as a working slice: a language
> model reads commercial insurance applications, a safety harness decides
> when to trust it, and every failure mode is measured — not narrated.

**The pitch.** Specialty insurance is the part of the market with no
off-the-shelf product: a broker reads a messy application, works out which
carriers would actually want the risk, drafts submissions, and normalises
the quotes that come back. This repo builds that core with an AI doing the
reading and code owning the judgment about when the AI can be trusted.
Every extracted field must quote its source verbatim. Shaky fields go to a
human. The rules that matter are hard-coded where the model cannot overrule
them. And the two ways extraction fails — *wrong* and *missed* — are
counted separately.

The point is not the demo. The point is that the hard parts of this problem
are argued about explicitly and the failure modes are measured.

## Quick start

```bash
git clone https://github.com/1Yuriy1/UnionSpecialtyEngineer
cd UnionSpecialtyEngineer/union-prep
pip install -e ".[dev]"

python -m pytest                                    # hard-filter safety rails
python evals/run_evals.py --suite appetite          # offline, no API calls, no key
python -m broker.cli data/samples/app_001_contractor.txt   # the demo, needs a key
python evals/run_evals.py --suite all               # costs a few cents, needs a key
```

## The pipeline

```
application text
      |
      v
 extract.py ------> Risk, every field carrying a confidence
      |             and a verbatim quote from the source
      |
      +--> any field below 0.85 confidence -> human review queue, stop
      |
      v
 appetite.py -----> hard filter (rules) then soft score (model)
      |
      v
 submit.py -------> drafted submission emails, returned, never sent
      |
      v
 submit.py -------> carrier replies normalised into comparable Quotes
```

## What is enforced, mechanically

The claims in this README used to live only in prose. Now they are gates:

- **CI on every push and PR.** `ruff` under the default ruleset, `pytest`
  (18 offline tests), and the 12-check appetite regression, on Python 3.12
  and 3.13. Secret-free and offline by construction; doc-only changes skip
  it via path filters. The gate bites: flipping one appetite expectation
  makes the eval exit 1, and the build goes red.
- **An SDK tripwire.** `tests/test_llm_surface.py` fails CI if the code ever
  passes a keyword argument the installed Anthropic SDK does not accept.
  It exists because the demo previously died on exactly this — a
  `temperature=` kwarg removed in the 1.x SDK — before any API call was
  attempted. The next drift is a red build instead of a dead demo.
- **A trap document.** `data/samples/app_003_messy.txt` is deliberately
  awful, built from the failure modes the arguments below warn about: no
  revenue figure anywhere, two conflicting dates, a loss run that
  contradicts the narrative, and a source quote that is not verbatim.
  Offline regression tests pin the correct handling of every landmine —
  missing revenue reaches a human, never the revenue-band filter.
- **A live eval, written by hand.** `EVALS.md` is recorded by a human after
  a deliberate, paid run. CI never calls the API, never spends money, and
  never writes that file.

## What we measured

First live run — 2026-09-19, `claude-sonnet-5` (the `BROKER_MODEL`
default), full per-field record in
[`union-prep/EVALS.md`](union-prep/EVALS.md):

- **27 labelled checks. Wrong-rate 0/27. Miss-rate 0/27.** Reported
  separately, because they fail differently and cost differently, and an
  average cannot tell you which one you have.

And one honest miss, disclosed on purpose. The eval set contains an
ambiguous date — "11/01/2026", which reads as November 1 in US format and
January 11 in European format. The model picked a reading at 0.95
confidence and sailed past the 0.85 review gate; no human saw it. That
finding lives in `EVALS.md` rather than a footnote, because a system whose
selling point is measurement has to publish its own misses. Converting it
into a catch is the first item on the roadmap.

## Three arguments this code is making

**1. Extraction is not a single accuracy number.**

Every field carries a confidence and the quote it came from. The quote is
checked against the source document; if it isn't there, the confidence is
floored to zero regardless of how sure the model sounded. Then the eval
splits errors into *missed* (said nothing, a human fills it in, cheap) and
*wrong* (said something unsupported, it flows onto a bound policy,
expensive). A system that misses more and is wrong less is the better
system. One averaged accuracy figure cannot tell you which one you have.

**2. Appetite has a hard half and a soft half and they need different machinery.**

State, line, revenue band, capacity, class exclusions are facts. A rule
engine decides them, the decision is explainable, and a model never gets to
overrule it. "They like clean interior contractors but won't touch
residential framing" lives in prose and only a language model reads it
well, so it ranks the eligible carriers and nothing else. Submitting
outside appetite burns the carrier relationship, and the carrier
relationships are the brokerage's actual asset, so the model is not allowed
near that edge.

The hard filter gets unit tests, not evals, and they must pass at 100%
forever. `test_missing_revenue_does_not_block` is the one to read: unknown
must never be treated as out of band.

**3. A submission is a state machine, not an agent loop.**

You market a risk on Monday, one carrier replies Thursday, one never
replies. The work lives for days. So the unit is a persisted, resumable
state machine with explicit gates, not a long-running loop that has to stay
alive and in-context. Here that's a dataclass and a JSON file; in
production it's Temporal or a durable queue. Two gates are deliberate:
low-confidence extraction stops before anything reaches market, and drafted
emails are returned rather than sent.

## Where the eval cases come from

The labelled cases in `evals/cases.yaml` are hand-written here. In a real
brokerage you get them free: instrument the human review queue, and every
correction a broker makes to an extracted field is a labelled example. That
is the flywheel, and it's the reason to build the review UI in week one
rather than week ten.

## Further plans

Each item converts a documented weakness into a documented strength:

1. **Deterministic field validators.** An ambiguous numeric date — both day
   and month ≤ 12, so the string reads validly either way — goes to review
   regardless of the model's confidence. Code decides, not the model. The
   same pattern extends to currency sanity ranges and NAICS format checks.
2. **Read-only tool use.** A cross-document reconciliation step that
   surfaces conflicting values (narrative vs. certificate) as data instead
   of letting the model resolve them silently, and a NAICS lookup so
   industry codes are resolved from a source of truth rather than recalled.
   The agent may query; the pipeline applies the rules.
3. **Runtime resilience.** A fail-fast credential pre-flight probe, an
   explicit retry policy (transient 5xx retries; 4xx never does), and
   stage-level resume through the existing `.state/` directory — the cheap
   cousin of the durable state machine below.
4. **The durable state machine.** Temporal or Postgres plus a worker behind
   the submission state machine (argument 3), so a submission that lives
   for days survives a process restart.

## What is deliberately missing

Real ACORD PDF parsing, carrier portal and API integrations, bind and
policy issuance, surplus lines tax and stamping fee calculation, premium
and commission accounting, a human review interface, and any notion of who
is licensed to do what. Each of those is real work, and none of them would
make the argument any clearer.
