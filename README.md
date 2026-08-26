# TrialGrid

**A human-supervised team of agents that answers multi-site clinical trial feasibility — without a single patient record leaving any hospital.**

Built at the Collaborative Agent Hackathon, Cambridge, 26 August 2026. Track 2 (Infrastructure).

---

## The problem

A sponsor wants to know whether a trial protocol can actually recruit. Today that is months of emails to twenty hospitals, each hand-counting patients against sixty criteria. No hospital will share records to answer it, so the question gets answered slowly, partially, or not at all — and protocols that could never have recruited open anyway, then fail.

## The answer this gives

Not "47 eligible". That is the easy number and everyone already has it. This reports the population everybody else discards:

```
  SITES      2 of 3 answered
             ABSTAINED: west-suffolk  -> counted as unknown, NOT as zero

  ELIGIBLE          7
  NEEDS SCREENING   11   <- fails nothing, one fact away
  NOT ELIGIBLE      32

  WHAT IS MISSING
    egfr_uncommon_mutation       9 patients
    ecog                         SUPPRESSED  (n < 5, withheld)

  BLOCKED - AWAITING SPONSOR SIGN-OFF   token c0ebf445
```

Eleven patients fail nothing. Nine of them are waiting on the same test — which is **one message to one lab**, not nine separate acts of remembering.

## The thesis

A missing lab result is not a "no". Federating that turns it into a rule about institutions:

> **A site that abstains is not a zero.**

Imputing zero for a silent site understates a network in the one direction that kills a viable trial. So the aggregate carries how many sites answered, and the model is instructed — and the tests require — that a partial network is never reported as a whole one.

---

## Where safety actually lives

Every agent in this system is deliberately weak. The controls are deterministic Python and there is no prompt that can talk past them.

| Boundary | What it does | Why it holds |
|---|---|---|
| **Site agents make no model call** | They run rules over their own log | A site with no model cannot be prompt-injected |
| **Query-shape allowlist** | Only `counts` is producible | The model may *agree* to list patients; the request still dies here |
| **Egress guard** | Refuses payloads, never sanitises them | A field that shouldn't exist is an error, not something to strip |
| **Small-cell suppression** | `n < 5` withheld, **not rounded** | Rounding still reveals that a small stratum exists |
| **Approval token** | Derived from the exact numbers | An approval cannot be replayed against a different result |

`trialgrid/prompts.py` holds every instruction any model is given, in one file, so it can be audited in one read. That file opens by stating that **none of those prompts is a safety control**. If all of them were replaced with empty strings, no patient record would still cross the wire.

That is the difference between a demo where a model *refuses* and this one. A judge who distrusts LLMs should find this design *more* convincing, not less.

## Run it

```bash
uv sync --extra dev
uv run pytest                    # 16 tests, each named for a promise above
uv run python -m trialgrid.demo  # deterministic core, no network, ~0.003s
```

On a local SuperLink with a Track 2 endpoint:

```bash
cp .env.example .env             # then fill in; never commit it
export FLWR_MODEL_API_ENDPOINT='http://129.212.182.232:8001/v1/responses'
unset FLWR_MODEL_API_KEY         # Qwen3.5 needs no key
uv run flower-superlink --insecure
```

```bash
uv run flwr run . local-agent --run-config 'model.id="/models/Qwen3.5-397B-A17B-FP8"' --stream
```

Release a blocked result by supplying its token:

```bash
uv run flwr run . local-agent --run-config 'policy.approval-token="c0ebf445"' --stream
```

`policy.narrate=false` skips every model call and completes in under two seconds — the panic button for a flaky endpoint.

## Architecture

```
   site agent        site agent        site agent
   own log           own log           own log
   rules only        rules only        rules only
   no model          no model          no model
        |                 |                 |
        +----- egress guard: counts only ---+
                          |
                   coordinator agent   (never sees a row)
                          |
                   human sign-off      (token bound to the numbers)
                          |
                   feasibility answer
```

Two model calls in the whole pipeline — one to route the question, one to phrase an approved answer. Everything that decides anything sits between them and is deterministic. That is a safety property first; it also keeps the run inside SuperGrid's five-minute task timeout, because the cost does not grow with the number of sites.

---

## What we do not claim

- **The data is synthetic.** Three generated cohorts with deliberately unequal recording rates, because real networks are not uniform. There is no patient data here — no PHI, no de-identified extract, nothing. `trialgrid/sites.py` generates it and you can read it.
- **The protocol is synthetic.** Criteria are shaped like a real uncommon-EGFR NSCLC trial. They are paraphrased and are not lifted from any sponsor's document.
- **We have measured no accuracy.** No benchmark, no percentage, no time saving. The rules are deterministic — the same input gives the same answer, and every answer names the fact it used. That is the claim, and it is the whole claim.
- **This is not anonymity.** Sites hold their own patient codes. Not sending identifiers is a real reduction in exposure; it is not the same as anonymising, and a compliance officer would rightly catch us saying otherwise.
- **This is not federated learning.** No model is trained. A Flower App Bundle holds either one `agentapp` or a `serverapp`+`clientapp`, never both.
- **This is not a medical device.** It is feasibility decision support for research staff. It does not diagnose, does not recommend treatment, and makes no enrolment decision.

## Relationship to Mizan

The three-tier idea — that a patient who fails nothing but is missing a fact belongs at the top of a worklist rather than in the "no" pile — comes from Mizan, a clinical trial eligibility engine the author is building separately. Mizan is a single-site product and has no cross-site capability; that gap is what this hackathon project explores.

**No Mizan source code is in this repository.** The eligibility module here was written from scratch today against the same idea. The four-state model (`MET / NOT_MET / UNKNOWN / NOT_APPLICABLE`) is not original to either — the NIH's TrialGPT emits the same four states, and it is public domain.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
