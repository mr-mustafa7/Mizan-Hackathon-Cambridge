"""TrialGrid — a human-supervised agent team answering multi-site feasibility.

    site agents (rules only, no model)  ->  egress guard  ->  coordinator  ->  human  ->  answer

A sponsor asks whether a protocol can recruit across a network. Each site
answers from its own screening log; nothing but counts crosses the wire; a
human approves before any number is released.

**Two model calls, total.** The sponsor's question is turned into a protocol
selection once, and the approved aggregate is phrased once. Everything between
them is deterministic. That is a safety property first — no model decides who
is eligible — and it is also what keeps the run inside SuperGrid's five-minute
task timeout, since the expensive steps do not scale with the number of sites.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context

from trialgrid.guard import (
    Aggregate,
    DEFAULT_MIN_CELL,
    SUPPRESSED,
    EgressViolation,
    combine,
)
from trialgrid.prompts import GATE_REPORT, ROUTER, disclosure_instructions
from trialgrid.sites import CRITERIA, PROTOCOL_ID, all_site_ids, run_site

#: Protocols this deployment is allowed to run. The model may choose from this
#: list; it may not invent an entry. A choice outside it is a refusal, not a
#: best-effort match.
PROTOCOL_ALLOWLIST = (PROTOCOL_ID,)

#: The only shape of answer this system will produce. A request for anything
#: else is refused here, before a site is asked. This check is what makes the
#: model's compliance with an injected instruction harmless: it can agree to
#: list patients, and the request still dies on this line.
QUERY_SHAPE_ALLOWLIST = ("counts",)

app = AgentApp()

def snapshot_items(context: Context) -> list[str]:
    """Copy the run series' stored conversation items."""
    record = context.state.config_records.get("items")
    return list(record.get("json", ())) if record is not None else []


def restore_items(context: Context, items: list[str]) -> None:
    """Put the run series' stored items back exactly as they were.

    Used around the routing call so its raw JSON output never becomes part of
    the visible conversation. A judge should see the site table and the
    decisions, not the machinery that produced them.
    """
    record = context.state.config_records.get("items")
    if record is not None:
        record["json"] = items
    elif "items" in context.state.config_records:
        del context.state.config_records["items"]


#: A human approves by typing this, because browser chat cannot pass run-config.
#: Deliberately an explicit word plus the exact token: it cannot be produced by
#: accident, and the token still binds the approval to the numbers that were
#: actually shown.
APPROVAL_PREFIX = "APPROVE"


def read_approval(text: str) -> str:
    """Return the token a human typed, or empty string if this is not an approval."""
    stripped = text.strip()
    if not stripped.upper().startswith(APPROVAL_PREFIX):
        return ""
    return stripped[len(APPROVAL_PREFIX):].strip().strip(":").strip()


def earlier_question(context: Context) -> str:
    """The last real question in this conversation, skipping approvals.

    Needed because an approval message replaces the question in `agent.input`,
    but the run still has to know what was being asked.
    """
    items_record = context.state.config_records.get("items")
    items = items_record.get("json", []) if items_record is not None else []
    for item_json in reversed(list(items)):
        try:
            item = json.loads(item_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if item.get("type") != "message" or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if isinstance(content, str) and content.strip() and not read_approval(content):
            return content.strip()
    return ""



def approval_token(aggregate: Aggregate) -> str:
    """A token derived from the exact numbers a human is approving.

    Deriving it from the aggregate rather than issuing a random nonce means an
    approval cannot be replayed against a different result. If the cohort
    changes, a site stops abstaining, or the threshold moves, the token changes
    and the previous approval no longer opens the gate.
    """
    material = json.dumps(
        {
            "sites_asked": aggregate.sites_asked,
            "sites_answered": aggregate.sites_answered,
            "abstained": list(aggregate.abstained),
            "eligible": aggregate.eligible,
            "needs_screening": aggregate.needs_screening,
            "not_eligible": aggregate.not_eligible,
            "gaps": {k: str(v) for k, v in aggregate.gaps.items()},
            "min_cell": aggregate.min_cell,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:8]


def render(aggregate: Aggregate) -> str:
    """The trace a judge reads from three metres away."""
    lines = [
        "",
        f"  PROTOCOL   {PROTOCOL_ID}   ({len(CRITERIA)} criteria)",
        f"  SITES      {aggregate.sites_answered} of {aggregate.sites_asked} answered",
    ]
    for site in aggregate.abstained:
        lines.append(f"             ABSTAINED: {site}  -> counted as unknown, NOT as zero")
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
            lines.append(
                f"    {attribute:28} {SUPPRESSED}  (n < {aggregate.min_cell}, withheld)"
            )
        else:
            lines.append(f"    {attribute:28} {count} patients")
    return "\n".join(lines)


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    question = context.run_config.get("agent.input")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("agent.input must be a non-empty string")

    model = context.run_config.get("model.id")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model.id must be set (see .env.example for endpoints)")

    min_cell = int(context.run_config.get("policy.min-cell", DEFAULT_MIN_CELL))
    require_approval = bool(context.run_config.get("policy.require-approval", True))
    supplied_token = str(context.run_config.get("policy.approval-token", "") or "")

    # A human may also approve by typing "APPROVE <token>" into chat.
    typed = read_approval(question)
    if typed:
        supplied_token = typed
        question = earlier_question(context) or question
    abstaining = str(context.run_config.get("policy.abstaining-site", "west-suffolk") or "")
    # Panic button. Skips every model call and completes in under two seconds.
    # If an endpoint is overloaded at 17:29, the demo still runs -- and what it
    # shows is the deterministic core, which is the part that matters anyway.
    narrate = bool(context.run_config.get("policy.narrate", True))

    # --- Model call 1 of 2: route the question, declare the answer shape -----
    if narrate:
        before = snapshot_items(context)
        routed = _route(agent, model, question)
        restore_items(context, before)  # the routing JSON stays out of the transcript
    else:
        routed = {"protocol_id": PROTOCOL_ID, "query_shape": "counts", "restatement": question}

    shape = routed.get("query_shape")
    if shape not in QUERY_SHAPE_ALLOWLIST:
        # The model may well have agreed to do this. It does not matter. The
        # request is refused here, before any site is contacted, and the refusal
        # is deterministic -- there is nothing to talk out of it.
        print(
            f"\n  GUARD - query shape {shape!r} is not in {list(QUERY_SHAPE_ALLOWLIST)}"
            f" -> REFUSED\n  No site was contacted. No data was read.\n"
        )
        raise EgressViolation(
            f"query shape {shape!r} is not permitted; this system emits aggregate counts only"
        )

    chosen = routed.get("protocol_id")
    if chosen not in PROTOCOL_ALLOWLIST:
        raise ValueError(
            f"model selected protocol {chosen!r}, which is not on the allowlist "
            f"{list(PROTOCOL_ALLOWLIST)}"
        )

    # --- Deterministic middle: sites answer locally, the guard pools ---------
    site_ids = all_site_ids()
    returns = [run_site(s, abstain=(s == abstaining)) for s in site_ids]
    aggregate = combine(returns, sites_asked=len(site_ids), min_cell=min_cell)

    print(render(aggregate))

    # --- The human supervision gate -----------------------------------------
    token = approval_token(aggregate)
    if require_approval and supplied_token != token:
        print(f"\n  BLOCKED - AWAITING SPONSOR SIGN-OFF   token {token}")
        print(f"  Approve by replying:  APPROVE {token}\n")
        if narrate:
            agent.responses.create(
                {
                    "model": model,
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": (
                                f"Aggregate:\n{render(aggregate)}\n\n"
                                f"Approval token: {token}"
                            ),
                        }
                    ],
                    "instructions": GATE_REPORT,
                    "stream": True,
                }
            )
        return

    # --- Model call 2 of 2: phrase the approved answer, from counts only -----
    if not narrate:
        print("\n  APPROVED - released (narration skipped)\n")
        return

    agent.responses.create(
        {
            "model": model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": (
                        f"Sponsor's question: {question}\n\n"
                        f"Approved aggregate (counts only):\n{render(aggregate)}"
                    ),
                }
            ],
            "instructions": disclosure_instructions(
                is_partial=aggregate.is_partial,
                has_suppressed=bool(aggregate.suppressed_gaps),
            ),
            "stream": True,
        }
    )


def _route(agent: AgentSession, model: str, question: str) -> dict[str, Any]:
    """Ask the model to route the question. Its answer is checked, not trusted."""
    response = agent.responses.create(
        {
            "model": model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": (
                        f"Sponsor's question:\n{question}\n\n"
                        f"Protocols this deployment may run: {list(PROTOCOL_ALLOWLIST)}"
                    ),
                }
            ],
            "instructions": ROUTER,
            "stream": False,
            "max_output_tokens": 300,
        }
    )
    return _parse_json(response)


def _parse_json(response: dict[str, Any]) -> dict[str, Any]:
    """Pull the model's JSON reply out of a Responses object."""
    text = ""
    for item in response.get("output", []):
        if isinstance(item, dict) and item.get("type") == "message":
            content = item.get("content")
            if isinstance(content, str):
                text += content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        text += part["text"]
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
