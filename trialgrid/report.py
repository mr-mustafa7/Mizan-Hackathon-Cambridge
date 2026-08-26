"""Structured results, so a screen can render what the terminal prints.

The web view must not be a second implementation of the pipeline — a demo that
draws its own numbers is a demo that can disagree with the system it claims to
show. So this module runs the real stages and reports what happened, and the
browser only ever draws what it is handed.
"""

from __future__ import annotations

from typing import Any

from trialgrid.agent_app import approval_token
from trialgrid.guard import SUPPRESSED, combine
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

    return {
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
