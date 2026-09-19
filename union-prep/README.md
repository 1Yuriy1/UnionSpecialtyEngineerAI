# Specialty brokerage, end to end

A working slice of what an AI-native specialty insurance brokerage does:
read an application, decide which carriers want the risk, draft the
submissions, normalise the replies, and evaluate every step of it.

Four toy carriers, two real-shaped submissions, and an eval harness. The point
is not the demo. The point is that the hard parts of this problem are
argued about explicitly and the failure modes are measured.

```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...

python -m pytest                                    # hard-filter safety rails
python evals/run_evals.py --suite appetite          # offline, no API calls
python -m broker.cli data/samples/app_001_contractor.txt
python evals/run_evals.py --suite all               # costs a few cents
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

## Three arguments this code is making

**1. Extraction is not a single accuracy number.**

Every field carries a confidence and the quote it came from. The quote is
checked against the source document; if it isn't there, the confidence is
floored to zero regardless of how sure the model sounded. Then the eval
splits errors into *missed* (said nothing, a human fills it in, cheap) and
*wrong* (said something unsupported, it flows onto a bound policy,
expensive). A system that misses more and is wrong less is the better system.
One averaged accuracy figure cannot tell you which one you have.

**2. Appetite has a hard half and a soft half and they need different machinery.**

State, line, revenue band, capacity, class exclusions are facts. A rule
engine decides them, the decision is explainable, and a model never gets to
overrule it. "They like clean interior contractors but won't touch
residential framing" lives in prose and only a language model reads it well,
so it ranks the eligible carriers and nothing else. Submitting outside
appetite burns the carrier relationship, and the carrier relationships are
the brokerage's actual asset, so the model is not allowed near that edge.

The hard filter gets unit tests, not evals, and they must pass at 100%
forever. `test_missing_revenue_does_not_block` is the one to read: unknown
must never be treated as out of band.

**3. A submission is a state machine, not an agent loop.**

You market a risk on Monday, one carrier replies Thursday, one never replies.
The work lives for days. So the unit is a persisted, resumable state machine
with explicit gates, not a long-running loop that has to stay alive and
in-context. Here that's a dataclass and a JSON file; in production it's
Temporal or a durable queue. Two gates are deliberate: low-confidence
extraction stops before anything reaches market, and drafted emails are
returned rather than sent.

## Where the eval cases come from

The labelled cases in `evals/cases.yaml` are hand-written here. In a real
brokerage you get them free: instrument the human review queue, and every
correction a broker makes to an extracted field is a labelled example. That
is the flywheel, and it's the reason to build the review UI in week one
rather than week ten.

## What's deliberately missing

Real ACORD PDF parsing, carrier portal and API integrations, bind and policy
issuance, surplus lines tax and stamping fee calculation, premium and
commission accounting, and any notion of who is licensed to do what. Each of
those is real work and none of them would make the argument any clearer.
