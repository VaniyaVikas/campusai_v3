
import json
import re
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from state import AgentState, DecisionOutcome
from config import cfg
from llm_factory import get_llm, safe_invoke

logger = logging.getLogger(__name__)

# FIX: Shorter, cleaner prompt → fewer parse issues
SYSTEM_PROMPT = """You are a Supervisor Agent validating college admin AI decisions.

Review the query, policy summary, decision, and response draft.
Output ONLY valid JSON (no markdown, no extra text):
{
  "approved": true,
  "feedback": "OK",
  "severity": "low"
}

Set approved=false ONLY if:
1. The decision directly contradicts the cited policy text.
2. The student-facing response contains factually wrong information.
3. The decision is "allowed" but the policy clearly states it is forbidden.

Do NOT reject for:
- Low confidence (insufficient_info is a valid outcome)
- Missing entities
- Policy not covering the topic (insufficient_info handles this)

severity: "low" | "medium" | "high"  — only used when approved=false.
"""


def _extract_json(raw: str) -> dict:
    """Multi-strategy JSON extraction."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    # Strategy 1: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Strategy 2: find first {...} block
    match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Strategy 3: greedy brace matching
    brace, start = 0, -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if start == -1:
                start = i
            brace += 1
        elif ch == "}":
            brace -= 1
            if brace == 0 and start != -1:
                try:
                    return json.loads(cleaned[start: i + 1])
                except json.JSONDecodeError:
                    break
    raise ValueError(f"Cannot extract JSON: {raw[:120]}")


def supervisor_agent(state: AgentState) -> AgentState:
    """LangGraph node: validate decision and action; approve or request rollback."""
    retry_count = state.get("retry_count", 0)

    # FIX: Force-approve BEFORE making any LLM call to prevent wasted retries
    if retry_count >= cfg.MAX_SUPERVISOR_RETRIES:
        logger.warning(
            f"Supervisor: max retries ({cfg.MAX_SUPERVISOR_RETRIES}) reached — force approving."
        )
        return {
            **state,
            "supervisor_approved": True,
            "supervisor_feedback": f"Force-approved after {cfg.MAX_SUPERVISOR_RETRIES} retries.",
            "supervisor_severity": "low",
        }

    decision       = state.get("decision")
    final_response = state.get("final_response", "")
    policy_summary = state.get("policy_summary", "")

    # FIX: If no decision exists, create a fallback and approve it
    if decision is None:
        return {
            **state,
            "supervisor_approved": True,
            "supervisor_feedback": "No decision to validate — auto-approved.",
            "supervisor_severity": "low",
        }

    # FIX: INSUFFICIENT_INFO with zero confidence is always a valid safe outcome
    # — do not reject it, just approve and let the student know
    outcome = decision.get("outcome")
    if (
        str(outcome) in (
            DecisionOutcome.INSUFFICIENT_INFO,
            "insufficient_info",
            "DecisionOutcome.INSUFFICIENT_INFO",
        )
        and float(decision.get("confidence", 0)) < 0.3
    ):
        return {
            **state,
            "supervisor_approved": True,
            "supervisor_feedback": "Auto-approved: insufficient_info is a safe outcome.",
            "supervisor_severity": "low",
        }

    # FIX: Use fast model — supervisor produces only a small JSON blob
    llm = get_llm(temperature=0.0, fast=True)

    # FIX: Trim policy summary to avoid token overflow
    policy_excerpt = (policy_summary or "")[:600]
    response_excerpt = (final_response or "")[:400]

    decision_str = json.dumps(
        {
            "outcome":           str(decision.get("outcome", "")),
            "reasoning":         str(decision.get("reasoning", ""))[:300],
            "confidence":        decision.get("confidence", 0),
            "policy_references": decision.get("policy_references", []),
        },
        indent=2,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Query: {state['raw_query']}\n\n"
                f"Policy summary (excerpt):\n{policy_excerpt}\n\n"
                f"Decision:\n{decision_str}\n\n"
                f"Response draft (excerpt):\n{response_excerpt}"
            )
        ),
    ]

    try:
        raw    = safe_invoke(llm, messages, context="SupervisorAgent")
        parsed = _extract_json(raw)

        approved = bool(parsed.get("approved", True))   # FIX: default True on ambiguity
        feedback = str(parsed.get("feedback", "OK"))
        severity = str(parsed.get("severity", "low"))

        return {
            **state,
            "supervisor_approved": approved,
            "supervisor_feedback": feedback,
            "supervisor_severity": severity,
            "retry_count": retry_count + (0 if approved else 1),
        }

    except Exception as e:
        # FIX: parse/network error → approve with warning, don't block the pipeline
        logger.error(f"SupervisorAgent error (approving by default): {e}")
        return {
            **state,
            "supervisor_approved": True,
            "supervisor_feedback": f"Supervisor error (approved by default): {e}",
            "supervisor_severity": "low",
            "errors": state.get("errors", []) + [f"SupervisorAgent error: {e}"],
        }


def should_rollback(state: AgentState) -> str:
    """
    LangGraph conditional edge function.
    Returns 'approved' or 'rollback'.
    FIX: also force-approved when retry_count is at the limit (belt-and-suspenders).
    """
    if state.get("supervisor_approved"):
        return "approved"
    if state.get("retry_count", 0) >= cfg.MAX_SUPERVISOR_RETRIES:
        return "approved"
    return "rollback"
