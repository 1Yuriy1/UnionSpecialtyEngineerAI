# Master plan: Union Specialty founding engineer

Keep this file private, or strip it before pushing the repo public. Split it
into `PLAN.md` (yours) and a clean public README if you share the repo with
them.

The whole strategy in one line: **every other candidate will know agents and
not know insurance.** Domain fluency plus a working demo of their product is
a combination almost nobody brings to a pre-seed interview, and it is
achievable in about three weeks of evenings.

---

## Week 1 — domain

Goal: talk to a broker for ten minutes without them noticing you learned this
last Tuesday.

- [ ] The lifecycle cold: submission → underwriter review → quote → bind →
      policy issuance → endorsement → renewal. Who touches each step, how long
      it takes today, where the weeks go.
- [ ] Admitted vs. non-admitted (E&S / surplus lines). Why specialty risks end
      up non-admitted, what surplus lines tax and stamping fees are, why the
      diligent search requirement exists. This is the single highest-signal
      thing to know.
- [ ] Retail broker vs. wholesale broker vs. MGA vs. carrier. Work out which
      one Union Specialty actually is from the posting. Ask them to confirm in
      the first call — it's a great opening question.
- [ ] Read real ACORD 125, 126 and 140 forms. Find blank ones online. Notice
      how much is free text, how much is checkbox, and where a human would go
      wrong.
- [ ] Loss runs, schedules of values, binders, subjectivities, quote
      comparison. What "bound" legally means and why getting it wrong is a
      claim against the brokerage.
- [ ] Economics: commission is roughly 10–15% of premium, sometimes plus a
      contingent. Work out what their revenue per placed policy looks like and
      what "doubling monthly" would have to mean in absolute terms.
- [ ] Skim the appetite guides three or four real E&S carriers publish. That's
      what `data/carriers.yaml` is imitating.

## Week 2 — build

The repo in this directory is the skeleton. Make it yours.

- [ ] Run it, break it, rewrite the parts you disagree with. If you disagree
      with the hard-filter-plus-soft-score split, say so in the interview and
      defend the alternative. A candidate with an opinion beats one with a
      demo.
- [ ] Swap the toy carriers for four real E&S carriers and their published
      appetite. Makes the demo land very differently.
- [ ] Add real ACORD PDF ingestion. Scanned forms, checkboxes, tables. This is
      where most of the actual difficulty lives.
- [ ] Add a fifth sample that is deliberately awful: missing revenue,
      contradictory dates, a loss run that doesn't match the narrative. Show
      the review queue catching it.
- [ ] Get the extraction eval to a real number over at least 20 fields and
      write down the wrong-rate separately from the miss-rate.
- [ ] Wire the state machine to something durable (Temporal's Python SDK, or
      Postgres plus a worker) so you can speak from experience about
      resuming a submission a week later.

## Week 3 — outreach

- [ ] Email careers@unionspecialty.com. Short. Three paragraphs: what you've
      shipped with agents in production, the repo link with one line on what
      it does, and why specialty insurance specifically. No cover-letter
      throat-clearing.
- [ ] Find the CEO and CTO on LinkedIn first and read their backgrounds
      properly. The CTO came from Jump and Meta; assume a high bar on
      systems fundamentals and low patience for hand-waving.
- [ ] Prepare the four questions you'll ask them (below). Asking good ones is
      half the evaluation at this stage.

## Week 4 — interview

### What they will probe

| Area | What they're checking | Prepare |
|---|---|---|
| Agent evals | Can you tell a working system from a demo? | Your wrong-rate vs. miss-rate framing; judge-grading-the-judge; building eval sets from the review queue |
| Long-running workflows | Have you run agents in production? | Idempotency, retries, resuming after a week, what you do when a carrier never replies |
| Messy extraction | Do you respect the liability? | Confidence, grounding against source, human-in-the-loop, what a wrong field on a bound policy costs |
| Backend fundamentals | The CTO's bar | Postgres, queues, schema design for something that will change monthly. Expect real systems questions, not LeetCode |
| Agency | "You write the spec" | Concrete examples of you deciding what to build, not just building it |
| Domain | Will you slow the brokers down? | Week 1 |

### The story to have ready

One production agent system you shipped: what it did, how you knew it worked,
what broke in production that you didn't predict, what you changed. That last
part is the whole question. Have a real failure with a real fix.

### Questions to ask them

1. Absolute numbers on the business: placed premium, commission run rate, how
   much is repeat. "Doubling monthly" needs a denominator.
2. Where does the CEO's time go today, and which of those hours is the first
   agent supposed to take back? This tells you what you'd actually build.
3. Of the 25+ carrier contracts, how many can you submit to programmatically
   and how many are an inbox? The answer determines the next two years of work.
4. Which is the bigger risk in their view: the agents not being good enough,
   or the carriers not accepting machine-generated submissions? Whoever
   answers honestly is worth working for.

## Negotiation

Do this before you fall in love with the job.

- **Find out where in the 1–3% band you'd land, early.** 1% and 3% are
  different jobs. Ask directly and ask what determines it.
- **Base is under market.** $150–190k for production agent experience in NYC
  is below what a larger company pays. That's the trade for founding equity,
  but it means the equity has to be real. Anchor at the top of the band and
  treat the gap as something the equity is buying.
- **Ask the questions that change what the equity is worth:** post-money
  valuation of the pre-seed, total option pool size, strike price, vesting and
  cliff, whether there's early exercise, and what happens to unvested shares
  if you leave or are let go.
- **Brokerages exit at lower multiples than software companies.** Your 1–3% is
  worth less per dollar of revenue than the same slice of a SaaS company.
  Factor that in rather than comparing percentages to startup folklore.
- **Get the runway number.** "Years of runway" with no figure and no named
  investors is the softest claim in an otherwise specific posting.

## Grading your own fit

Take the job if you want to build the whole thing and be responsible for it,
can absorb a below-market base for a year or two, and find regulated, messy,
unglamorous domains interesting rather than annoying. Skip it if you need a
spec, want to optimise for cash now, or would resent five days a week in an
office on Broadway.
