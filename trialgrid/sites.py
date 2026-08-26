"""Site agents and the synthetic cohorts they hold.

Each site holds its own screening log and never sees another's. A site agent
does exactly three things: evaluate its own patients against the protocol, ask
the guard whether what it is about to say is permitted, and answer or abstain.

It does not call a model. Eligibility is decided by rules, so there is nothing
for a model to do here — and a site with no model call is a site that cannot be
prompt-injected, which is worth more than the flexibility it gives up.

**The cohorts are synthetic and deliberately unequal.** Real networks are not
uniform: a specialist centre sequences everybody, a district hospital rarely
does. That asymmetry is the whole reason multi-site feasibility is hard, so a
demo with three identical sites would be demonstrating nothing.
"""

from __future__ import annotations

import random
from dataclasses import asdict

from trialgrid.eligibility import Criterion, Kind, Patient, Tier, assess_all
from trialgrid.guard import Disposition, SiteReturn, check_shape

#: Criteria in the shape of a real uncommon-EGFR NSCLC protocol. The wording is
#: paraphrased for the demo and is NOT lifted from any sponsor's document.
PROTOCOL_ID = "SYNTHETIC-EGFR-UNCOMMON-01"

CRITERIA: list[Criterion] = [
    Criterion("I1", Kind.INCLUSION, "histology", "equals", "adenocarcinoma",
              "Histologically confirmed lung adenocarcinoma"),
    Criterion("I2", Kind.INCLUSION, "egfr_uncommon_mutation", "equals", "present",
              "Documented uncommon EGFR mutation (G719X, S768I, L861Q)"),
    Criterion("I3", Kind.INCLUSION, "ecog", "less_than_or_equal", "1",
              "ECOG performance status 0 or 1"),
    Criterion("I4", Kind.INCLUSION, "measurable_disease", "equals", "yes",
              "At least one measurable lesion by RECIST v1.1"),
    Criterion("E1", Kind.EXCLUSION, "active_infection", "equals", "yes",
              "Active uncontrolled systemic infection"),
    Criterion("E2", Kind.EXCLUSION, "prior_egfr_tki", "equals", "yes",
              "Prior treatment with an EGFR tyrosine kinase inhibitor"),
]

#: site_id -> (cohort size, how often each attribute is actually recorded)
#: A specialist centre sequences nearly everyone; a district hospital does not.
_SITE_PROFILES: dict[str, tuple[int, dict[str, float]]] = {
    "addenbrookes": (28, {"egfr_uncommon_mutation": 0.85, "ecog": 0.90, "measurable_disease": 0.95}),
    "royal-papworth": (22, {"egfr_uncommon_mutation": 0.35, "ecog": 0.80, "measurable_disease": 0.85}),
    "west-suffolk": (17, {"egfr_uncommon_mutation": 0.20, "ecog": 0.55, "measurable_disease": 0.70}),
}


def cohort(site_id: str) -> list[Patient]:
    """Build one site's synthetic screening log. Deterministic per site."""
    size, recorded = _SITE_PROFILES[site_id]
    rng = random.Random(f"trialgrid/{site_id}")
    patients: list[Patient] = []

    for n in range(1, size + 1):
        facts: dict[str, str] = {
            "histology": rng.choice(["adenocarcinoma"] * 8 + ["squamous", "small cell"]),
            "active_infection": rng.choice(["no"] * 9 + ["yes"]),
            "prior_egfr_tki": rng.choice(["no"] * 8 + ["yes", "yes"]),
        }
        # Attributes a site may simply never have recorded. A blank is not a
        # "no" — it is an unanswered question, and the engine treats it that way.
        if rng.random() < recorded["egfr_uncommon_mutation"]:
            facts["egfr_uncommon_mutation"] = rng.choice(["present", "present", "absent"])
        elif rng.random() < 0.4:
            facts["egfr_uncommon_mutation"] = "pending"  # at the lab, chase it
        if rng.random() < recorded["ecog"]:
            facts["ecog"] = rng.choice(["0", "1", "1", "2"])
        if rng.random() < recorded["measurable_disease"]:
            facts["measurable_disease"] = rng.choice(["yes"] * 4 + ["no"])

        patients.append(Patient(code=f"{site_id.upper()[:3]}-{n:03d}", facts=facts))
    return patients


def run_site(
    site_id: str, *, criteria: list[Criterion] | None = None, abstain: bool = False
) -> SiteReturn:
    """Evaluate one site's cohort locally and emit only what the wire carries.

    A site that abstains returns a marked abstention, never a zero. The
    coordinator must be able to tell "nobody here" apart from "we did not look".
    """
    if abstain:
        return SiteReturn(
            site_id=site_id,
            disposition=Disposition.ABSTAINED,
            note="data controller declined: no approval in place for this protocol",
        )

    assessments = assess_all(cohort(site_id), criteria if criteria is not None else CRITERIA)

    gaps: dict[str, int] = {}
    for a in assessments:
        for attribute in a.missing:
            gaps[attribute] = gaps.get(attribute, 0) + 1

    payload = {
        "site_id": site_id,
        "disposition": Disposition.ANSWERED,
        "eligible": sum(a.tier is Tier.ELIGIBLE for a in assessments),
        "needs_screening": sum(a.tier is Tier.NEEDS_SCREENING for a in assessments),
        "not_eligible": sum(a.tier is Tier.NOT_ELIGIBLE for a in assessments),
        "gaps": gaps,
        "note": "",
    }

    # Ask the guard before speaking, not after. If this raises, the site says
    # nothing rather than saying something it should not have.
    check_shape(payload)
    return SiteReturn(**payload)


def all_site_ids() -> list[str]:
    return list(_SITE_PROFILES)
