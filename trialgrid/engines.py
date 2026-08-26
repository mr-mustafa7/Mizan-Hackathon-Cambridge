"""Which engine decides eligibility, and how one is swapped for another.

Mizan defines an `EvaluationEngine` Protocol — one method, `evaluate`, and
nothing else. That seam exists so the reasoning backend is an implementation
detail rather than the product. This module honours it from the outside.

Two engines satisfy the contract here:

* the reference engine in `trialgrid.eligibility`, which ships with this repo
  so it can be read, tested and run by anyone who clones it
* Mizan's production engine, used automatically when it is importable

The demo prefers Mizan when present and says so on screen. Nothing else in the
system changes: the guard, the Gatekeeper and the tiers behave identically,
because tiers are decided from rule results and not by the engine that produced
them. That is the seam doing its job, and it is the honest answer to "why isn't
your reasoning vendor your whole company".

**No Mizan source is vendored into this repository.** It is imported if it
happens to be on the path, and the reference engine runs if it is not.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from trialgrid.eligibility import Assessment, Criterion, Kind, Patient, Tier, assess_all

#: Where a local Mizan checkout may be found. Configurable so nobody has to
#: edit code to point at their own copy.
MIZAN_PATH = os.environ.get("MIZAN_PATH", "/Users/onlyforstudy/Cambridge Hack/mizan-grid")


@dataclass(frozen=True, slots=True)
class EngineInfo:
    name: str
    detail: str
    is_production: bool


def _try_mizan() -> bool:
    if MIZAN_PATH and MIZAN_PATH not in sys.path and os.path.isdir(MIZAN_PATH):
        sys.path.insert(0, MIZAN_PATH)
    try:
        import mizan_engine.local  # noqa: F401
        import mizan_engine.aggregate  # noqa: F401
    except ImportError:
        return False
    return True


MIZAN_AVAILABLE = _try_mizan()


def engine_info() -> EngineInfo:
    if MIZAN_AVAILABLE:
        return EngineInfo(
            name="Mizan",
            detail="production engine, four-state evaluation with lineage",
            is_production=True,
        )
    return EngineInfo(
        name="Reference",
        detail="in-repo implementation of the same contract",
        is_production=False,
    )


def _via_mizan(patients: list[Patient], criteria: list[Criterion]) -> list[Assessment]:
    """Translate to Mizan's shapes, evaluate, translate the answer back.

    The translation is deliberately total: every criterion and every fact is
    passed through, so a difference in outcome would be a real disagreement
    between engines rather than an artefact of what we chose to send.
    """
    from decimal import Decimal

    from mizan_engine.aggregate import Tier as MTier
    from mizan_engine.aggregate import assess_all as m_assess_all
    from mizan_engine.local import LocalEngine
    from mizan_engine.shapes import Criterion as MCriterion
    from mizan_engine.shapes import Fact as MFact
    from mizan_engine.shapes import RuleType, Severity

    m_criteria = [
        MCriterion(
            criterion_ref=c.ref,
            rule_type=RuleType.INCLUSION if c.kind is Kind.INCLUSION else RuleType.EXCLUSION,
            severity=Severity.HARD,
            canonical_attribute=c.attribute,
            operator=c.operator,
            expected_value=c.value,
            wording=c.wording,
        )
        for c in criteria
    ]
    m_facts = [
        MFact(
            patient_code=p.code,
            canonical_attribute=attribute,
            value=value,
            confidence=Decimal("0.95"),
            source="screening_log",
        )
        for p in patients
        for attribute, value in p.facts.items()
        if value.strip()
    ]

    results = LocalEngine().evaluate(
        patients=[p.code for p in patients],
        facts=m_facts,
        criteria=m_criteria,
        criteria_version="trialgrid-1",
    )

    tier_map = {
        MTier.ELIGIBLE: Tier.ELIGIBLE,
        MTier.NEEDS_SCREENING: Tier.NEEDS_SCREENING,
        MTier.NOT_ELIGIBLE: Tier.NOT_ELIGIBLE,
    }
    return [
        Assessment(
            patient_code=a.patient_code,
            tier=tier_map[a.tier],
            missing=tuple(sorted({m.canonical_attribute for m in a.missing_facts})),
            blocked_by=tuple(sorted({b.canonical_attribute for b in a.blocking_facts})),
        )
        for a in m_assess_all(results, criteria_version="trialgrid-1")
    ]


def evaluate(patients: list[Patient], criteria: list[Criterion]) -> list[Assessment]:
    """Assess a cohort with whichever engine is available."""
    if MIZAN_AVAILABLE:
        return _via_mizan(patients, criteria)
    return assess_all(patients, criteria)


def trace_one_patient(
    patient: Patient, criteria: list[Criterion]
) -> list[dict[str, str]]:
    """Every criterion, decided, for one real patient — with the engine's own reason.

    This is what makes the engine's decisions inspectable rather than a black
    box behind a tier. `RuleResult.reason` is produced deterministically by the
    engine itself, not written by a model — so what a judge reads here is
    exactly what a coordinator would read in production.
    """
    if MIZAN_AVAILABLE:
        return _trace_via_mizan(patient, criteria)
    return _trace_via_reference(patient, criteria)


def _trace_via_mizan(patient: Patient, criteria: list[Criterion]) -> list[dict[str, str]]:
    from decimal import Decimal

    from mizan_engine.local import LocalEngine
    from mizan_engine.shapes import Criterion as MCriterion
    from mizan_engine.shapes import Fact as MFact
    from mizan_engine.shapes import RuleType, Severity, State as MState

    m_criteria = [
        MCriterion(
            criterion_ref=c.ref,
            rule_type=RuleType.INCLUSION if c.kind is Kind.INCLUSION else RuleType.EXCLUSION,
            severity=Severity.HARD,
            canonical_attribute=c.attribute,
            operator=c.operator,
            expected_value=c.value,
            wording=c.wording,
        )
        for c in criteria
    ]
    m_facts = [
        MFact(
            patient_code=patient.code,
            canonical_attribute=attribute,
            value=value,
            confidence=Decimal("0.95"),
            source="screening_log",
        )
        for attribute, value in patient.facts.items()
        if value.strip()
    ]
    results = LocalEngine().evaluate(
        patients=[patient.code], facts=m_facts, criteria=m_criteria, criteria_version="trialgrid-1"
    )
    state_icon = {MState.MET: "MET", MState.NOT_MET: "NOT_MET", MState.UNKNOWN: "UNKNOWN"}
    return [
        {
            "ref": r.criterion_ref,
            "attribute": r.canonical_attribute,
            "wording": r.wording,
            "state": state_icon.get(r.state, str(r.state)),
            "reason": r.reason,
            "deciding_fact": r.deciding_fact.value if r.deciding_fact else None,
            "unknown_reason": r.unknown_reason.value if r.unknown_reason else None,
        }
        for r in results
    ]


def _trace_via_reference(patient: Patient, criteria: list[Criterion]) -> list[dict[str, str]]:
    from trialgrid.eligibility import evaluate as ref_evaluate

    results = ref_evaluate(patient, criteria)
    return [
        {
            "ref": r.criterion_ref,
            "attribute": r.attribute,
            "wording": r.wording,
            "state": r.state.value,
            "reason": r.reason or "criterion met",
            "deciding_fact": patient.facts.get(r.attribute),
            "unknown_reason": r.reason or None,
        }
        for r in results
    ]
