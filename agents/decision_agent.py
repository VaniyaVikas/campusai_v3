
import json
import re
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from state import AgentState, DecisionRecord, DecisionOutcome
from llm_factory import get_llm, safe_invoke

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Decision Agent for a college administration AI system.
You receive a student query, relevant policy summaries, and extracted entities.
Output ONLY a valid JSON object (no markdown, no preamble):
{
  "outcome": "allowed" | "not_allowed" | "conditional" | "insufficient_info",
  "reasoning": "<clear explanation referencing specific rules>",
  "policy_references": ["<source1>", "<source2>"],
  "confidence": <float 0.0-1.0>,
  "conditions": "<conditions the student must meet, or null>",
  "confidence_explanation": "<one sentence explaining why this confidence level was chosen>"
}

Decision rules:
- "allowed"           → policies clearly support the request
- "not_allowed"       → policies clearly forbid it
- "conditional"       → student meets some but not all conditions
- "insufficient_info" → not enough policy context  OR  confidence < 0.55
- confidence < 0.55   → MUST return "insufficient_info"
- Always cite the specific policy source (filename) your decision is based on.
"""


def _extract_json(raw: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Cannot extract JSON from LLM response: {raw[:200]}")


def decision_agent(state: AgentState) -> AgentState:
    """LangGraph node: apply retrieved policy to produce a decision."""

    # FIX: short-circuit if spam detected
    if state.get("spam_flag"):
        fallback = DecisionRecord(
            outcome=DecisionOutcome.INSUFFICIENT_INFO,
            reasoning="Query appears to be spam or unrelated to college administration.",
            policy_references=[],
            confidence=0.0,
            conditions=None,
            confidence_explanation="Spam flag set by Query Understanding Agent.",
        )
        return {**state, "decision": fallback}

    llm = get_llm(temperature=0.1, fast=False)

    query          = state.get("normalized_query") or state["raw_query"]
    entities_str   = json.dumps(state.get("entities") or {}, indent=2)
    policy_summary = state.get("policy_summary") or "No policies retrieved."
    policy_sources = [p["source"] for p in (state.get("retrieved_policies") or [])]
    emotion        = state.get("emotion_detected", "neutral")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Student query: {query}\n\n"
                f"Student emotion: {emotion}\n\n"
                f"Extracted entities:\n{entities_str}\n\n"
                f"Policy summary:\n{policy_summary}\n\n"
                f"Available policy sources: {', '.join(policy_sources) or 'none'}"
            )
        ),
    ]

    try:
        raw    = safe_invoke(llm, messages, context="DecisionAgent")
        parsed = _extract_json(raw)

        # FIX: safe outcome enum conversion
        outcome_str = str(parsed.get("outcome", "insufficient_info")).lower()
        try:
            outcome = DecisionOutcome(outcome_str)
        except ValueError:
            outcome = DecisionOutcome.INSUFFICIENT_INFO

        # FIX: clamp confidence to [0, 1]
        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        # FIX: enforce rule — low confidence → insufficient_info
        if confidence < 0.55 and outcome not in (
            DecisionOutcome.INSUFFICIENT_INFO,
        ):
            outcome    = DecisionOutcome.INSUFFICIENT_INFO
            confidence = confidence  # keep the value, just correct outcome

        decision = DecisionRecord(
            outcome=outcome,
            reasoning=str(parsed.get("reasoning", "")),
            policy_references=parsed.get("policy_references", []),
            confidence=confidence,
            conditions=parsed.get("conditions"),
            confidence_explanation=parsed.get("confidence_explanation", ""),
        )
        return {**state, "decision": decision}

    except Exception as e:
        logger.error(f"DecisionAgent error: {e}")
        fallback = DecisionRecord(
            outcome=DecisionOutcome.INSUFFICIENT_INFO,
            reasoning="Could not parse LLM response. Please contact the admin office.",
            policy_references=[],
            confidence=0.0,
            conditions=None,
            confidence_explanation="LLM parse failure.",
        )
        return {
            **state,
            "decision": fallback,
            "errors": state.get("errors", []) + [f"DecisionAgent error: {e}"],
        }
