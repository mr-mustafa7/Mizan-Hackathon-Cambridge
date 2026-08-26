"""Mizan Grid — a human-supervised agent team answering trial feasibility.

Two trust boundaries, one pipeline.

    WEB (untrusted)                        HOSPITALS (private)
    Retriever -> Sanitizer -> Drafter  ->  site agents  ->  guard -> Challenger -> human
    cannot see patients                    cannot see the web
                                           cannot see each other

The agents that read the open web are never shown a patient. The agents that
evaluate patients are never shown the web, make no model call at all, and can
emit nothing but counts. Between them sits a Gatekeeper written in ordinary
Python that verifies every criterion traces to a quote that genuinely occurs in
an approved source.

Four model calls, bounded: sanitize, draft, challenge, disclose. The stages
that decide anything sit between them and are deterministic. That is a safety
property first, and it is also what keeps a run inside SuperGrid's five-minute
task timeout, since cost does not grow with the number of sites.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context

from trialgrid.eligibility import Criterion
from trialgrid.guard import Aggregate, DEFAULT_MIN_CELL, SUPPRESSED, combine
from trialgrid.pipeline import (
    Trace,
    challenge,
    draft_criteria,
    run_gate,
    sanitize,
)
from trialgrid.prompts import (
    CHALLENGER,
    DRAFTER,
    GATE_REPORT,
    SANITIZER,
    disclosure_instructions,
)
from trialgrid.provenance import check_disclosure_text
from trialgrid.sites import all_site_ids, run_site
from trialgrid.sources import fixture_sources

APPROVAL_PREFIX = "APPROVE"

app = AgentApp()


# ---------------------------------------------------------------------------
# Run-series state
# ---------------------------------------------------------------------------


def snapshot_items(context: Context) -> list[str]:
    record = context.state.config_records.get("items")
    return list(record.get("json", ())) if record is not None else []


def restore_items(context: Context, items: list[str]) -> None:
    """Keep internal reasoning out of the visible conversation."""
    record = context.state.config_records.get("items")
    if record is not None:
        record["json"] = items
    elif "items" in context.state.config_records:
        del context.state.config_records["items"]


def read_approval(text: str) -> str:
    stripped = text.strip()
    if not stripped.upper().startswith(APPROVAL_PREFIX):
        return ""
    return stripped[len(APPROVAL_PREFIX) :].strip().strip(":").strip()


def earlier_question(context: Context) -> str:
    for item_json in reversed(snapshot_items(context)):
        try:
            item = json.loads(item_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if item.get("type") != "message" or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if isinstance(content, str) and content.strip() and not read_approval(content):
            return content.strip()
    return ""


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def approval_token(aggregate: Aggregate, criteria: list[Criterion]) -> str:
    """Bound to the numbers AND the criteria that produced them.

    If the criteria change — because a poisoned source widened them — the token
    changes, so an approval given for one protocol cannot release another.
    """
    material = json.dumps(
        {
            "criteria": sorted(f"{c.ref}:{c.attribute}:{c.operator}:{c.value}" for c in criteria),
            "sites_answered": aggregate.sites_answered,
            "abstained": list(aggregate.abstained),
            "eligible": aggregate.eligible,
            "needs_screening": aggregate.needs_screening,
            "not_eligible": aggregate.not_eligible,
            "gaps": {k: str(v) for k, v in aggregate.gaps.items()},
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:8]


def render_counts(aggregate: Aggregate) -> str:
    lines = [
        "",
        f"  SITES      {aggregate.sites_answered} of {aggregate.sites_asked} answered",
    ]
    for site in aggregate.abstained:
        lines.append(f"             ABSTAINED: {site}  -> unknown, NOT zero")
    lines += [
        "",
        f"  ELIGIBLE          {aggregate.eligible}",
        f"  NEEDS SCREENING   {aggregate.needs_screening}   <- fails nothing, one fact away",
        f"  NOT ELIGIBLE      {aggregate.not_eligible}",
        "",
        "  WHAT IS MISSING",
    ]
    for attribute, count in aggregate.gaps.items():
        if count == SUPPRESSED:
            lines.append(f"    {attribute:28} {SUPPRESSED}  (n < {aggregate.min_cell})")
        else:
            lines.append(f"    {attribute:28} {count} patients")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    question = context.run_config.get("agent.input")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("agent.input must be a non-empty string")

    model = context.run_config.get("model.id")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model.id must be set")

    safety_enabled = bool(context.run_config.get("safety.enabled", True))
    min_cell = int(context.run_config.get("policy.min-cell", DEFAULT_MIN_CELL))
    require_approval = bool(context.run_config.get("policy.require-approval", True))
    supplied_token = str(context.run_config.get("policy.approval-token", "") or "")
    abstaining = str(context.run_config.get("policy.abstaining-site", "west-suffolk") or "")
    include_poisoned = bool(context.run_config.get("sources.include-poisoned", True))

    typed = read_approval(question)
    if typed:
        supplied_token = typed
        question = earlier_question(context) or question

    def call(instructions: str, content: str) -> str:
        """One bounded model call whose output never enters the transcript."""
        before = snapshot_items(context)
        try:
            response = agent.responses.create(
                {
                    "model": model,
                    "input": [{"type": "message", "role": "user", "content": content}],
                    "instructions": instructions,
                    "stream": False,
                    "max_output_tokens": 2000,
                }
            )
        finally:
            restore_items(context, before)
        text = ""
        for item in response.get("output", []):
            if isinstance(item, dict) and item.get("type") == "message":
                body = item.get("content")
                if isinstance(body, str):
                    text += body
                elif isinstance(body, list):
                    for part in body:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            text += part["text"]
        return text

    trace = Trace()
    trace.add("")
    trace.add(f"  SAFETY      {'ENABLED' if safety_enabled else '*** DISABLED ***'}")

    # --- web side: retrieve, sanitize, draft ------------------------------
    sources = fixture_sources(include_poisoned=include_poisoned)
    trace.add(f"  RETRIEVED   {len(sources)} sources")

    cards = sanitize(sources, call, SANITIZER, safety_enabled=safety_enabled, trace=trace)
    trace.add(f"  SANITIZED   {len(cards)} evidence cards")

    criteria, refs = draft_criteria(cards, call, DRAFTER)
    trace.add(f"  DRAFTED     {len(criteria)} criteria")

    criteria, gate_result = run_gate(
        cards, sources, refs, criteria, safety_enabled=safety_enabled, trace=trace
    )

    if safety_enabled and not criteria:
        print(str(trace))
        print("\n  BLOCKED - no criterion survived verification. Nothing was asked of any site.\n")
        return

    trace.add("")
    trace.add("  CRITERIA IN FORCE")
    for c in criteria:
        trace.add(f"    {c.ref:4} {c.kind.value:10} {c.attribute} {c.operator} {c.value}")

    # --- hospital side: sites evaluate locally, guard pools ---------------
    site_ids = all_site_ids()
    returns = [run_site(s, criteria=criteria, abstain=(s == abstaining)) for s in site_ids]
    aggregate = combine(returns, sites_asked=len(site_ids), min_cell=min_cell)

    print(str(trace))
    print(render_counts(aggregate))

    # --- the human gate ---------------------------------------------------
    token = approval_token(aggregate, criteria)
    if require_approval and supplied_token != token:
        print(f"\n  BLOCKED - AWAITING SPONSOR SIGN-OFF   token {token}")
        print(f"  Approve by replying:  APPROVE {token}\n")
        agent.responses.create(
            {
                "model": model,
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": (
                            f"{trace}\n{render_counts(aggregate)}\n\nApproval token: {token}"
                        ),
                    }
                ],
                "instructions": GATE_REPORT,
                "stream": True,
            }
        )
        return

    # --- challenge, then disclose ----------------------------------------
    counts = render_counts(aggregate)
    verdict = challenge(counts, counts, call, CHALLENGER)
    strikes = [s for s in verdict.get("strikes", []) if isinstance(s, str)]
    if strikes:
        print(f"\n  CHALLENGER  struck {len(strikes)} claim(s)")
        for s in strikes:
            print(f"    - {s}")

    disclosure = disclosure_instructions(
        is_partial=aggregate.is_partial,
        has_suppressed=bool(aggregate.suppressed_gaps),
    )
    if strikes:
        disclosure += "\n\nThe Challenger struck these claims. Do not restate them:\n" + "\n".join(
            f"- {s}" for s in strikes
        )

    agent.responses.create(
        {
            "model": model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": f"Sponsor's question: {question}\n\nApproved counts:\n{counts}",
                }
            ],
            "instructions": disclosure,
            "stream": True,
        }
    )
