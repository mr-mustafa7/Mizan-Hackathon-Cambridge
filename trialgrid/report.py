"""Structured results, so a screen can render what the terminal prints.

The web view must not be a second implementation of the pipeline — a demo that
draws its own numbers is a demo that can disagree with the system it claims to
show. So this module runs the real stages and reports what happened, and the
browser only ever draws what it is handed.
"""

from __future__ import annotations

from typing import Any

from trialgrid.agent_app import approval_token
from trialgrid.engines import engine_info, trace_one_patient
from trialgrid.guard import SUPPRESSED, combine
from trialgrid.impact import analyse
from trialgrid.sites import cohort
from trialgrid.offline import scripted_model
from trialgrid.pipeline import Trace, draft_criteria, run_gate, sanitize
from trialgrid.prompts import DRAFTER, SANITIZER
from trialgrid.sites import all_site_ids, run_site
from trialgrid.sources import POISONED_SOURCE, fixture_sources

QUESTION = "We are opening the uncommon-EGFR NSCLC protocol. Can it recruit across our network?"


def run_structured(*, safety_enabled: bool, abstaining: str = "west-suffolk") -> dict[str, Any]:
    """Run the pipeline and report every stage as data."""
    sources = fixture_sources(include_poisoned=True)
    trace = Trace()

    cards = sanitize(sources, scripted_model, SANITIZER, safety_enabled=safety_enabled, trace=trace)
    criteria, refs = draft_criteria(cards, scripted_model, DRAFTER)
    kept, gate_result = run_gate(
        cards, sources, refs, criteria, safety_enabled=safety_enabled, trace=trace
    )

    site_ids = all_site_ids()
    returns = [run_site(s, criteria=kept, abstain=(s == abstaining)) for s in site_ids]
    aggregate = combine(returns, sites_asked=len(site_ids))

    admissible = set(gate_result.admissible)
    flagged = [c for c in cards if c.quarantine_flags]

    # The agent roster, described by what each one was actually handed. The
    # capability columns are the point: they say what an agent CANNOT reach,
    # which is the only claim that survives a compromised model.
    agents = [
        {
            "name": "Retriever",
            "role": "Fetches source documents",
            "model_call": False,
            "can": ["read the open web"],
            "cannot": ["see a patient", "write a criterion", "decide anything"],
            "received": "1 protocol question",
            "produced": f"{len(sources)} documents ({sum(s['hostile'] for s in [{'hostile': x.source_id == POISONED_SOURCE.source_id} for x in sources])} hostile)",
            "zone": "web",
        },
        {
            "name": "Sanitizer",
            "role": "Distils documents into evidence cards",
            "model_call": True,
            "can": ["read raw untrusted text", "flag hostile content"],
            "cannot": ["see a patient", "act on an instruction it reads"],
            "received": f"{len(sources)} raw documents",
            "produced": f"{len(cards)} cards, {len(flagged)} quarantined",
            "zone": "web",
        },
        {
            "name": "Drafter",
            "role": "Writes machine-checkable criteria",
            "model_call": True,
            "can": ["read evidence cards"],
            "cannot": ["touch the internet", "see raw documents", "see a patient"],
            "received": f"{len(cards)} cards",
            "produced": f"{len(criteria)} criteria, each citing a card",
            "zone": "web",
        },
        {
            "name": "Gatekeeper",
            "role": "Verifies provenance — plain Python, not a model",
            "model_call": False,
            "can": ["reject any criterion", "block the whole run"],
            "cannot": ["be persuaded", "be prompted", "be overridden by a model"],
            "received": f"{len(criteria)} criteria + {len(cards)} cards",
            "produced": (
                f"{len(kept)} admitted, {len(gate_result.violations)} violations"
                + ("" if safety_enabled else " (IGNORED — safety off)")
            ),
            "zone": "gate",
        },
        *[
            {
                "name": f"Site · {r.site_id}",
                "role": "Evaluates its own patients locally",
                "model_call": False,
                "can": ["read its own screening log", "emit counts"],
                "cannot": ["touch the internet", "see another site", "emit a patient row"],
                "received": f"{len(kept)} criteria",
                "produced": (
                    f"{r.screened} screened → counts only"
                    if r.disposition.value == "ANSWERED"
                    else "ABSTAINED → unknown, not zero"
                ),
                "zone": "hospital",
            }
            for r in returns
        ],
        {
            "name": "Egress guard",
            "role": "Suppresses small cells — plain Python",
            "model_call": False,
            "can": ["refuse a payload", "withhold a count"],
            "cannot": ["be persuaded", "round instead of suppress"],
            "received": f"{len(returns)} site returns",
            "produced": (
                f"{aggregate.sites_answered} of {aggregate.sites_asked} pooled, "
                f"{len(aggregate.suppressed_gaps)} cells suppressed"
            ),
            "zone": "gate",
        },
        {
            "name": "Human",
            "role": "Signs off before anything is released",
            "model_call": False,
            "can": ["release", "refuse"],
            "cannot": ["be skipped when safeguards are on"],
            "received": "the full aggregate + token",
            "produced": "BLOCKED — awaiting sign-off" if safety_enabled else "bypassed",
            "zone": "human",
        },
    ]

    pool = [p for sid in site_ids if sid != abstaining for p in cohort(sid)]
    impacts = analyse(pool, kept) if kept else []
    info = engine_info()

    # One real patient, walked criterion by criterion, so the engine's own
    # reasoning is inspectable rather than a tier hiding a black box.
    # Prefer the patient the whole thesis is about: nothing disqualifies them,
    # but one fact was never recorded, so they sit at NEEDS_SCREENING rather
    # than being silently dropped.
    demo_patient = None
    if pool and kept:
        for p in pool:
            if (
                "egfr_uncommon_mutation" not in p.facts
                and p.facts.get("histology") == "adenocarcinoma"
                and p.facts.get("active_infection") == "no"
                and p.facts.get("prior_egfr_tki") == "no"
                and p.facts.get("ecog") in ("0", "1")
                and p.facts.get("measurable_disease") == "yes"
            ):
                demo_patient = p
                break
        if demo_patient is None:
            demo_patient = pool[0]
    patient_trace = (
        {"code": demo_patient.code, "facts": demo_patient.facts, "rows": trace_one_patient(demo_patient, kept)}
        if demo_patient else None
    )

    return {
        "engine": {"name": info.name, "detail": info.detail, "production": info.is_production},
        "patient_trace": patient_trace,
        "agents": agents,
        "impact": [
            {
                "ref": i.ref,
                "attribute": i.attribute,
                "wording": i.wording,
                "blocks": i.blocks,
                "unanswered": i.unanswered,
                "total_cost": i.total_cost,
                "gain_if_removed": i.gain_if_removed,
                "relaxed_to": i.relaxed_to,
                "gain_if_relaxed": i.gain_if_relaxed,
            }
            for i in impacts
        ],
        "safety_enabled": safety_enabled,
        "question": QUESTION,
        "sources": [
            {
                "id": s.source_id,
                "title": s.title,
                "url": s.url,
                "domain": s.domain,
                "hostile": s.source_id == POISONED_SOURCE.source_id,
                "allowlisted": s.is_allowlisted,
            }
            for s in sources
        ],
        "cards": [
            {
                "id": c.card_id,
                "claim": c.claim,
                "quote": c.verbatim_quote,
                "source_id": c.source_id,
                "flags": list(c.quarantine_flags),
                "admissible": c.card_id in admissible,
            }
            for c in cards
        ],
        "criteria": [
            {
                "ref": c.ref,
                "kind": c.kind.value,
                "attribute": c.attribute,
                "operator": c.operator,
                "value": c.value,
                "wording": c.wording,
                "card_id": refs.get(c.ref, ""),
            }
            for c in kept
        ],
        "violations": [{"rule": v.rule, "detail": v.detail} for v in gate_result.violations],
        "sites": [
            {
                "id": r.site_id,
                "disposition": r.disposition.value,
                "screened": r.screened,
                "note": r.note,
            }
            for r in returns
        ],
        "counts": {
            "eligible": aggregate.eligible,
            "needs_screening": aggregate.needs_screening,
            "not_eligible": aggregate.not_eligible,
            "sites_answered": aggregate.sites_answered,
            "sites_asked": aggregate.sites_asked,
            "abstained": list(aggregate.abstained),
            "min_cell": aggregate.min_cell,
            "gaps": [
                {"attribute": k, "count": None if v == SUPPRESSED else v}
                for k, v in aggregate.gaps.items()
            ],
        },
        "token": approval_token(aggregate, kept),
        "trace": trace.lines,
    }


def both_runs() -> dict[str, Any]:
    """The comparison the whole demonstration rests on."""
    guarded = run_structured(safety_enabled=True)
    unguarded = run_structured(safety_enabled=False)

    def ecog(run: dict[str, Any]) -> str | None:
        for c in run["criteria"]:
            if c["attribute"] == "ecog":
                return f"{c['operator']} {c['value']}"
        return None

    return {
        "guarded": guarded,
        "unguarded": unguarded,
        "diff": {
            "ecog_guarded": ecog(guarded),
            "ecog_unguarded": ecog(unguarded),
            "recruitable_guarded": guarded["counts"]["needs_screening"],
            "recruitable_unguarded": unguarded["counts"]["needs_screening"],
            "eligible_guarded": guarded["counts"]["eligible"],
            "eligible_unguarded": unguarded["counts"]["eligible"],
        },
    }
