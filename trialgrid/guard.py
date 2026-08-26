"""The egress guard. Deterministic Python, and deliberately not a model.

Everything a site sends across the wire passes through here first. It is the
boundary the whole design rests on, so it is written to be read by someone who
does not trust it: no network, no I/O, no imports beyond the standard library,
and no branch that depends on anything a language model said.

Two rules do the work.

**Small cells are suppressed, not rounded.** Rounding a count of 2 to "fewer
than 5" still tells you the stratum exists and is small. In a rare-mutation
cohort at a named hospital that can be enough to identify a person. So a
stratum below the threshold is removed and replaced by an explicit marker,
and the marker is visible in the output rather than silently absent.

**An abstaining site is not a zero.** If a site declines, errors, or times out,
its contribution is *unknown*, not nought. Imputing zero would understate a
network's true recruitment and would do it in exactly the direction that kills
a trial: it makes a viable protocol look unviable. So the aggregate carries how
many sites answered, and any consumer must state it.

That second rule is the founding product rule — a missing lab result is not a
"no" — applied to institutions instead of patients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

#: Below this, a stratum is suppressed. Configurable upward, never downward.
DEFAULT_MIN_CELL = 5

#: Marker that replaces a suppressed count. Present in the output on purpose:
#: a reader must be able to see that something was withheld.
SUPPRESSED = "SUPPRESSED"


class Disposition(StrEnum):
    ANSWERED = "ANSWERED"
    #: The site chose not to answer, or could not. Never a zero.
    ABSTAINED = "ABSTAINED"
    #: The site tried to send something it was not allowed to send.
    REFUSED = "REFUSED"


class EgressViolation(Exception):
    """A site tried to emit something the wire does not carry."""


@dataclass(frozen=True, slots=True)
class SiteReturn:
    """The only shape a site is permitted to emit.

    Scalar counts and attribute *names*. There is no field that can hold a
    patient code, a row, or free text, so a compromised site agent cannot
    smuggle one out — the transport simply has nowhere to put it.
    """

    site_id: str
    disposition: Disposition
    eligible: int = 0
    needs_screening: int = 0
    not_eligible: int = 0
    #: attribute name -> how many patients are waiting on it.
    gaps: dict[str, int] = field(default_factory=dict)
    note: str = ""

    @property
    def screened(self) -> int:
        return self.eligible + self.needs_screening + self.not_eligible


@dataclass(frozen=True, slots=True)
class Aggregate:
    sites_asked: int
    sites_answered: int
    abstained: tuple[str, ...]
    eligible: int
    needs_screening: int
    not_eligible: int
    #: attribute -> count, or the SUPPRESSED marker.
    gaps: dict[str, int | str]
    suppressed_gaps: tuple[str, ...]
    min_cell: int

    @property
    def is_partial(self) -> bool:
        """True when at least one site did not answer.

        A consumer that reports these numbers without saying so is misreporting
        them, and `phrase_instructions()` says exactly that to the model.
        """
        return self.sites_answered < self.sites_asked


_ALLOWED_KEYS = {f for f in SiteReturn.__slots__}
#: Substrings that must never appear in a key crossing the wire.
_FORBIDDEN = ("patient", "code", "mrn", "nhs", "dob", "name", "id_")


def check_shape(payload: dict[str, object]) -> None:
    """Refuse a payload rather than sanitise it.

    Stripping a bad field teaches nobody anything and hides a bug. Refusing is
    loud, and loud is what you want on the egress path.
    """
    for key in payload:
        if key not in _ALLOWED_KEYS:
            raise EgressViolation(f"field {key!r} is not permitted on the wire")
    gaps = payload.get("gaps") or {}
    if not isinstance(gaps, dict):
        raise EgressViolation("gaps must be a mapping of attribute name to count")
    for attribute, count in gaps.items():
        low = str(attribute).lower()
        if any(token in low for token in _FORBIDDEN):
            raise EgressViolation(f"gap key {attribute!r} looks like an identifier")
        if not isinstance(count, int) or isinstance(count, bool):
            raise EgressViolation(f"gap {attribute!r} must be an integer count")


def combine(
    returns: list[SiteReturn], *, sites_asked: int, min_cell: int = DEFAULT_MIN_CELL
) -> Aggregate:
    """Pool site returns, suppressing small cells and preserving abstention."""
    if min_cell < DEFAULT_MIN_CELL:
        # Configurable upward only. A demo that quietly lowers the threshold to
        # make the numbers look better is the exact failure this guards against.
        raise EgressViolation(f"min_cell may not be lowered below {DEFAULT_MIN_CELL}")

    answered = [r for r in returns if r.disposition is Disposition.ANSWERED]
    withheld = tuple(
        sorted(r.site_id for r in returns if r.disposition is not Disposition.ANSWERED)
    )

    pooled: dict[str, int] = {}
    for r in answered:
        for attribute, count in r.gaps.items():
            pooled[attribute] = pooled.get(attribute, 0) + count

    gaps: dict[str, int | str] = {}
    suppressed: list[str] = []
    for attribute, count in sorted(pooled.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < min_cell:
            gaps[attribute] = SUPPRESSED
            suppressed.append(attribute)
        else:
            gaps[attribute] = count

    return Aggregate(
        sites_asked=sites_asked,
        sites_answered=len(answered),
        abstained=withheld,
        eligible=sum(r.eligible for r in answered),
        needs_screening=sum(r.needs_screening for r in answered),
        not_eligible=sum(r.not_eligible for r in answered),
        gaps=gaps,
        suppressed_gaps=tuple(suppressed),
        min_cell=min_cell,
    )
