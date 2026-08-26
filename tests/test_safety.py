"""Tests for the properties the whole design rests on.

Each test names a promise made in the README. If someone removes the promise,
the test fails loudly rather than the demo quietly becoming a lie.
"""

from __future__ import annotations

import pytest

from trialgrid.eligibility import Criterion, Kind, Patient, Tier, assess, evaluate
from trialgrid.guard import (
    DEFAULT_MIN_CELL,
    SUPPRESSED,
    Disposition,
    EgressViolation,
    SiteReturn,
    check_shape,
    combine,
)

INCLUDE_EGFR = Criterion(
    "I2", Kind.INCLUSION, "egfr_uncommon_mutation", "equals", "present", "Uncommon EGFR mutation"
)
EXCLUDE_INFECTION = Criterion(
    "E1", Kind.EXCLUSION, "active_infection", "equals", "yes", "Active infection"
)
CRITERIA = [INCLUDE_EGFR, EXCLUDE_INFECTION]


# --- the founding rule ------------------------------------------------------


def test_a_hard_unknown_never_produces_not_eligible() -> None:
    """Missing information is a job to do, never a reason to drop someone."""
    patient = Patient("PT-001", {"active_infection": "no"})  # EGFR simply unanswered
    a = assess("PT-001", CRITERIA, evaluate(patient, CRITERIA))
    assert a.tier is Tier.NEEDS_SCREENING
    assert "egfr_uncommon_mutation" in a.missing


def test_the_missing_fact_is_named_not_counted() -> None:
    patient = Patient("PT-002", {"active_infection": "no"})
    a = assess("PT-002", CRITERIA, evaluate(patient, CRITERIA))
    assert a.missing == ("egfr_uncommon_mutation",)


def test_failure_is_decided_before_unknown() -> None:
    """A patient who genuinely fails is NOT_ELIGIBLE even with gaps elsewhere."""
    patient = Patient("PT-003", {"active_infection": "yes"})  # EGFR unanswered too
    a = assess("PT-003", CRITERIA, evaluate(patient, CRITERIA))
    assert a.tier is Tier.NOT_ELIGIBLE
    assert a.blocked_by == ("active_infection",)
    assert a.missing == ()  # already out; not also "work"


def test_an_unreadable_value_never_rejects_a_patient() -> None:
    """A gap in our dictionary is our problem, not the patient's."""
    numeric = Criterion("I3", Kind.INCLUSION, "ecog", "less_than_or_equal", "1", "ECOG 0-1")
    a = assess("PT-004", [numeric], evaluate(Patient("PT-004", {"ecog": "good"}), [numeric]))
    assert a.tier is Tier.NEEDS_SCREENING


# --- the federated rule -----------------------------------------------------


def test_an_abstaining_site_is_not_a_zero() -> None:
    """The thesis. A site that declines is unknown, never nought."""
    returns = [
        SiteReturn("a", Disposition.ANSWERED, eligible=6, needs_screening=9, not_eligible=4),
        SiteReturn("b", Disposition.ABSTAINED),
    ]
    agg = combine(returns, sites_asked=2)
    assert agg.sites_answered == 1
    assert agg.abstained == ("b",)
    assert agg.is_partial is True
    # the abstainer contributed nothing -- and is not silently counted as zero
    assert agg.eligible == 6


def test_a_full_network_is_not_flagged_partial() -> None:
    returns = [
        SiteReturn("a", Disposition.ANSWERED, eligible=6),
        SiteReturn("b", Disposition.ANSWERED, eligible=7),
    ]
    assert combine(returns, sites_asked=2).is_partial is False


# --- disclosure control -----------------------------------------------------


def test_small_cells_are_suppressed_not_rounded() -> None:
    returns = [SiteReturn("a", Disposition.ANSWERED, gaps={"rare_marker": 2, "ecog": 11})]
    agg = combine(returns, sites_asked=1)
    assert agg.gaps["rare_marker"] == SUPPRESSED
    assert agg.gaps["ecog"] == 11
    assert agg.suppressed_gaps == ("rare_marker",)


def test_suppression_is_visible_never_silent() -> None:
    returns = [SiteReturn("a", Disposition.ANSWERED, gaps={"rare_marker": 1})]
    agg = combine(returns, sites_asked=1)
    assert "rare_marker" in agg.gaps  # present, marked -- not quietly dropped


def test_the_threshold_cannot_be_lowered() -> None:
    returns = [SiteReturn("a", Disposition.ANSWERED, gaps={"rare_marker": 2})]
    with pytest.raises(EgressViolation):
        combine(returns, sites_asked=1, min_cell=DEFAULT_MIN_CELL - 1)


def test_pooling_happens_before_suppression() -> None:
    """Two sites with 3 each is 6 -- disclosable. Suppressing first would hide it."""
    returns = [
        SiteReturn("a", Disposition.ANSWERED, gaps={"ecog": 3}),
        SiteReturn("b", Disposition.ANSWERED, gaps={"ecog": 3}),
    ]
    assert combine(returns, sites_asked=2).gaps["ecog"] == 6


# --- the egress boundary ----------------------------------------------------


def test_the_wire_refuses_an_identifier() -> None:
    with pytest.raises(EgressViolation):
        check_shape({"site_id": "a", "gaps": {"patient_code": 3}})


def test_the_wire_refuses_an_unknown_field() -> None:
    with pytest.raises(EgressViolation):
        check_shape({"site_id": "a", "rows": [], "gaps": {}})


def test_the_wire_refuses_a_non_integer_count() -> None:
    with pytest.raises(EgressViolation):
        check_shape({"site_id": "a", "gaps": {"ecog": "lots"}})
