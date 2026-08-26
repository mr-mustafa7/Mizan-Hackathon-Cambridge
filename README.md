# TrialGrid

**A human-supervised team of agents that answers multi-site clinical trial feasibility — without a single patient record leaving any hospital.**

Built at the Collaborative Agent Hackathon, Cambridge, 26 August 2026. Track 2 (Infrastructure).

---

## The problem

Sites spent **$170M in 2024** completing feasibility assessments for FDA-regulated
industry trials. The average assessment takes **29.4 days**. **70–80% of trials** hit
delays or enrollment shortfalls.

Federated feasibility already exists — [TriNetX](https://trinetx.com/data/) runs it across
300M+ patients, and [DataSHIELD](https://datashield.org/about/) has done federated
disclosure control for years. **This project is not claiming to have invented that.**

What those systems answer is *who matches*. But there is a documented **65% gap between
the structured data recorded for care and the data needed to assess eligibility**, and in
practice *"subjects with incomplete eligibility data are almost always excluded from
analysis"* — a known source of selection bias.

So the patients who fail nothing, and are simply missing one fact, get dropped. This
answers a different question: **who is one fact away, and which fact is it.**

## The answer this gives

Not "47 eligible". That is the easy number and everyone already has it. This reports the population everybody else discards:

```
  QUARANTINE  C6 from S4  -> injected_instruction
  QUARANTINE  C7 from S4  -> injected_instruction, disclosure_request

  SITES      2 of 3 answered
             ABSTAINED: west-suffolk  -> unknown, NOT zero

  ELIGIBLE          8
  NEEDS SCREENING   12   <- fails nothing, one fact away
  NOT ELIGIBLE      30

  WHAT IS MISSING
    egfr_uncommon_mutation       9 patients
    ecog                         SUPPRESSED  (n < 5)

  BLOCKED - AWAITING SPONSOR SIGN-OFF   token 6a112dcc
```

Twelve patients fail nothing. Nine are waiting on the same test — **one message to one lab**,
not nine separate acts of remembering.

## The thesis

A missing lab result is not a "no". Federating that turns it into a rule about institutions:

> **A site that abstains is not a zero.**

Imputing zero for a silent site understates a network in the one direction that kills a viable trial. So the aggregate carries how many sites answered, and the model is instructed — and the tests require — that a partial network is never reported as a whole one.

---

## Two trust boundaries, one pipeline

Criteria are not born structured. Somebody reads them off a registry page — untrusted
content from the open web. Patients live in hospitals — private data that must not move.
Those are different problems, and the architecture keeps them apart:

```
  WEB (untrusted)                            HOSPITALS (private)

  Retriever ─▶ Sanitizer ─▶ Drafter          site agent   site agent   site agent
  reads the    strips out   writes the       own log      own log      own log
  web only     injected     criteria         rules only   rules only   rules only
               instructions                  no model     no model     no model
       │                        │                 │            │            │
       │                        ▼                 └──── counts only ────────┘
       │              ┌──────────────────┐                     │
       └─ never sees ─┤   GATEKEEPER     ├── criteria ─────────┘
          a patient   │  ordinary Python │                     │
                      └──────────────────┘              Challenger
                                                              │
                                                     human sign-off
```

The agents that touch the web are never shown a patient. The agents that evaluate
patients never touch the web, make no model call at all, and can emit nothing but counts.

## Where safety actually lives

Every agent here is deliberately weak. The controls are deterministic and there is no
prompt that talks past them.

| Boundary | What it does | Why it holds |
|---|---|---|
| **Site agents make no model call** | They run rules over their own log | A site with no model cannot be prompt-injected |
| **Quote verification** | Every cited quote must *occur* in the source | No phrasing makes a substring appear in a document it isn't in |
| **Source allowlist** | Only approved domains can support a criterion | Enforced in code, not requested in a prompt |
| **Quarantine** | Hostile pages are reported, not obeyed — and not deleted | A human must be able to see the attack |
| **Egress guard** | Refuses payloads rather than sanitising them | A field that shouldn't exist is an error |
| **Small-cell suppression** | `n < 5` withheld, **not rounded** | Rounding still reveals a small stratum exists |
| **Approval token** | Bound to the counts *and* the criteria | Approving a strict protocol doesn't release a loosened one |

`trialgrid/prompts.py` holds every instruction any model is given, in one file, and opens
by stating that **none of them is a safety control**. Replace all of them with empty
strings and no patient record still crosses the wire.

## The demonstration

```bash
uv run python -m trialgrid.web      # opens http://localhost:8000
```

A projector-legible page with two buttons. Standard library only — no web framework, no
build step. Every number on it comes from a live call into the same pipeline the AgentApp
runs; the browser computes nothing itself, so the demo cannot drift from the system it
claims to show.

Terminal version, if you prefer:

```bash
uv run python -m trialgrid.demo
```

The same question, asked twice, over the same four sources — one of which is a hostile
"protocol clarification notice" carrying an instruction addressed to whatever is reading it.

```
  ECOG criterion, guarded    : less_than_or_equal 1
  ECOG criterion, unguarded  : less_than_or_equal 4   <- rewritten by the hostile page

  Recruitable (needs screening), guarded   : 12
  Recruitable (needs screening), unguarded : 16
```

Nobody is told a lie. The protocol is simply loosened, the feasibility answer inflates by
37%, and a sponsor opens sites that cannot deliver. The second run is not a strawman — it
is the identical code path with two checks disabled.

## Run it

```bash
uv sync --extra dev
uv run pytest                    # 32 tests, each named for a promise above
uv run python -m trialgrid.demo  # the A/B contrast, no network, ~0.004s
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
uv run flwr run . local-agent --run-config 'policy.approval-token="6a112dcc"' --stream
```

Run the unguarded version to see what the safeguards prevent:

```bash
uv run flwr run . local-agent --run-config 'safety.enabled=false' --stream
```

`python -m trialgrid.demo` is the panic button: no network, no model, no Flower runtime,
and it still shows the entire argument.

## Model budget

Four bounded model calls: sanitize, draft, challenge, disclose. Every stage that *decides*
anything sits between them and is deterministic. That is a safety property first, and it
also keeps a run inside SuperGrid's five-minute task timeout, since cost does not grow
with the number of sites.

---

## What we do not claim

- **The data is synthetic.** Three generated cohorts with deliberately unequal recording rates, because real networks are not uniform. There is no patient data here — no PHI, no de-identified extract, nothing. `trialgrid/sites.py` generates it and you can read it.
- **The protocol is synthetic.** Criteria are shaped like a real uncommon-EGFR NSCLC trial. They are paraphrased and are not lifted from any sponsor's document.
- **We have measured no accuracy.** No benchmark, no percentage, no time saving. The rules are deterministic — the same input gives the same answer, and every answer names the fact it used. That is the claim, and it is the whole claim.
- **This is not anonymity.** Sites hold their own patient codes. Not sending identifiers is a real reduction in exposure; it is not the same as anonymising, and a compliance officer would rightly catch us saying otherwise.
- **This is not federated learning.** No model is trained. A Flower App Bundle holds either one `agentapp` or a `serverapp`+`clientapp`, never both.
- **The sites run in one process today.** Their isolation is architectural — no shared state, no model call, counts-only egress — but they are not yet on separate machines. Saying otherwise would be a lie about the threat model.
- **The demo's model is scripted.** `trialgrid/offline.py` returns fixed, role-appropriate JSON so the A/B contrast is reproducible rather than dependent on a language model having a good day. Against a live model the Sanitizer may catch more or less; the Gatekeeper's checks are unaffected either way, because they are code.
- **This is not a medical device.** It is feasibility decision support for research staff. It does not diagnose, does not recommend treatment, and makes no enrolment decision.

## Relationship to Mizan

The three-tier idea — that a patient who fails nothing but is missing a fact belongs at the top of a worklist rather than in the "no" pile — comes from Mizan, a clinical trial eligibility engine the author is building separately. Mizan is a single-site product and has no cross-site capability; that gap is what this hackathon project explores.

**No Mizan source code is in this repository.** The eligibility module here was written from scratch today against the same idea. The four-state model (`MET / NOT_MET / UNKNOWN / NOT_APPLICABLE`) is not original to either — the NIH's TrialGPT emits the same four states, and it is public domain.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
