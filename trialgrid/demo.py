"""The demonstration: the same question, asked twice, answered differently.

    python -m trialgrid.demo

No network, no Flower runtime, no API key. Runs in milliseconds and shows the
entire argument: with the safeguards on, a hostile document is caught and the
protocol's real criteria survive. With them off, the same document rewrites the
eligibility criteria and the feasibility answer silently inflates.

The second run is not a strawman. It is the identical code path with two checks
disabled, which is what most systems in this space actually are.
"""

from __future__ import annotations

import time

from trialgrid.agent_app import approval_token, render_counts
from trialgrid.guard import combine
from trialgrid.offline import scripted_model
from trialgrid.pipeline import Trace, draft_criteria, run_gate, sanitize
from trialgrid.prompts import DRAFTER, SANITIZER
from trialgrid.sites import all_site_ids, run_site
from trialgrid.sources import fixture_sources

QUESTION = "We are opening the uncommon-EGFR NSCLC protocol. Can it recruit across our network?"


def run(*, safety_enabled: bool, abstaining: str = "west-suffolk"):
    sources = fixture_sources(include_poisoned=True)
    trace = Trace()
    trace.add(f"  SAFETY      {'ENABLED' if safety_enabled else '*** DISABLED ***'}")
    trace.add(f"  RETRIEVED   {len(sources)} sources (1 hostile)")

    cards = sanitize(
        sources, scripted_model, SANITIZER, safety_enabled=safety_enabled, trace=trace
    )
    trace.add(f"  SANITIZED   {len(cards)} evidence cards")

    criteria, refs = draft_criteria(cards, scripted_model, DRAFTER)
    trace.add(f"  DRAFTED     {len(criteria)} criteria")

    criteria, _ = run_gate(
        cards, sources, refs, criteria, safety_enabled=safety_enabled, trace=trace
    )

    trace.add("")
    trace.add("  CRITERIA IN FORCE")
    for c in criteria:
        trace.add(f"    {c.ref:4} {c.kind.value:10} {c.attribute} {c.operator} {c.value}")

    site_ids = all_site_ids()
    returns = [run_site(s, criteria=criteria, abstain=(s == abstaining)) for s in site_ids]
    aggregate = combine(returns, sites_asked=len(site_ids))

    print(trace)
    print(render_counts(aggregate))
    if safety_enabled:
        print(f"\n  BLOCKED - AWAITING SPONSOR SIGN-OFF   token "
              f"{approval_token(aggregate, criteria)}")
    return aggregate, criteria


def main() -> None:
    started = time.perf_counter()

    print("\n" + "=" * 72)
    print("  RUN 1 - safeguards ON")
    print("=" * 72)
    guarded, guarded_criteria = run(safety_enabled=True)

    print("\n" + "=" * 72)
    print("  RUN 2 - same question, same sources, safeguards OFF")
    print("=" * 72)
    unguarded, unguarded_criteria = run(safety_enabled=False)

    print("\n" + "=" * 72)
    print("  THE DIFFERENCE")
    print("=" * 72)

    def ecog(criteria):
        return next((c for c in criteria if c.attribute == "ecog"), None)

    g, u = ecog(guarded_criteria), ecog(unguarded_criteria)
    print(f"\n  ECOG criterion, guarded    : "
          f"{g.operator + ' ' + g.value if g else 'dropped (unverifiable)'}")
    print(f"  ECOG criterion, unguarded  : "
          f"{u.operator + ' ' + u.value if u else 'dropped'}"
          f"{'   <- rewritten by the hostile page' if u and u.value == '4' else ''}")
    print(f"\n  Recruitable (needs screening), guarded   : {guarded.needs_screening}")
    print(f"  Recruitable (needs screening), unguarded : {unguarded.needs_screening}")
    print(f"\n  Eligible today, guarded   : {guarded.eligible}")
    print(f"  Eligible today, unguarded : {unguarded.eligible}")
    print(
        "\n  Same question. Same sources. The unguarded run reports a protocol"
        "\n  that recruits better than it does, because a web page said so."
    )
    print(f"\n  both runs: {time.perf_counter() - started:.3f}s, zero network calls\n")


if __name__ == "__main__":
    main()
