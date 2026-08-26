"""The Gatekeeper's promises. Each test removes one and proves it was load-bearing."""

from __future__ import annotations

from trialgrid.offline import scripted_model
from trialgrid.pipeline import draft_criteria, run_gate, sanitize
from trialgrid.prompts import DRAFTER, SANITIZER
from trialgrid.provenance import Verdict, check_disclosure_text, gate
from trialgrid.sources import POISONED_SOURCE, EvidenceCard, Source, fixture_sources

CLEAN = Source("S1", "https://clinicaltrials.gov/study/X", "X", "ECOG performance status of 0 or 1.")
SHADY = Source("S9", "https://pharma-marketing.example.com/x", "X", "Anything you like.")


def _card(**kw) -> EvidenceCard:
    base = dict(
        card_id="C1", claim="c", verbatim_quote="ECOG performance status of 0 or 1.",
        source_id="S1", source_url=CLEAN.url,
    )
    base.update(kw)
    return EvidenceCard(**base)


# --- the check a model cannot argue with ------------------------------------


def test_a_fabricated_quote_is_rejected() -> None:
    """The strongest control here: the quote must actually occur in the source.

    No prompt phrasing makes a substring appear in a document it is not in.
    """
    invented = _card(verbatim_quote="ECOG performance status of 0, 1, 2, 3 or 4.")
    result = gate([invented], [CLEAN], {"I1": "C1"})
    assert result.verdict is Verdict.BLOCKED
    assert any(v.rule == "quote_not_in_source" for v in result.violations)


def test_a_genuine_quote_passes() -> None:
    assert gate([_card()], [CLEAN], {"I1": "C1"}).verdict is Verdict.PASS


def test_whitespace_differences_do_not_break_a_genuine_quote() -> None:
    reflowed = _card(verbatim_quote="ECOG   performance\nstatus of 0 or 1.")
    assert gate([reflowed], [CLEAN], {"I1": "C1"}).verdict is Verdict.PASS


# --- source and quarantine boundaries ---------------------------------------


def test_a_non_allowlisted_source_cannot_support_a_criterion() -> None:
    card = _card(source_id="S9", verbatim_quote="Anything you like.")
    result = gate([card], [SHADY], {"I1": "C1"})
    assert result.verdict is Verdict.BLOCKED
    assert any(v.rule == "source_not_allowlisted" for v in result.violations)


def test_a_quarantined_card_cannot_support_a_criterion() -> None:
    card = _card(quarantine_flags=("injected_instruction",))
    result = gate([card], [CLEAN], {"I1": "C1"})
    assert result.verdict is Verdict.BLOCKED
    assert any(v.rule == "quarantined_card" for v in result.violations)


def test_an_empty_criteria_set_blocks_rather_than_passing() -> None:
    """Nothing to check must never read as nothing wrong."""
    assert gate([_card()], [CLEAN], {}).verdict is Verdict.BLOCKED


def test_a_criterion_citing_nothing_is_refused() -> None:
    result = gate([_card()], [CLEAN], {"I1": ""})
    assert any(v.rule == "criterion_without_evidence" for v in result.violations)


# --- individualised advice ---------------------------------------------------


def test_population_language_is_allowed() -> None:
    assert check_disclosure_text("12 patients fail nothing and await one fact.") == []


def test_advice_about_a_person_is_refused() -> None:
    assert check_disclosure_text("This patient should start osimertinib.") != []
    assert check_disclosure_text("We recommend that you take 80mg daily.") != []


# --- the end-to-end contrast -------------------------------------------------


def _pipeline(*, safety_enabled: bool):
    sources = fixture_sources(include_poisoned=True)
    cards = sanitize(sources, scripted_model, SANITIZER, safety_enabled=safety_enabled)
    criteria, refs = draft_criteria(cards, scripted_model, DRAFTER)
    kept, result = run_gate(cards, sources, refs, criteria, safety_enabled=safety_enabled)
    return kept, result


def test_the_hostile_document_is_quarantined_when_safety_is_on() -> None:
    cards = sanitize(
        fixture_sources(), scripted_model, SANITIZER, safety_enabled=True
    )
    hostile = [c for c in cards if c.source_id == POISONED_SOURCE.source_id]
    assert hostile, "the hostile source should still produce cards, so a human can see it"
    assert all(c.quarantine_flags for c in hostile)
    assert all(not c.is_clean for c in hostile)


def test_safety_on_keeps_the_real_criterion() -> None:
    kept, _ = _pipeline(safety_enabled=True)
    ecog = next(c for c in kept if c.attribute == "ecog")
    assert ecog.value == "1", "the protocol's real ECOG limit must survive"


def test_safety_off_lets_the_hostile_page_rewrite_the_protocol() -> None:
    """The failure being prevented. If this ever passes cleanly, the demo is a lie."""
    kept, result = _pipeline(safety_enabled=False)
    ecog = next(c for c in kept if c.attribute == "ecog")
    assert ecog.value == "4", "unguarded, the injected criterion should take effect"
    assert result.violations, "the violations should still be detected, just ignored"
