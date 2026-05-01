
import uuid
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from state import (
    AgentState, ActionRecord, ActionType,
    DecisionOutcome, Language,
)
from llm_factory import get_llm, safe_invoke

logger = logging.getLogger(__name__)

RESPONSE_SYSTEM_PROMPT = """You are a helpful, empathetic college administration assistant named CampusAI.
Write a clear, friendly response to the student based on the decision provided.

Language rules:
- If detected_language is "gujarati" → respond in Gujarati script.
- If detected_language is "hinglish" → respond in simple Hinglish (Hindi + English mix, Roman script).
- Otherwise → respond in English.

Tone rules:
- If emotion is "urgent" or "frustrated" → be extra empathetic, acknowledge the urgency first.
- If emotion is "confused" → explain clearly step-by-step.
- If decision is "not_allowed" → explain the exact rule violated and suggest the next step.
- If decision is "conditional" → list every condition clearly.
- Keep the response under 200 words.
- Do NOT use markdown formatting. Plain text only.
- End with a helpful next-step suggestion.
"""


def _determine_action_type(state: AgentState) -> ActionType:
    intent  = state.get("intent", "")
    outcome = (state.get("decision") or {}).get("outcome")

    # Complaints → ticket
    if "grievance" in intent or "complaint" in intent:
        return ActionType.TICKET_CREATE

    # Form-related intents → form suggestion
    form_keywords = ("form", "atkt", "admission", "hall_ticket", "register", "placement")
    if any(k in intent for k in form_keywords):
        return ActionType.FORM_SUGGESTION

    # Email if student address provided
    if state.get("student_email"):
        return ActionType.EMAIL_REPLY

    return ActionType.INFORMATION_ONLY


def action_agent(state: AgentState) -> AgentState:
    """LangGraph node: generate student-facing response and determine action."""
    llm      = get_llm(temperature=0.3, fast=False)
    decision = state.get("decision")
    emotion  = state.get("emotion_detected", "neutral")

    # FIX: safe language comparison – Language is a str enum
    lang = state.get("detected_language")
    if lang is None:
        lang = Language.UNKNOWN
    # Normalise to string for comparison
    lang_val = lang.value if hasattr(lang, "value") else str(lang)

    lang_note = {
        "gujarati": "Respond in Gujarati script.",
        "hinglish": "Respond in Hinglish (Hindi + English mix, Roman script).",
    }.get(lang_val, "Respond in English.")

    decision_summary = (
        f"Decision outcome: {decision['outcome']}\n"
        f"Reasoning: {decision['reasoning']}\n"
        f"Conditions: {decision.get('conditions') or 'None'}\n"
        f"Confidence: {decision['confidence']:.0%}"
        if decision else "No decision available."
    )

    messages = [
        SystemMessage(
            content=RESPONSE_SYSTEM_PROMPT
            + f"\n\nLanguage instruction: {lang_note}"
            + f"\nStudent emotion: {emotion}"
        ),
        HumanMessage(
            content=(
                f"Original query: {state['raw_query']}\n\n"
                f"Normalized query: {state.get('normalized_query', '')}\n\n"
                f"{decision_summary}"
            )
        ),
    ]

    try:
        final_response = safe_invoke(llm, messages, context="ActionAgent")
    except Exception as e:
        logger.error(f"ActionAgent LLM error: {e}")
        final_response = (
            "Sorry, I could not process your query right now. "
            "Please visit the Student Helpdesk (Admin Block, Mon-Sat 9AM-5PM) "
            "or email helpdesk@college.edu for help."
        )
        state["errors"] = state.get("errors", []) + [f"ActionAgent LLM error: {e}"]

    action_type = _determine_action_type(state)

    # Form suggestion mapping
    form_name  = None
    intent     = state.get("intent", "")
    FORM_MAP   = {
        "atkt":         "ATKT Examination Form",
        "admission":    "Admission Application Form",
        "fee":          "Fee Payment Receipt Form",
        "hall_ticket":  "Hall Ticket Request Form",
        "placement":    "Placement Registration Form",
        "revaluation":  "Revaluation Application Form",
        "register":     "Course Registration Form",
    }
    if action_type == ActionType.FORM_SUGGESTION:
        for key, name in FORM_MAP.items():
            if key in intent:
                form_name = name
                break

    ticket_id = f"TICKET-{uuid.uuid4().hex[:8].upper()}"

    # FIX: always create an action; subject reflects both intent and outcome
    outcome_label = (
        decision["outcome"].value
        if decision and hasattr(decision.get("outcome"), "value")
        else str((decision or {}).get("outcome", "inquiry"))
    )
    subject = (
        f"Re: {state.get('intent', 'general').replace('_', ' ').title()} "
        f"– {outcome_label.replace('_', ' ').title()}"
    )

    action = ActionRecord(
        action_type=action_type,
        subject=subject,
        body=final_response,
        recipient=state.get("student_email"),
        form_name=form_name,
        ticket_id=ticket_id,
        sent=False,
    )

    return {
        **state,
        "action":         action,
        "final_response": final_response,
    }
