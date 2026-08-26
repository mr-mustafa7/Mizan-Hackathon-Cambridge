"""The deterministic core, with no Flower runtime and no model call.

    python -m trialgrid.demo

Exists so the safety story can be demonstrated when the network cannot be. What
it prints is exactly what the AgentApp prints between its two model calls --
the part that decides anything.
"""

from __future__ import annotations

import sys
import time

from trialgrid.agent_app import approval_token, render
from trialgrid.guard import combine
from trialgrid.sites import all_site_ids, run_site


def main(abstaining: str = "west-suffolk") -> None:
    started = time.perf_counter()
    site_ids = all_site_ids()

    print(f"\n  Asking {len(site_ids)} sites. Each evaluates its own log; none sees another's.")
    returns = []
    for site_id in site_ids:
        r = run_site(site_id, abstain=(site_id == abstaining))
        mark = "ABSTAINED" if site_id == abstaining else f"{r.screened} screened"
        print(f"    {site_id:18} {mark}")
        returns.append(r)

    aggregate = combine(returns, sites_asked=len(site_ids))
    print(render(aggregate))
    print(f"\n  BLOCKED - AWAITING SPONSOR SIGN-OFF   token {approval_token(aggregate)}")
    print(f"  deterministic core: {time.perf_counter() - started:.3f}s, zero model calls\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "west-suffolk")
