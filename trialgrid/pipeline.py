"""The role chain, and the switch that turns its protections off.

    Retriever -> Sanitizer -> Drafter -> Gatekeeper -> sites -> guard -> Challenger -> human

Each stage is a function here rather than a class, because the interesting
property is not the objects — it is what each stage is *handed*. The Drafter
receives cards and not documents. The site agents receive criteria and not
cards. Nothing that touches the web is ever passed a patient.

`safety_enabled=False` disables the Sanitizer's quarantine and the Gatekeeper's
verification while changing nothing else. It exists so the same question can be
asked twice and answered differently, which is the only honest way to show that
a safeguard does something. It is not a performance mode and it is not a
fallback — running it is how you demonstrate the failure you are preventing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from trialgrid.eligibility import Criterion, Kind
from trialgrid.provenance import GateResult, Verdict, gate
from trialgrid.sources import EvidenceCard, Source

#: Reasons the Sanitizer may raise. Mirrored here so the deterministic side can
#: recognise them without importing prompt text.
INJECTION_FLAGS = ("injected_instruction", "disclosure_request")

ModelCall = Callable[[str, str], str]
"""Takes (instructions, user_content) and returns the model's raw text."""


@dataclass
class Trace:
    """What happened, in the order it happened, for a human to read."""

    lines: list[str] = field(default_factory=list)

    def add(self, line: str) -> None:
        self.lines.append(line)

    def __str__(self) -> str:
        return "\n".join(self.lines)


def parse_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model reply. Returns {} rather than raising."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1].removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def sanitize(
    sources: list[Source],
    call: ModelCall,
    prompt: str,
    *,
    safety_enabled: bool = True,
    trace: Trace | None = None,
) -> list[EvidenceCard]:
    """Turn raw documents into cards. The only stage shown untrusted text."""
    payload = "\n\n".join(
        f"[{s.source_id}] {s.title}\nURL: {s.url}\n---\n{s.text}" for s in sources
    )
    data = parse_json(call(prompt, payload))

    cards: list[EvidenceCard] = []
    for raw in data.get("cards", []):
        if not isinstance(raw, dict):
            continue
        flags = tuple(str(f) for f in raw.get("quarantine_flags", []) if isinstance(f, str))
        if not safety_enabled:
            # The unguarded run keeps the card and forgets why it was suspect.
            flags = ()
        source_url = next(
            (s.url for s in sources if s.source_id == raw.get("source_id")), ""
        )
        card = EvidenceCard(
            card_id=str(raw.get("card_id", f"C{len(cards) + 1}")),
            claim=str(raw.get("claim", "")),
            verbatim_quote=str(raw.get("verbatim_quote", "")),
            source_id=str(raw.get("source_id", "")),
            source_url=source_url,
            quarantine_flags=flags,
        )
        cards.append(card)
        if trace is not None and card.quarantine_flags:
            trace.add(
                f"  QUARANTINE  {card.card_id} from {card.source_id}"
                f"  -> {', '.join(card.quarantine_flags)}"
            )
    return cards


def draft_criteria(
    cards: list[EvidenceCard], call: ModelCall, prompt: str
) -> tuple[list[Criterion], dict[str, str]]:
    """Turn cards into criteria. Never sees a document, never sees a patient.

    Returns the criteria and a map of criterion ref -> the card it cites, which
    is what the Gatekeeper verifies.
    """
    payload = json.dumps(
        [
            {
                "card_id": c.card_id,
                "claim": c.claim,
                "verbatim_quote": c.verbatim_quote,
                "source_id": c.source_id,
                "quarantine_flags": list(c.quarantine_flags),
            }
            for c in cards
        ],
        indent=2,
    )
    data = parse_json(call(prompt, payload))

    criteria: list[Criterion] = []
    refs: dict[str, str] = {}
    for raw in data.get("criteria", []):
        if not isinstance(raw, dict):
            continue
        ref = str(raw.get("ref", f"R{len(criteria) + 1}"))
        kind = Kind.EXCLUSION if str(raw.get("kind", "")).lower() == "exclusion" else Kind.INCLUSION
        criteria.append(
            Criterion(
                ref=ref,
                kind=kind,
                attribute=str(raw.get("attribute", "")),
                operator=str(raw.get("operator", "equals")),
                value=str(raw.get("value", "")),
                wording=str(raw.get("wording", "")),
            )
        )
        refs[ref] = str(raw.get("card_id", ""))
    return criteria, refs


def run_gate(
    cards: list[EvidenceCard],
    sources: list[Source],
    refs: dict[str, str],
    criteria: list[Criterion],
    *,
    safety_enabled: bool = True,
    trace: Trace | None = None,
) -> tuple[list[Criterion], GateResult]:
    """Verify provenance and drop any criterion that fails.

    With safety disabled the checks still *run* — so the trace can show what
    would have been caught — but nothing is dropped. That contrast is the
    demonstration.
    """
    result = gate(cards, sources, refs)

    if trace is not None:
        for v in result.violations:
            trace.add(f"  GATE        {v.rule}: {v.detail}")

    if not safety_enabled:
        if trace is not None and result.violations:
            trace.add(
                f"  GATE        SAFETY DISABLED - {len(result.violations)} violation(s) ignored"
            )
        return criteria, result

    admissible = set(result.admissible)
    kept = [c for c in criteria if refs.get(c.ref) in admissible]
    if trace is not None and len(kept) != len(criteria):
        trace.add(f"  GATE        kept {len(kept)} of {len(criteria)} criteria")
    return kept, result


def challenge(
    summary: str, counts: str, call: ModelCall, prompt: str
) -> dict[str, Any]:
    """Attack the draft. Sees counts and the draft; never a patient, never the web."""
    return parse_json(call(prompt, f"Counts:\n{counts}\n\nDraft summary:\n{summary}"))
