"""The approval token binds a human's signature to specific numbers."""

from __future__ import annotations

from trialgrid.agent_app import approval_token
from trialgrid.eligibility import Criterion, Kind
from trialgrid.guard import Disposition, SiteReturn, combine

CRITERIA = [Criterion("I1", Kind.INCLUSION, "ecog", "less_than_or_equal", "1", "ECOG 0-1")]
WIDENED = [Criterion("I1", Kind.INCLUSION, "ecog", "less_than_or_equal", "4", "ECOG 0-4")]


def _agg(eligible: int, *, abstain: bool = False):
    returns = [SiteReturn("a", Disposition.ANSWERED, eligible=eligible, gaps={"ecog": 7})]
    if abstain:
        returns.append(SiteReturn("b", Disposition.ABSTAINED))
    return combine(returns, sites_asked=len(returns))


def test_the_same_result_yields_the_same_token() -> None:
    assert approval_token(_agg(6), CRITERIA) == approval_token(_agg(6), CRITERIA)


def test_different_numbers_yield_a_different_token() -> None:
    """An approval cannot be replayed against a result the human never saw."""
    assert approval_token(_agg(6), CRITERIA) != approval_token(_agg(7), CRITERIA)


def test_a_site_joining_invalidates_a_prior_approval() -> None:
    assert approval_token(_agg(6), CRITERIA) != approval_token(_agg(6, abstain=True), CRITERIA)


def test_a_human_can_approve_by_typing() -> None:
    from trialgrid.agent_app import read_approval

    assert read_approval("APPROVE c0ebf445") == "c0ebf445"
    assert read_approval("approve: c0ebf445") == "c0ebf445"


def test_an_ordinary_question_is_not_an_approval() -> None:
    from trialgrid.agent_app import read_approval

    assert read_approval("Can this protocol recruit?") == ""
    assert read_approval("Do you approve of this approach?") == ""


def test_rewritten_criteria_invalidate_a_prior_approval() -> None:
    """A sponsor who approved a strict protocol has not approved a loosened one."""
    assert approval_token(_agg(6), CRITERIA) != approval_token(_agg(6), WIDENED)
