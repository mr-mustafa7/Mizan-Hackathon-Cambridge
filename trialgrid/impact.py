"""Which criterion is costing you patients, and what happens if you relax it.

The question a sponsor actually pays to answer is not "can this protocol
recruit". It is "which rule is throwing patients away, and can I safely loosen
it" — asked *before* the protocol is signed, because afterwards the fix is a
protocol amendment.

The evidence for caring about this is unusually direct:

* 76% of trials now require an amendment, averaging 3.3 each, at $141k-$535k
  apiece; 16% of amendments change eligibility criteria and 23% of all
  amendments are judged avoidable
* current criteria deem 47.5% of patients still alive at six months ineligible
* trials using relaxed laboratory thresholds showed no increase in withdrawals
  for adverse events compared with stringent ones

So the counterfactual is not reckless. It is the analysis that stops a
$535,000 amendment 260 days after first patient in.

Everything here is computed from counts. A criterion's cost is measured by
re-running the cohort without it and comparing tiers — no patient leaves a
site, and the output is an aggregate exactly like every other number in this
system.
"""

from __future__ import annotations

from dataclasses import dataclass

from trialgrid.eligibility import Criterion, Patient, Tier
from trialgrid.engines import evaluate

#: One step of relaxation per numeric operator. Deliberately one step: the
#: point is to show the shape of the trade, not to search for a threshold that
#: makes the numbers look good.
_RELAX = {
    "less_than_or_equal": lambda v: str(int(float(v)) + 1),
    "less_than": lambda v: str(int(float(v)) + 1),
    "greater_than_or_equal": lambda v: str(int(float(v)) - 1),
    "greater_than": lambda v: str(int(float(v)) - 1),
}


@dataclass(frozen=True, slots=True)
class CriterionImpact:
    ref: str
    attribute: str
    wording: str
    #: Patients this criterion rules out outright.
    blocks: int
    #: Patients who are only "needs screening" because this is unanswered.
    unanswered: int
    #: Recruitable patients gained if this criterion were removed entirely.
    gain_if_removed: int
    #: The one-step relaxation, when the operator admits one.
    relaxed_to: str | None
    gain_if_relaxed: int

    @property
    def total_cost(self) -> int:
        """Patients this criterion currently keeps out of the trial."""
        return self.blocks + self.unanswered


def _recruitable(patients: list[Patient], criteria: list[Criterion]) -> int:
    """Eligible plus one-fact-away — the population a sponsor could actually reach."""
    assessments = evaluate(patients, criteria)
    return sum(a.tier is not Tier.NOT_ELIGIBLE for a in assessments)


def analyse(patients: list[Patient], criteria: list[Criterion]) -> list[CriterionImpact]:
    """Cost each criterion by removing it and by relaxing it one step.

    Returns criteria ordered by what they cost, most expensive first — which is
    the order a protocol author should read them in.
    """
    baseline_assessments = evaluate(patients, criteria)
    baseline = sum(a.tier is not Tier.NOT_ELIGIBLE for a in baseline_assessments)

    impacts: list[CriterionImpact] = []
    for c in criteria:
        blocks = sum(c.attribute in a.blocked_by for a in baseline_assessments)
        unanswered = sum(c.attribute in a.missing for a in baseline_assessments)

        without = [x for x in criteria if x.ref != c.ref]
        gain_removed = _recruitable(patients, without) - baseline

        relaxed_to: str | None = None
        gain_relaxed = 0
        relax = _RELAX.get(c.operator)
        if relax is not None:
            try:
                new_value = relax(c.value)
            except (TypeError, ValueError):
                new_value = None
            if new_value is not None:
                relaxed_to = f"{c.operator} {new_value}"
                swapped = [
                    Criterion(c.ref, c.kind, c.attribute, c.operator, new_value, c.wording)
                    if x.ref == c.ref
                    else x
                    for x in criteria
                ]
                gain_relaxed = _recruitable(patients, swapped) - baseline

        impacts.append(
            CriterionImpact(
                ref=c.ref,
                attribute=c.attribute,
                wording=c.wording,
                blocks=blocks,
                unanswered=unanswered,
                gain_if_removed=max(0, gain_removed),
                relaxed_to=relaxed_to,
                gain_if_relaxed=max(0, gain_relaxed),
            )
        )

    return sorted(impacts, key=lambda i: (-i.total_cost, i.ref))
