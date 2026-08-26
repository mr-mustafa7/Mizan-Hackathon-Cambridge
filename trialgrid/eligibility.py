"""Four-state criterion evaluation and three-tier assessment.

Deterministic. No model is consulted here, and none can be: this module has no
network, no I/O and no dependency beyond the standard library. That is the
point. A language model may read a record and propose a fact; it may never
judge one.

The four states are the ones the NIH's TrialGPT also emits, so the shape of the
problem is not ours alone. The third tier — "fails nothing, we are simply
missing a fact" — is the part that matters, because it is the patient everyone
else discards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# Values that mean "nobody has answered this yet" rather than a real answer.
_NO_ANSWER = frozenset({"", "unknown", "not done", "nd", "pending", "awaited", "n/a", "na"})

# Values that mean the test was ordered but the result has not arrived. A
# different phone call from "never ordered", so a different column of work.
_AWAITING = frozenset({"pending", "awaited", "sent", "at lab"})


class State(StrEnum):
    MET = "MET"
    NOT_MET = "NOT_MET"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Tier(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NEEDS_SCREENING = "NEEDS_SCREENING"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class Kind(StrEnum):
    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"


@dataclass(frozen=True, slots=True)
class Criterion:
    """One rule, as the protocol wrote it."""

    ref: str
    kind: Kind
    attribute: str
    operator: str
    value: str
    #: The protocol's own words. Travels with every result so an audit record
    #: never has to go back and look it up.
    wording: str


@dataclass(frozen=True, slots=True)
class Patient:
    """One patient, as the site's screening log holds them.

    `code` is the site's own reference. No name, no date of birth, no medical
    record number — this class has no field that could hold one.
    """

    code: str
    facts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Result:
    criterion_ref: str
    attribute: str
    state: State
    wording: str
    #: Why we could not answer, when we could not. Empty otherwise.
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Assessment:
    patient_code: str
    tier: Tier
    #: Attributes that are unanswered and standing between this patient and a
    #: decision. Named, never counted — a count is a statistic and nobody can
    #: act on a statistic.
    missing: tuple[str, ...] = ()
    #: Attributes that actually rule the patient out.
    blocked_by: tuple[str, ...] = ()


_NUMERIC = {
    "less_than": lambda a, b: a < b,
    "less_than_or_equal": lambda a, b: a <= b,
    "greater_than": lambda a, b: a > b,
    "greater_than_or_equal": lambda a, b: a >= b,
}


def _as_number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_no_answer(raw: str | None) -> bool:
    return raw is None or raw.strip().lower() in _NO_ANSWER


def is_awaiting_result(raw: str) -> bool:
    """Ordered, not back. Chase the lab — do not re-order the test."""
    return raw.strip().lower() in _AWAITING


def evaluate(patient: Patient, criteria: list[Criterion]) -> list[Result]:
    """Answer every criterion for one patient. Never raises on bad data."""
    results: list[Result] = []
    for c in criteria:
        raw = patient.facts.get(c.attribute)

        if _has_no_answer(raw):
            reason = "awaiting_result" if raw and is_awaiting_result(raw) else "no_record"
            results.append(Result(c.ref, c.attribute, State.UNKNOWN, c.wording, reason))
            continue

        held = raw.strip().lower()
        want = c.value.strip().lower()

        if c.operator in _NUMERIC:
            lhs, rhs = _as_number(held), _as_number(want)
            if lhs is None or rhs is None:
                # We hold a value but cannot compare it. That is a gap in our
                # dictionary, not a fact about the patient, so it must never
                # become a rejection.
                results.append(
                    Result(c.ref, c.attribute, State.UNKNOWN, c.wording, "unreadable_value")
                )
                continue
            satisfied = _NUMERIC[c.operator](lhs, rhs)
        elif c.operator == "equals":
            satisfied = held == want
        elif c.operator == "not_equals":
            satisfied = held != want
        elif c.operator == "in_set":
            satisfied = held in {p.strip() for p in want.split("|") if p.strip()}
        elif c.operator == "contains":
            satisfied = want in held
        else:
            results.append(
                Result(c.ref, c.attribute, State.UNKNOWN, c.wording, "unsupported_operator")
            )
            continue

        results.append(
            Result(c.ref, c.attribute, State.MET if satisfied else State.NOT_MET, c.wording)
        )
    return results


def assess(patient_code: str, criteria: list[Criterion], results: list[Result]) -> Assessment:
    """Turn per-criterion answers into one tier.

    The order of these checks is the safety property, and it is not negotiable:
    a definite failure is decided before an unknown is considered. Reverse them
    and a patient who genuinely fails a rule would be sent for screening; keep
    them and a patient we merely cannot answer for is never rejected.
    """
    by_ref = {c.ref: c for c in criteria}
    blocked: list[str] = []
    missing: list[str] = []

    for r in results:
        c = by_ref.get(r.criterion_ref)
        if c is None:
            continue
        fails = (c.kind is Kind.INCLUSION and r.state is State.NOT_MET) or (
            c.kind is Kind.EXCLUSION and r.state is State.MET
        )
        if fails:
            blocked.append(r.attribute)
        elif r.state is State.UNKNOWN:
            missing.append(r.attribute)

    if blocked:
        tier = Tier.NOT_ELIGIBLE
    elif missing:
        tier = Tier.NEEDS_SCREENING
    else:
        tier = Tier.ELIGIBLE

    # A patient who is already out is not also "missing" things. Reporting both
    # would put them in a coordinator's queue as work that cannot pay off.
    return Assessment(
        patient_code=patient_code,
        tier=tier,
        missing=() if blocked else tuple(sorted(set(missing))),
        blocked_by=tuple(sorted(set(blocked))),
    )


def assess_all(patients: list[Patient], criteria: list[Criterion]) -> list[Assessment]:
    return [assess(p.code, criteria, evaluate(p, criteria)) for p in patients]
