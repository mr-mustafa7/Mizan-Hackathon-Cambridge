"""The Gatekeeper. Deterministic, unpersuadable, and not a model.

Everything upstream of this file is advisory. The Sanitizer is a detector, the
Challenger is a critic, and both are language models that can be argued with.
This module is the control, and it works by checking rather than believing:

* a criterion may only cite a card that exists
* that card must carry no quarantine flag
* that card's source must be on the allowlist
* the card's verbatim quote must ACTUALLY OCCUR in the source text

The last check is the one that matters most and it costs almost nothing. A
model that invents a supporting quote fails it mechanically. There is no
phrasing of a prompt that makes a substring appear in a document it is not in.

If every language model in this system were replaced with one that lies as
convincingly as possible, the worst it could achieve is an empty criteria set
and a blocked run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from trialgrid.sources import EvidenceCard, Source

#: Phrases that turn a population summary into direction for one patient. This
#: system reports feasibility to research staff; it does not advise on care.
_INDIVIDUALISED_ADVICE = (
    r"\byou should (?:take|start|stop|switch)\b",
    r"\bwe recommend that (?:you|the patient|this patient)\b",
    r"\bprescribe\b",
    r"\byour dose\b",
    r"\bthis patient should\b",
)


class Verdict(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class Violation:
    rule: str
    detail: str


@dataclass(frozen=True, slots=True)
class GateResult:
    verdict: Verdict
    violations: tuple[Violation, ...] = field(default=())
    #: Cards that survived every check and may support a criterion.
    admissible: tuple[str, ...] = field(default=())

    @property
    def passed(self) -> bool:
        return self.verdict is Verdict.PASS


def _normalise(text: str) -> str:
    """Collapse whitespace so a quote matches across reflowed text."""
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_cards(
    cards: list[EvidenceCard], sources: list[Source]
) -> tuple[list[EvidenceCard], list[Violation]]:
    """Return the cards that may be cited, and why the others may not.

    A rejected card is not deleted. It stays visible in the trace, because a
    reviewer needs to see what was thrown away and on what grounds.
    """
    by_id = {s.source_id: s for s in sources}
    admissible: list[EvidenceCard] = []
    violations: list[Violation] = []

    for card in cards:
        if card.quarantine_flags:
            violations.append(
                Violation(
                    "quarantined_card",
                    f"{card.card_id} flagged: {', '.join(card.quarantine_flags)}",
                )
            )
            continue

        source = by_id.get(card.source_id)
        if source is None:
            violations.append(
                Violation("unknown_source", f"{card.card_id} cites missing source {card.source_id}")
            )
            continue

        if not source.is_allowlisted:
            violations.append(
                Violation(
                    "source_not_allowlisted",
                    f"{card.card_id} cites {source.domain}, which is not an approved source",
                )
            )
            continue

        # The check a model cannot talk its way past.
        if _normalise(card.verbatim_quote) not in _normalise(source.text):
            violations.append(
                Violation(
                    "quote_not_in_source",
                    f"{card.card_id} quotes text that does not occur in {source.source_id}",
                )
            )
            continue

        admissible.append(card)

    return admissible, violations


def verify_criteria(criteria_refs: dict[str, str], admissible_ids: set[str]) -> list[Violation]:
    """Every criterion must trace to an admissible card. No exceptions."""
    violations: list[Violation] = []
    for ref, card_id in criteria_refs.items():
        if card_id not in admissible_ids:
            violations.append(
                Violation(
                    "criterion_without_evidence",
                    f"criterion {ref} cites {card_id or '<nothing>'}, which is not admissible",
                )
            )
    return violations


def check_disclosure_text(text: str) -> list[Violation]:
    """Refuse output that reads as advice about an individual patient."""
    violations: list[Violation] = []
    for pattern in _INDIVIDUALISED_ADVICE:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            violations.append(
                Violation("individualised_advice", f"output contains {match.group(0)!r}")
            )
    return violations


def gate(
    cards: list[EvidenceCard],
    sources: list[Source],
    criteria_refs: dict[str, str],
) -> GateResult:
    """Run every check. Any violation blocks."""
    admissible, violations = verify_cards(cards, sources)
    admissible_ids = {c.card_id for c in admissible}
    violations = list(violations) + verify_criteria(criteria_refs, admissible_ids)

    # A criteria set with nothing in it is a failure, not a permissive pass.
    if not criteria_refs:
        violations.append(
            Violation("no_criteria", "no criterion survived verification; nothing to evaluate")
        )

    return GateResult(
        verdict=Verdict.BLOCKED if violations else Verdict.PASS,
        violations=tuple(violations),
        admissible=tuple(sorted(admissible_ids)),
    )
